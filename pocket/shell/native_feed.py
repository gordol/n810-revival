"""Bounded read-only packet log over the desktop's existing shared receive source."""
from collections import namedtuple
import json
import time
import hashlib
import time_display
import re
import textwrap
import math
from app_widgets import AdaptivePanels,Canvas,PanelSpec,SelectList, status_text, DetailBlock
from device_retained import owner


class FeedAction(namedtuple('FeedAction','id label keys contexts',defaults=(('browse', 'inspect'),))):
    __slots__=()
    id:str
    label:str
    keys:tuple
    contexts:tuple

# App actions are local; shared controls retain editing/modal ownership.
FEED_ACTIONS=(
    FeedAction('feed.evidence.toggle','Toggle evidence',('e',)),
    FeedAction('feed.inspector.toggle','Expand/restore inspector; show original evidence',('i',)),
    FeedAction('feed.order.reverse','Reverse recorded-time order',('t',)),
    FeedAction('feed.direction.cycle','Cycle all / RX / TX',('f',)),
    FeedAction('feed.latest','Jump to latest packets',('g',)),
    FeedAction('feed.older','Load older packets',('o',)),
    FeedAction('feed.inspect.selection','Focus inspector; show original evidence',('\r','\n')),
    FeedAction('pane.next','Next pane',('\t',)),
    FeedAction('pane.previous','Previous pane',('backtab',)),
    FeedAction('pane.resize.begin','Resize split',('\x12','r')),
    FeedAction('pane.restore','Restore both panes',('\x1b',),('expanded inspector',)),
    FeedAction('list.previous','Previous record',('up','k'),('browse',)),
    FeedAction('list.next','Next record',('down','j'),('browse',)),
    FeedAction('list.first','First record in displayed order',('home',),('browse',)),
    FeedAction('list.last','Last record in displayed order',('end',),('browse',)),
    FeedAction('list.page.previous','Previous list page',('pageup',),('browse',)),
    FeedAction('list.page.next','Next list page',('pagedown',),('browse',)),
    FeedAction('search.begin','Begin list search',('/',),('browse',)),
    FeedAction('search.next','Next accepted-query match',('n',),('browse',)),
    FeedAction('search.previous','Previous accepted-query match',('N',),('browse',)),
    FeedAction('scroll.previous','Scroll details up',('up','k'),('inspect',)),
    FeedAction('scroll.next','Scroll details down',('down','j'),('inspect',)),
    FeedAction('scroll.page.previous','Page details up',('pageup',),('inspect',)),
    FeedAction('scroll.page.next','Page details down',('pagedown',),('inspect',)),
    FeedAction('scroll.first','Start of details',('home',),('inspect',)),
    FeedAction('scroll.last','End of details',('end',),('inspect',)),
    FeedAction('search.accept','Accept query',('\r','\n'),('search editor',)),
    FeedAction('search.cancel','Clear query / leave search',('\x1b',),('search editor or accepted query',)),
    FeedAction('search.edit','Edit query',('printable text','backspace'),('search editor',)),
    FeedAction('pane.resize.adjust','Adjust split',('left','right'),('split resize',)),
    FeedAction('pane.resize.commit','Commit split',('\r','\n'),('split resize',)),
    FeedAction('pane.resize.cancel','Cancel split',('\x1b',),('split resize',)),
)
ACTION_BY_ID={row.id:row for row in FEED_ACTIONS}
KEY_ACTIONS={(context,key):row.id for row in FEED_ACTIONS for context in row.contexts
             if context in ('browse','inspect') for key in row.keys}
KEY_LABELS={'\r':'Enter','\n':'Enter','\t':'Tab','backtab':'Shift-Tab','\x12':'Ctrl-R','\x1b':'Esc',' ':'Space'}
def binding_label(action):
    return ' / '.join(dict.fromkeys(KEY_LABELS.get(key,key) for key in action.keys))


class RadioFeed:
    def presentation_interval(self):return 1. if self.metadata else None
    actions=tuple((row.keys[0],row.label) for row in FEED_ACTIONS if row.id in ('feed.evidence.toggle','feed.inspector.toggle','feed.order.reverse','feed.direction.cycle','feed.older','feed.latest','pane.resize.begin'))
    def navigation_action_spans(self,key):
        identity=KEY_ACTIONS.get(('browse',key))
        return tuple((y,x,w,'input') for x,y,w,action in self._actions if action==identity)
    def help_pages(self):
        from app_help_content import pages
        controls=tuple(binding_label(row)+' — '+row.label+' ['+', '.join(row.contexts)+']' for row in FEED_ACTIONS)
        return (('Controls',controls),('Reading the Feed',(
            'Packet details and Original evidence are display modes; e toggles them and focuses the inspector.',
            'Enter and i retain their existing behavior: both show Original evidence.',
            'Recorded time is the retained record time, not arrival order or verified RF transmission time.',
            'Scroll past the oldest packet or press o to load an older page. Press g to return to the latest packets.',
            'Selection stays on its retained identity; filtering can hide it without selecting another record.',
            'Mouse wheel scrolls the pane under the pointer. Toolbar buttons invoke actions even while search is active.',
            'Search editing owns printable keys. Tab accepts search and changes pane.',
            'Right-click / Shift-F10 opens record actions. Inspect original evidence uses the retained capture.',
            'Host write evidence does not prove over-the-air delivery. Unknown timestamps/bytes remain unknown.',
        )))+pages('Radio Feed')[3:]
    def __init__(self,provider):
        self.provider=provider;self.width=96;self.height=28
        self.rows=();self.list=SelectList(());self.selected=None;self.scroll=0
        self.layout=AdaptivePanels((PanelSpec('feed','Packets',28,52),PanelSpec('inspect','Original record',28,42)))
        self.direction='all';self.oldest=False;self.evidence=False;self._all_records=();self._source_token=None;self._view_token=None;self._actions=[]
        self._history_pool=None;self._history_pending=None;self._history_cursor=None;self._history_more=True;self._history_rows=();self.history_error='';self._history_loader=None;self._history_device=None
        self.history_module=owner('n810-frame-history.py')
        self.history_limit=self.history_module.limits()[0]
        self.browse_limit=self.history_module.setting('POCKET_RX_BROWSE_RECORDS',1000,10000)
        self.metadata={};self._token=None;self._rects={};self._hits=[];self._spans=[]
        self.layout.ratio=.65;self._restoring=False;self._detail_length=0
        self.monitor=owner('n810-packet-monitor.py');self.messages=owner('n810-messages-model.py');self._diagnostic_key=None;self._diagnostic_value=None
    @staticmethod
    def identity(row):
        digest=hashlib.sha256((str(row.get('frame') or '')+'\0'+str(row.get('raw') or '')).encode()).hexdigest()
        return (row.get('time'),digest,None,row.get('direction'))
    def diagnostic(self,row):
        key=(self._source_token,self.identity(row))
        if key!=self._diagnostic_key:
            self._diagnostic_value=self.messages.receive_diagnostic(row);self._diagnostic_key=key
        return self._diagnostic_value
    def describe(self,row):
        raw=row.get('raw')
        if raw and not raw.lower().startswith('malformed'):return raw
        if not row.get('frame'):return raw or 'Original frame unavailable'
        diagnostic=self.diagnostic(row);protocol=diagnostic['protocol'];observation=diagnostic.get('observation')
        if observation and protocol=='bss':
            source=observation.get('source');destination=observation.get('to')
            return 'BSS '+str(source if source is not None else '(unknown)')+'→'+str(destination if destination not in (None,'') else '(unknown/empty)')+' '+str(observation.get('text') or '(no text field)')
        if protocol=='ax25':
            try:decoded=self.monitor.describe(bytes.fromhex(row['frame']))
            except (ValueError,KeyError,TypeError):decoded=None
            return decoded if decoded and not decoded.lower().startswith('malformed') else 'AX.25-shaped frame · payload interpretation unavailable'
        if protocol=='kiss_control':return 'KISS control · command '+str(diagnostic.get('kiss_command'))+' / port '+str(diagnostic.get('kiss_port'))
        stage=next((item for item in diagnostic['stages'] if item['status'] in ('invalid','unsupported')),None)
        return protocol.upper()+' · '+(stage['reason'] if stage else 'Original frame retained')
    def bind_session(self,callback):
        self._session_callback=callback;self._session_selection=(self.direction,self.oldest,self.selected)
        self.layout.bind_session(callback)
    def _session_changed(self):
        state=(self.direction,self.oldest,self.selected)
        if state!=getattr(self,'_session_selection',state):
            self._session_selection=state
            callback=getattr(self,'_session_callback',None)
            if callback:callback()
    def session_state(self):
        return dict(panels=self.layout.session_state(),direction=self.direction,oldest=self.oldest,selected=list(self.selected) if self.selected else None)
    def restore_session(self,state):
        if not isinstance(state,dict):return
        if state.get('direction') in ('all','rx','tx'):self.direction=state['direction']
        self.oldest=state.get('oldest') is True
        self.layout.restore_session(state.get('panels',state))
        selected=state.get('selected')
        if isinstance(selected,list) and len(selected)==4 and all(v is None or isinstance(v,str) for v in selected):self.selected=tuple(selected);self._restoring=True
    def compact(self,row):
        clock=time_display.clock(row.get('time'))
        shown=time_display.displayed(row.get('time'))
        if shown is not None and shown.date()!=getattr(self,'_display_day',shown.date()):clock=shown.strftime('%m-%d ')+clock
        text=self.describe(row);match=re.fullmatch(r'(\S+)>(\S+) ctl=[0-9a-f]+ pid=f0 (.*)',text)
        if match:text=match[1]+'→'+match[2]+' '+match[3]
        return clock+' '+self.direction_of(row).upper()+' '+text[:512]
    @staticmethod
    def direction_of(row):
        value=row.get('direction')
        return 'rx' if value=='radio_to_host' else 'tx' if value in ('host_to_radio','host_to_radio_written') else '?'
    def selected_record(self):
        return next((r for r in self._all_records if self.identity(r)==self.selected),None)
    def update(self):
        data=self.provider() or {};self.metadata=data
        loader=data.get('history_page')
        # Changing devices must not mix their archives or reuse their cursors.
        if loader!=self._history_loader or data.get('history_device')!=self._history_device:
            self._history_loader=loader;self._history_device=data.get('history_device');self._history_rows=();self._history_cursor=None;self._history_more=True
            self._history_pending=None;self._source_token=None;self.history_error=''
        if self._history_pending is not None and self._history_pending.done():
            pending=self._history_pending;self._history_pending=None
            try:
                page=pending.result()
                if not isinstance(page,dict) or not isinstance(page.get('records'),list):raise ValueError('Invalid history page')
                rows=page['records']
                if len(rows)>200:raise ValueError('History page too large')
                cursor=page.get('before')
                if cursor is not None and (type(cursor) is not int or cursor<1):raise ValueError('Invalid history cursor')
                if type(page.get('more')) is not bool:raise ValueError('Invalid history page boundary')
                rows=[self.history_module.validate(row) for row in rows]
                self._history_cursor=page.get('before');self._history_more=page.get('more') is True
                unique={self.identity(r):r for r in self._history_rows}
                unique.update((self.identity(r),r) for r in rows)
                # Browsing is bounded separately from the live buffer and archive.
                self._history_rows=tuple(unique.values())[-self.browse_limit:]
                self._source_token=None;self.history_error=''
            except (OSError,ValueError,TypeError,KeyError) as error:self.history_error='History unavailable: '+str(error)

        token=data.get('records_revision',data.get('revision'))
        if token is None or token!=self._source_token:
            source=data.get('records') or data.get('evidence') or ()
            live=tuple(dict(r) for r in source[-self.history_limit:] if isinstance(r,dict))
            unique={self.identity(r):r for r in self._history_rows}
            unique.update((self.identity(r),r) for r in live)
            self._all_records=tuple(unique.values())
            self._source_token=token;self._token=token;self._view_token=None
        # A successful subscribed connection follows a validated snapshot in
        # console_source.Source. Error/disconnect alone never proves absence.
        authoritative=bool(data.get('subscribed') and data.get('connected') and not data.get('error'))
        waiting=self._restoring and not self._all_records and not authoritative
        view_token=(waiting,self._source_token,self.direction,self.oldest,time_display.ZONE)
        if view_token==self._view_token:return
        previous=self.selected
        if not self.oldest and self.rows and self.selected==self.identity(self.rows[0]) and self.list.offset==0 and not self._history_rows:previous=None
        latest=max(self._all_records,key=lambda r:time_display.epoch(r.get('time')) or float('-inf'),default={})
        shown=time_display.displayed(latest.get('time'));self._display_day=shown.date() if shown else None
        rows=[r for r in self._all_records if self.direction=='all' or self.direction_of(r)==self.direction]
        known=[(time_display.epoch(r.get('time')),i,r) for i,r in enumerate(rows)]
        timed=[item for item in known if item[0] is not None]
        timed.sort(key=lambda item:(item[0],item[1]),reverse=not self.oldest)
        unknown=[item for item in known if item[0] is None]
        self.rows=tuple(item[2] for item in timed+list(reversed(unknown) if not self.oldest else unknown))
        ids=tuple(self.identity(r) for r in self.rows)
        self.list.replace(tuple(self.compact(r) for r in self.rows),ids)
        retained=waiting or any(self.identity(r)==previous for r in self._all_records)
        if not waiting:self._restoring=False
        self.list.index=ids.index(previous) if previous in ids else -1 if retained else 0
        self.selected=previous if retained else ids[0] if ids else None
        self._view_token=view_token
        self._session_changed()
    def cycle_direction(self):
        modes=('all','rx','tx');self.direction=modes[(modes.index(self.direction)+1)%len(modes)];self.update()
    def choose(self):
        if not 0<=self.list.index<len(self.rows):return
        selected=self.identity(self.rows[self.list.index])
        if selected!=self.selected:self.scroll=0
        self.selected=selected;self._restoring=False
        self._session_changed()
    def load_older(self):
        if self._history_pending is not None or not self._history_more:return
        if self._history_loader is None:self.history_error='This connection does not provide packet history';return
        if self._history_pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self._history_pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='packet-history')
        anchor=min(self._all_records,key=lambda r:time_display.epoch(r.get('time')) or float('inf'),default=None) if self._history_cursor is None else None
        self._history_pending=self._history_pool.submit(self._history_loader,self._history_cursor,anchor=anchor)
        self.history_error=''
    def close(self):
        if self._history_pool is not None:self._history_pool.shutdown(wait=False,cancel_futures=True)

    def action(self,action_id):
        """One semantic path for Feed keys and buttons; no key injection."""
        if action_id not in ACTION_BY_ID:return False
        # Resize consumes these toolbar actions, just as the keyboard modal does.
        if self.resizing and action_id in ('feed.direction.cycle','feed.order.reverse','feed.evidence.toggle'):return True
        self.update()
        if action_id=='feed.direction.cycle':self.cycle_direction()
        elif action_id=='feed.order.reverse':self.oldest=not self.oldest;self.update()
        elif action_id=='feed.evidence.toggle':self.evidence=not self.evidence;self.scroll=0;self.layout.select('inspect')
        elif action_id=='feed.inspector.toggle':self.layout.select('inspect');self.layout.set_expanded(not self.layout.expanded);self.evidence=True
        elif action_id=='pane.restore':self.layout.set_expanded(False)
        elif action_id=='feed.older':self.load_older()
        elif action_id=='feed.latest':
            if self._history_pending is not None:self._history_pending.cancel()
            self._history_pending=None
            self.oldest=False;self._history_rows=();self._history_cursor=None;self._history_more=True
            self._source_token=None;self.update();self.list.index=0;self.choose()
        elif action_id in ('pane.next','pane.previous'):self.layout.cycle(-1 if action_id=='pane.previous' else 1)
        elif action_id=='pane.resize.begin':return self.layout.split_key('\x12',self.width)
        elif action_id=='feed.inspect.selection':self.layout.select('inspect');self.evidence=True;self.scroll=0
        elif action_id.startswith('scroll.'):
            if action_id=='scroll.first':self.scroll=0
            elif action_id=='scroll.last':self.scroll=self._detail_length
            else:self.scroll=max(0,self.scroll+(-1 if action_id.endswith('previous') else 1)*(8 if '.page.' in action_id else 1))
        elif action_id.startswith(('list.','search.')) and action_id in ACTION_BY_ID:
            edge=self.list.index==(0 if self.oldest else len(self.rows)-1)
            if edge and action_id in (('list.previous','list.page.previous') if self.oldest else ('list.next','list.page.next')):self.load_older()
            if not self.list.key(ACTION_BY_ID[action_id].keys[0]):return False
            self.choose()
        else:return False
        return True
    def key(self,key):
        self.update()
        if self.layout.resizing and self.layout.split_key(key,self.width):return True
        if self.layout.focus=='feed' and not self.resizing and self.list.search_key(key):
            self.choose();return True
        if key=='\x12' and self.list.searching:return False
        if key=='\x1b' and self.layout.expanded:return self.action('pane.restore')
        context='browse' if self.layout.focus=='feed' else 'inspect'
        action_id=KEY_ACTIONS.get((context,key))
        return self.action(action_id) if action_id is not None else False
    def details(self):
        row=self.selected_record()
        if row is None:return ['No record selected.']
        body=['Original record time: '+str(row.get('time') or 'unknown'),
              'Direction: '+str(row.get('direction') or 'unknown'),
              'Serial record; RF origin/delivery unverified','',self.describe(row),'']
        shown=time_display.displayed(row.get('time'))
        if shown:body.insert(1,'Display: '+shown.strftime('%Y-%m-%d %H:%M:%S %Z %z'))
        try:
            frame=bytes.fromhex(row['frame']);protocol=self.messages.classify_frame(frame)
            body+=['Protocol: '+protocol.upper(), 'KISS command at byte 0; AX.25 begins at 1' if protocol=='ax25' else 'Native/control bytes; not an AX.25 envelope','HEX + ASCII']
            if len(frame)>1024:body.append(f'Showing first 1024 of {len(frame)} bytes; original record retained')
            for at in range(0,min(1024,len(frame)),8):
                chunk=frame[at:at+8];body.append(f'{at:04x}  '+chunk.hex(' ').ljust(23)+'  '+''.join(chr(b) if 32<=b<127 else '.' for b in chunk))
        except (KeyError,ValueError,TypeError):body+=['Decoded text only; original bytes unavailable.']
        diagnostic=self.diagnostic(row)
        if diagnostic['raw_hex'] is not None and any(stage['stage']=='capture_hex' and stage['status']=='invalid' for stage in diagnostic['stages']):
            encoded=str(diagnostic['raw_hex']);body+=['Original frame field: '+encoded[:2048]]
            if len(encoded)>2048:body+=['Showing first 2048 characters; original retained']
        body+=['','Interpretation stages']
        if 'kiss_command' in diagnostic:body.append('KISS command '+str(diagnostic['kiss_command'])+' / port '+str(diagnostic['kiss_port']))
        for stage in diagnostic['stages']:body.append(stage['stage']+' · '+stage['status']+' · '+stage['reason'])
        if row.get('raw') and row['raw']!=self.describe(row):body+=['','Original monitor text',row['raw']]
        body+=['','Source: '+str(self.metadata.get('source') or 'unknown')]
        if self.metadata.get('error'):body+=['Connection: '+str(self.metadata['error'])]
        if row.get('capture') is not None:body+=['','Capture provenance',json.dumps(row['capture'],ensure_ascii=True)[:2000]]
        return body
    def inspect_identity(self,identity):
        if not any(self.identity(r)==identity for r in self._all_records):return
        self.selected=identity;self._restoring=False
        self._session_changed()
        ids=tuple(self.identity(r) for r in self.rows)
        self.list.index=ids.index(identity) if identity in ids else -1
        self.layout.select('inspect');self.scroll=0;self.evidence=True
    def entities_at(self,column,row):
        from entity_actions import EntityRef
        record=None
        for key,(x,y,w,h) in self._rects.items():
            if not(x<=column<x+w and y<row<y+h):continue
            if key=='feed':
                if self.list.has_scrollbar(w) and column==x+w-1:return ()
                index=self.list.offset+row-y-1
                if 0<=index<len(self.rows):record=self.rows[index]
            else:record=self.selected_record()
        return self.record_entities(record)
    def selected_entities(self):return self.record_entities(self.selected_record())
    def record_entities(self,record):
        from entity_actions import EntityRef
        if record is None:return ()
        identity=self.identity(record)
        refs=[EntityRef('observation',identity[1],dict(identity=identity,inspect=self.inspect_identity))]
        match=re.match(r'([A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?)>',self.describe(record))
        if match:refs.append(EntityRef('station',match[1]))
        return tuple(refs)
    def pointer(self,column,row,width,button=0,released=False):
        if self.layout.split_pointer(column,row,width,button,released,top=2,bottom=self.height-1):return True
        if released or button&32:return False
        for x,y,w,action in self._actions:
            if row==y and x<=column<x+w and button==0:self.action(action);return True
        for x,y,w,key in self._hits:
            if row==y and x<=column<x+w:self.layout.select(key);return True
        for key,(x,y,w,h) in self._rects.items():
            if x<=column<x+w and y<=row<y+h:
                if button&64:
                    if key=='feed':
                        if (button&1 and not self.oldest and self.list.offset+max(1,h-1)>=len(self.rows)) or (not button&1 and self.oldest and self.list.offset==0):self.load_older()
                        self.list.scroll(3 if button&1 else -3,max(1,h-1))
                    else:self.scroll=max(0,self.scroll+(1 if button&1 else -1))
                    return True
                if button!=0:return False
                self.layout.select(key)
                if key=='feed':
                    if self.list.pointer_at(column-x,row-y-1,w,max(1,h-1)):self.choose()
                return True
        return False
    @property
    def pointer_captured(self):return self.layout.pointer_captured
    @property
    def resizing(self):return self.layout.resizing
    def cancel_pointer(self):self.layout.cancel_pointer()
    def status_header(self):
        """Radio evidence and local service availability have separate owners."""
        link=self.metadata.get('radio_link') or {}
        reported=link.get('last_reported_connected')
        current=link.get('current_known') is True and link.get('freshness') in ('recent','current')
        if reported is False:
            radio='Radio: '+('disconnected' if current else 'last disconnected');role='warning'
        elif reported is True and current:radio='Radio: connected';role='status'
        elif reported is True:radio='Radio: unknown (last connected)';role='warning'
        else:radio='Radio: unknown';role='muted'
        if self.width>=72 and not current and reported is not None:
            radio+=' · '+('telemetry stale' if link.get('freshness')=='stale' else 'age unknown')
        service_label='' if self.metadata.get('connected') and not self.metadata.get('error') else 'Feed unavailable' if self.metadata.get('error') or not self.metadata.get('subscribed') else 'Connecting feed…'
        header=radio+(' · '+service_label if service_label else '')

        return header,radio,role,service_label
    def lines(self):
        self.update();c=Canvas(self.width,self.height);self._spans=[];self._hits=[];self._actions=[]
        header,radio_status,radio_role,service_status=self.status_header()
        latest=max((r for r in self._all_records if r.get('direction')=='radio_to_host'),
                   key=lambda r:time_display.epoch(r.get('time')) or float('-inf'),default={})
        header+=' · Last packet '
        stamp=time_display.epoch(latest.get('time'))
        if stamp is None:header+='none'
        else:
            age=max(0,int(time.time()-stamp))
            age_text=str(age)+'s' if age<60 else str(age//60)+'m' if age<3600 else str(age//3600)+'h' if age<86400 else str(age//86400)+'d'
            header+=age_text+' ago · '+time_display.day(latest.get('time'))+' '+time_display.clock(latest.get('time'))
        c.put(0,0,status_text(header,header+' · '+str(self.metadata.get('source') or 'Source unknown'),self.width))
        x=0
        for label,action in (('[f '+self.direction.upper()+']','feed.direction.cycle'),('[t Oldest]' if not self.oldest else '[t Newest]','feed.order.reverse'),('[e Raw]','feed.evidence.toggle'),('[o Older]','feed.older'),('[g Latest]','feed.latest')):
            c.put(x,1,label);self._actions.append((x,1,len(label),action));x+=len(label)+1
        rects=self.layout.layout(self.width,max(1,self.height-3));self._rects={k:(x,y+2,w,h) for k,(x,y,w,h) in rects.items()}
        if self.layout.tabbed:
            x=0
            for panel in self.layout.panels:
                label=('['+panel.title+']') if panel.key==self.layout.focus else panel.title
                c.put(x,2,label);self._hits.append((x,2,len(label),panel.key));x+=len(label)+2
        if not self.layout.tabbed:
            divider=self._rects['feed'][2]
            for y in range(2,self.height-1):c.put(divider,y,'│')
        for key,(x,y,w,h) in self._rects.items():
            c.pane(x,y,w,h,('Oldest first' if self.oldest else 'Newest first') if key=='feed' else 'Original evidence' if self.evidence else 'Packet details',key==self.layout.focus,inset=key=='feed')
            if key=='feed':
                self.list.draw(c,x,y+1,w,max(1,h-1))
                if self.list.visible_selection is not None:self._spans.append((y+1+self.list.visible_selection,x,w,'selected'))
            else:
                body=DetailBlock(w);row=self.selected_record()
                if row:
                    if self.evidence:
                        for line in self.details():body.text(line,'warning' if ' · invalid · ' in line else 'muted')
                    else:
                        body.section('Packet')
                        body.text(self.describe(row))
                        body.field('Direction',{'rx':'Radio → host','tx':'Host → radio'}.get(self.direction_of(row),'Unknown'))
                        body.field('Recorded',time_display.full(row.get('time')),'time')
                        body.text('')
                        body.text('e  '+ACTION_BY_ID['feed.evidence.toggle'].label,'control')
                    self._detail_length=len(body.lines);self.scroll=body.draw(c,x,y+1,w,max(1,h-1),self.scroll)
                else:c.put(x,y+1,'No record selected.',w)
        c.role(0,0,self.width,'muted')
        c.role(0,0,len(radio_status),radio_role)
        service_start=len(radio_status)+3
        c.role(service_start,0,len(service_status),'status' if self.metadata.get('connected') and not self.metadata.get('error') else 'warning' if self.metadata.get('error') else 'muted')
        c.role(0,1,self.width,'control');c.role(0,self.height-1,self.width,'muted')
        footer='←/→ resize split · Enter done · Esc cancel' if self.resizing else '/'+self.list.query if self.list.searching else self.history_error or ('Loading older packets…' if self._history_pending is not None else 'No older packets' if not self._history_more else '/ Find · Tab pane · Enter details')
        if self.selected and self.list.index<0:footer+=' · Selection hidden by filter'
        c.put(0,self.height-1,footer)
        self._spans=c.styled_spans(self._spans)
        return c.lines()
    def spans(self):return tuple(self._spans)
