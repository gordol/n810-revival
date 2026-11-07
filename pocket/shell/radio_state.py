"""Radio runtime: cached projections and explicit owner-read intents; no UI drawing."""
import importlib.util
import json
from pathlib import Path
import time
import threading
import marshal

_root=Path(__file__).resolve().parent
_path=_root/'vendor/packet-console/web-console/radio-manager-adapter.py'
_spec=importlib.util.spec_from_file_location('pocket_radio_adapter',_path)
adapter=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(adapter)


def snapshot_token(value):
    """Typed, detached comparison bytes; never transmitted or read from a file."""
    # The built-in C encoder is faster on ARM11 than rebuilding JSON strings.
    # Version 2 compares values independently of shared-object identities.
    return marshal.dumps(value,2)


class State:
    def __init__(self,path=None,clock=time.time,source=None,read_client=None):
        self.path=Path(path) if path else None;self.clock=clock;self.source=source
        self.read_client=read_client;self.read_telemetry=None;self.read_seen=None;self.read_message=''
        self._automatic_read_client=False;self._read_source=None
        self.payload={};self.result=adapter.adapt({},clock());self.error=None
        self.signature=None;self.deadline=None;self.version=0
        self._change_lock=threading.Lock();self._generation=1;self._consumed_generation=0
        self._wakeup=None;self._closed=False;self._read_notifies=False
        self.catalog_model=None
        self.catalog_token=None;self.observation_token=None
        if self.source and callable(getattr(self.source,'bind_wakeup',None)):
            self.source.bind_wakeup(self._source_changed)
    def bind_wakeup(self,callback):
        """Use the shell's existing Inbox; producers only mark pending source work."""
        if callback is not None and not callable(callback):raise TypeError('wakeup must be callable')
        with self._change_lock:self._wakeup=callback
        self._read_notifies=False
        if self.read_client and callable(getattr(self.read_client,'bind_wakeup',None)):
            self.read_client.bind_wakeup(self._source_changed if callback is not None else None)
            self._read_notifies=callback is not None
    def _source_changed(self):
        with self._change_lock:
            if self._closed:return
            self._generation+=1;callback=self._wakeup
        if callback is not None:callback()
    @property
    def read_job(self):return self.read_client.publication if self.read_client else {}
    @property
    def can_read(self):return self.read_client is not None
    def read_action(self,action):
        client=self.read_client
        if client is None:self.read_message='No owner read endpoint configured.';return False
        accepted=bool(getattr(client,{'read':'start','check':'check','cancel':'cancel'}[action])())
        if accepted:self.read_message=''
        elif action=='read' and client.publication.get('uncertain'):self.read_message='Previous read outcome unknown; use Check or Cancel with the same request.'
        elif client.active:self.read_message='A read is already running.'
        else:self.read_message='No active read request, or the read client is closed.'
        return accepted
    def close(self):
        with self._change_lock:self._closed=True;self._wakeup=None
        if self.source and callable(getattr(self.source,'bind_wakeup',None)):self.source.bind_wakeup(None)
        if self.read_client:self.read_client.close()
        if self.source and hasattr(self.source,'close'):self.source.close()
    def with_read_telemetry(self,payload):
        actual=self.read_telemetry
        if actual is None:return payload
        envelope=payload.get('live') or {};live=adapter.data(envelope)
        current=live.get('radio_live') or {}
        def publication_stamp(telemetry):
            # Ordering content is separate from owner liveness/field freshness.
            # v2 has no heartbeat; its published_at is content publication only.
            import math
            if not isinstance(telemetry,dict):return None
            version=telemetry.get('version')
            if version is None or type(version) is int and version==1:key='heartbeat'
            elif type(version) is int and version==2:key='published_at'
            else:return None
            value=telemetry.get(key)
            try:return value if type(value) in (int,float) and math.isfinite(value) and value>=0 else None
            except OverflowError:return None
        current_stamp=publication_stamp(current);actual_stamp=publication_stamp(actual)
        if current and (actual_stamp is None or current_stamp is not None and current_stamp>actual_stamp):return payload
        live=dict(live,radio_live=actual)
        envelope=dict(envelope,data=live) if 'data' in envelope else live
        return dict(payload,live=envelope)
    def publication_pending(self):
        """A new source/job needs app updates; an age deadline does not."""
        with self._change_lock:
            if self._generation!=self._consumed_generation:return True
        delay=getattr(self.source,'delay',lambda now:None)(self.clock())
        return delay is not None and delay<=0 or bool(self.read_client and self.read_job is not self.read_seen)
    def update(self,force=False):
        if self._closed:return False
        now=self.clock();changed=False
        with self._change_lock:generation=self._generation
        source_delay=getattr(self.source,'delay',lambda now:None)(now)
        check_catalog=force or generation!=self._consumed_generation or source_delay is not None and source_delay<=0
        if check_catalog and (self.read_client is None or self._automatic_read_client):
            endpoint=getattr(self.source,'radio_read_endpoint',None)
            endpoint=Path(endpoint) if endpoint is not None else None
            attachment=getattr(self.source,'source',self.source)
            if endpoint!=getattr(self.read_client,'path',None) or attachment is not self._read_source:
                self._read_source=attachment
                if self.read_client:self.read_client.close()
                from radio_read_client import RadioRead
                self.read_client=RadioRead(endpoint) if endpoint is not None else None
                self._automatic_read_client=self.read_client is not None
                self.read_telemetry=None;self.read_seen=None
                if self.read_client:self.read_client.bind_wakeup(self._source_changed if self._wakeup is not None else None)
                self._read_notifies=self.read_client is not None and self._wakeup is not None
                changed=True
        self.publication_read=check_catalog
        job=self.read_job
        if self.read_client and job is not self.read_seen:
            self.publication_read=True
            self.read_seen=job;self.version+=1
            if job.get('radio_live') is not None:self.read_telemetry=job['radio_live'];changed=True
        if check_catalog:
            if force and self._consumed_generation and self.source and callable(getattr(self.source,'refresh',None)):self.source.refresh()
            if self.source:
                payload=self.with_read_telemetry(self.source.read(now))
                # Always adopt the newest complete publication. Python equality
                # may conflate typed changes; revision tokens inspect this value.
                # System samples and packet history do not change the radio
                # projection. Its detached keys below select the relevant facts.
                self.payload=payload
            if self.path:
                try:
                    stat=self.path.stat();signature=(stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
                    if stat.st_size>4*1024*1024:raise ValueError('connector snapshot exceeds 4 MiB')
                    if signature!=self.signature:
                        payload=json.loads(self.path.read_text())
                        if not isinstance(payload,dict):raise ValueError('connector snapshot must be an object')
                        self.payload=self.with_read_telemetry(payload);self.signature=signature;changed=True
                    if self.error and self.error.startswith('Connector snapshot unavailable:'):self.error=None;changed=True
                except (OSError,ValueError) as error:
                    self.signature=None
                    message='Connector snapshot unavailable: '+str(error)
                    if message!=self.error:self.error=message;changed=True
            if self.error is None or self.error.startswith(('Radio snapshot updater:','Receive transport:')):
                live=self.payload.get('live') or {}
                message=live.get('error') if isinstance(live,dict) else None
                prefix='Receive transport: ' if self.source and getattr(self.source,'remote',False) else 'Radio snapshot updater: '
                message=prefix+str(message) if message else None
                if message!=self.error:self.error=message;changed=True
        self.payload=self.with_read_telemetry(self.payload)
        live=adapter.data(self.payload.get('live'))
        owner_source=getattr(self.source,'receive',None) or self.source
        owner_context=getattr(owner_source,'owner_context',None) if self.path is None else None
        observations=dict(live={name:live.get(name) for name in
                          ('radio_live','radio_model','captured','history_source','receive_subscription','receive_connected')},
                          owner_context=owner_context,
                          error=adapter.model.obj(self.payload.get('live')).get('error'),
                          connector=self.payload.get('connector'),operation=self.payload.get('operation','view'),
                          selection=self.payload.get('selection'))
        # Detached observations also catch an existing producer updating a
        # dictionary in place. Packet history is not copied for this projection.
        # Preserve numeric/boolean distinctions and in-place producer edits.
        # Binary tokens avoid rebuilding large sorted JSON strings on UI ticks.
        observation_token=snapshot_token(observations)
        if observation_token!=self.observation_token:changed=True
        catalog=adapter.data(self.payload.get('catalog'))
        retained={name:catalog.get(name) for name in ('radio_snapshot','radio_banks','radio_profiles')}
        catalog_token=(snapshot_token(retained)
                       if check_catalog else self.catalog_token)
        if catalog_token!=self.catalog_token:changed=True
        if force or changed or self.deadline is not None and now>=self.deadline:
            # Detach only a changed revision; live ages are recomputed below.
            if self.catalog_model is None or catalog_token!=self.catalog_token:
                # Normalization emits plain data. Detach it with the same C
                # codec used for revision keys instead of walking every field
                # again through Python's generic object-copy machinery.
                catalog_model=marshal.loads(snapshot_token(adapter.model.normalize_catalog(retained)))
            else:catalog_model=self.catalog_model
            result=adapter.adapt(self.payload,now,catalog_model=catalog_model,owner_context=owner_context)
            # Publish the input/projection pair only after the entire adaptation
            # succeeds. Failed new data must be retried, not marked as cached.
            self.catalog_model=catalog_model
            self.catalog_token,self.observation_token=catalog_token,observation_token
            self.deadline=result['next_invalidation_at']
            changed_result=result!=self.result
            self.result=result
            if changed_result:self.version+=1
        else:changed_result=False
        # Commit only the generation captured before reading. Arrivals during a
        # read/normalization remain pending and cannot be lost to a clear flag.
        self._consumed_generation=generation
        return changed_result
    def delay(self):
        if self._closed:return None
        with self._change_lock:
            if self._generation!=self._consumed_generation:return 0.
        delays=[];now=self.clock()
        source_delay=getattr(self.source,'delay',lambda now:None)(now)
        if source_delay is not None:delays.append(source_delay)
        if self.deadline is not None:delays.append(max(0,self.deadline-now))
        # Compatibility while an explicit Read owner lacks a completion wake.
        # This is armed only during that finite job, never by retained files.
        if self.read_client and self.read_client.active and not self._read_notifies:delays.append(1.)
        return min(delays) if delays else None
    def label(self,width):
        s=self.result['statusbar'];r=s['radio'];state=r['state']
        radio={'paused':'paused','live':'recent','owner_unavailable':'stale','unavailable':'unknown'}.get(state,state)
        if state=='disconnected' and not r['link'].get('current_known'):radio='last disconnected; observation '+r['link'].get('freshness','unknown')
        if state=='paused' and r['link']['state']=='reported_up':radio='connected; polling off'
        if width<120:return 'Radio '+radio+' '
        ssh={'recent':'ok','failed':'failed','stale':'stale','unknown':'unknown'}[s['ssh']['state']]
        feed={'recent':'ok','unavailable':'down','stale':'stale','unknown':'unknown'}[s['feed']['state']]
        bt={'reported_up':'up','reported_down':'down','stale':'stale','unknown':'unknown'}[r['link']['state']]
        if r['link']['state']=='unknown' and r['link'].get('freshness')=='stale':bt='stale; current unknown'
        attachment=(self.payload.get('connector') or {}).get('attachment') or {}
        if attachment.get('transport')=='ssh':ssh='connected' if attachment.get('connected') else 'disconnected'
        transport='Local' if self.payload.get('connector',{}).get('local') is True else 'SSH '+ssh
        return f'{transport}  Feed {feed}  BT {bt}  Radio {radio} '
    def panel(self,width,ascii=False):
        s=self.result['statusbar'];radio=s['radio'];entries=[];styles={}
        parts=[('Radio',radio['state'])] if width<120 else [('SSH',s['ssh']['state']),('RX',s['feed']['state']),('BT',radio['link']['state']),('Radio',radio['state'])]
        attachment=(self.payload.get('connector') or {}).get('attachment') or {}
        if attachment.get('transport')=='ssh':
            parts=[(name,('recent' if attachment.get('connected') else 'failed') if name=='SSH' else state) for name,state in parts]
        if self.source and not getattr(self.source,'remote',False):parts=([('Local','recent')] if width>=120 else [])+[p for p in parts if p[0]!='SSH']
        for name,state in parts:
            role='good' if state in ('recent','reported_up','live') else 'bad' if state in ('failed','reported_down','disconnected') else 'unknown' if state in ('unknown','unavailable') else 'warning'
            if name=='Radio':
                link=radio['link']
                role='bad' if link['state']=='reported_down' else 'good' if link.get('current_known') and link.get('current_connected') is True else 'warning' if link.get('freshness')=='stale' else 'unknown'
                entries.append(('radio:Radio','Radio  '));styles['radio:Radio']=role
                continue
            symbol=('+' if role=='good' else '!' if role=='bad' else '?') if ascii else ('●' if role=='good' else '!' if role=='bad' else '○')
            suffix=' down' if name=='BT' and state=='reported_down' else ' stale' if state in ('stale','owner_unavailable') else ''
            if name=='BT' and state=='unknown' and radio['link'].get('freshness')=='stale':suffix=' stale; current unknown'
            action='radio:'+name;label='Feed' if name=='RX' else name
            entries.append((action,f'{symbol} {label}{suffix}  '));styles[action]=role
        return entries,styles

    def link_observation(self):
        link=self.result['statusbar']['radio']['link'];stamp=link.get('observed_at');age=link.get('age_seconds')
        import time_display
        try:observed=time_display.now_at(stamp).strftime('%Y-%m-%d %H:%M:%S %Z') if adapter.model.number(stamp) else 'unknown'
        except (OverflowError,OSError,ValueError):observed='unknown'
        elapsed=str(int(age))+'s' if adapter.model.number(age) and age>=0 else 'unknown'
        if link.get('source')=='feed_live_owner' and link.get('current_known'):
            return 'Link state last changed: '+observed+' · live owner subscribed'
        return 'Link observed: '+observed+' · age '+elapsed+' · '+str(link.get('freshness','unknown'))

    def catalog_sync(self):
        device=(self.payload.get('connector') or {}).get('device') or {}
        return device.get('radio_catalog_sync')

    def receive_observations(self):
        """Snapshot receipt is distinct from the original RF capture time."""
        import time_display
        live=adapter.data(self.payload.get('live'))
        rows=live.get('raw_records') or live.get('packets') or ()
        stamps=[time_display.epoch(row.get('time')) for row in rows
                if isinstance(row,dict) and row.get('direction')=='radio_to_host']
        stamps=[stamp for stamp in stamps if stamp is not None]
        def shown(stamp):
            try:return time_display.now_at(stamp).strftime('%Y-%m-%d %H:%M:%S %Z') if adapter.model.number(stamp) else 'Unknown'
            except (OverflowError,OSError,ValueError):return 'Unknown'
        return ['Latest received packet: '+shown(max(stamps) if stamps else None),
                'Receive snapshot loaded: '+shown(live.get('captured'))]
