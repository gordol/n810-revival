"""Shared retained app facts over the existing connector; no receive transport."""
import datetime
from runtime_codec import copy_data
import json
from pathlib import Path
import time


def data(envelope):
    if not isinstance(envelope,dict):return {}
    value=envelope.get('data',envelope)
    return value if isinstance(value,dict) else {}


def reconcile_views(host):
    """Publish source revisions to retained UI owners, including hidden Feed.

    Called only when Catalog.update reports a source change. This is independent
    of drawing, focus and input; it does not ask any owner for session_state.
    """
    feed=getattr(host,'app_forms',{}).get('Radio Feed')
    feed=getattr(feed,'owner',feed)
    if feed is not None:feed.update()


class Catalog:
    def __init__(self,state,schedule=None,clock=time.time):
        from device_retained import owner
        self.history_limit=owner('n810-frame-history.py').limits()[0]
        self.state=state;self.clock=clock;self.revision=0;self.records_revision=0
        self.receive_input=None;self.metadata_input=None
        root=Path(__file__).resolve().parent
        bundled=root/'vendor/apps/data/nets-puget-sound.json'
        self.path=Path(schedule) if schedule else bundled
        self.schedule=None;self.schedule_signature=None;self.check_at=0
        self.lines=();self.evidence=();self.bss_records=();self.outbox=();self.services={};self.nets={};self.walks={};self.feed={};self.heard={};self.error=None
    def update(self):
        now=self.clock()
        if now>=self.check_at:
            self.check_at=now+1
            try:
                stat=self.path.stat();signature=(stat.st_mtime_ns,stat.st_size)
                if stat.st_size>2*1024*1024:raise ValueError('schedule too large')
                if signature!=self.schedule_signature:
                    schedule=json.loads(self.path.read_text())
                    if not isinstance(schedule,dict) or not isinstance(schedule.get('nets'),list):raise ValueError('invalid schedule')
                    self.schedule=schedule;self.schedule_signature=signature
            except (OSError,ValueError):self.schedule=None;self.schedule_signature=None
        live=data(self.state.payload.get('live'));catalog=data(self.state.payload.get('catalog'))
        statusbar=getattr(self.state,'result',{}).get('statusbar',{})
        radio_link=statusbar.get('radio',{}).get('link',{})
        snapshot_observation=statusbar.get('feed',{})
        receive=dict(packets=live.get('packets',())[-self.history_limit:],raw_records=(live.get('raw_records') or [])[-self.history_limit:])
        # Only facts projected by these views belong in their invalidation key.
        # Cached link/snapshot facts are metadata; general owner versions do not
        # invalidate packet parsing or rebuild records.
        metadata=dict(history_device=id(getattr(getattr(self.state,'source',None),'source',getattr(self.state,'source',None))),outbox=catalog.get('outbox') or (),nets_state=catalog.get('nets_state'),
                      walks=catalog.get('walks') or [],schedule=self.schedule,
                      error=live.get('retained_error') or getattr(self.state,'error',None),
                      source=str(live.get('history_source') or 'Receive source unavailable'),
                      subscribed=bool(live.get('receive_subscription')),connected=bool(live.get('receive_connected')),
                      gap=bool(live.get('receive_gap_possible')),activity=live.get('directory_activity'),
                      radio_link=radio_link,snapshot_observation=snapshot_observation)
        receive_changed=receive!=self.receive_input
        metadata_changed=metadata!=self.metadata_input
        if not receive_changed and not metadata_changed:return False
        self.revision+=1
        if metadata_changed:
            previous=self.metadata_input or {}
            self.metadata_input={key:previous[key] if key in previous and value==previous[key] else copy_data(value)
                                 for key,value in metadata.items()}
        if receive_changed:
            # Own snapshots so equal-length/in-place edits cannot evade comparison.
            self.receive_input=copy_data(receive);self.records_revision+=1
            lines=[];evidence=[]
            for packet in self.receive_input['packets']:
                if not isinstance(packet,dict) or packet.get('direction')!='radio_to_host':continue
                try:
                    raw=packet['raw'];stamp=packet['time']
                    if not isinstance(raw,str) or not isinstance(stamp,str):continue
                    # Domain parsers accept complete capture timestamps as well as
                    # legacy time-only streams. Never truncate replay identities.
                    captured=datetime.datetime.fromisoformat(stamp)
                    if captured.tzinfo is None or not stamp.isprintable():continue
                    text=stamp+' '+raw
                except (KeyError,ValueError):continue
                lines.append(text);evidence.append(packet)
            self.lines=tuple(lines);self.evidence=tuple(evidence)
            bss=[]
            if self.receive_input['raw_records']:
                from device_retained import owner
                classifier=owner('n810-messages-model.py').classify_frame
            for record in self.receive_input['raw_records']:
                if not isinstance(record,dict) or record.get('direction')!='radio_to_host':continue
                try:
                    frame=bytes.fromhex(record['frame'])
                    if frame.startswith(b'\x00\x01') and classifier(frame)=='bss':bss.append(record)
                except (KeyError,TypeError,ValueError):continue
            self.bss_records=tuple(bss)
        self.outbox=tuple(self.metadata_input['outbox'])
        self.error=live.get('retained_error') or getattr(self.state,'error',None)
        source=str(live.get('history_source') or 'Receive source unavailable')
        freshness='Receive socket updates · bounded raw snapshots · original RX dates retained' if live.get('receive_subscription') else 'Original RX dates retained; snapshot is not a live subscription'
        if live.get('receive_gap_possible'):freshness+=' · reconnect gap possible beyond live history'
        connection='Offline' if self.error else 'Listening' if live.get('receive_connected') else 'Connecting' if live.get('receive_subscription') else 'Offline'
        metadata=dict(lines=self.lines,packet_times={line:packet['time'] for line,packet in zip(self.lines,self.evidence)},source=source,freshness=freshness,revision=self.revision,records_revision=self.records_revision,connection=connection,error=self.error,status=connection,last_record=self.evidence[-1].get('time') if self.evidence else None)
        self.feed=dict(metadata,history_page=self.history_page,history_device=self.metadata_input['history_device'],records=tuple(self.receive_input['raw_records']),evidence=self.evidence,connected=live.get('receive_connected',False),subscribed=live.get('receive_subscription',False),error=self.error,
                       radio_link=copy_data(self.metadata_input['radio_link']),snapshot_observation=copy_data(self.metadata_input['snapshot_observation']))
        activity=self.metadata_input['activity']
        self.heard=activity if isinstance(activity,dict) else dict(events=(),revision=0,attached=False,connected=False,source='Activity source unavailable',scope=None,error=None,gap_possible=False)
        self.services=metadata
        self.nets=dict(metadata,data=self.metadata_input['schedule'],settings=self.metadata_input['nets_state'],
                       source='Published schedule / retained announcements',
                       status='Read only · existing Nets app owns reminder delivery')
        self.walks=dict(walks=self.metadata_input['walks'],source='Retained walk journals',freshness='Saved evidence; no probe is armed',revision=self.revision)
        return True
    def service_view(self):return self.services
    def net_view(self):return self.nets
    def walk_view(self):return self.walks

    def history_page(self,before=None,anchor=None):
        source=self.state.source
        method=getattr(source,'history_page',None)
        if method is None:raise ValueError('This connection does not provide packet history')
        return method(before,anchor=anchor)

    def feed_view(self):return self.feed
    def heard_view(self):return self.heard
