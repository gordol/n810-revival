"""Native Messages presentation. Inject original decoded RX; no transport or storage.

Messages(call).update(lines, call=None, outbox=None, records=None) accepts original
decoded APRS strings and a bounded raw BSS snapshot, oldest to newest. No
timestamp/capture reconstruction. Protocols have separate receive/thread state.
The composer is a per-peer, memory-only scratchpad: Enter never submits or saves.
"""
import importlib.util
from pathlib import Path
import textwrap
from app_widgets import AdaptivePanels, PanelSpec, Canvas, SelectList, TextInput


def load_model():
    here=Path(__file__).resolve().parent
    path=here/'vendor/packet-console/n810-messages-model.py'
    spec=importlib.util.spec_from_file_location('pocket_messages_model',path)
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    return model


class ReceiveMessages:
    def help_pages(self):
        from app_help_content import pages
        return pages('Messages')
    def __init__(self,call,model=None):
        self.model=model or load_model();self.state=self.model.State(call)
        self.bss=self.model.State(call);self.bss_input=None
        self.width=84;self.height=26;self.mode='inbox';self.selected=None
        self.peers=();self.list=SelectList(());self.scroll=0;self.drafts={}
        self.layout=AdaptivePanels((PanelSpec('threads','Conversations',22,30),PanelSpec('chat','Conversation',32,60)))
        self.composing=False;self.notice='Receive only · draft text stays in this window';self._detail_length=0
        self._spans=[];self._rects={};self._tabs=[];self.revision=0;self._groups_token=None;self.groups={};self._filter_hit=None
    def update(self,lines,call=None,outbox=None,records=None):
        """Feed original decoded lines and optional detached owner outbox snapshot.

        Outbox restoration uses owner restart semantics (Submitted becomes
        Unconfirmed); no injected owner row is mutated or submitted.
        """
        if call is not None and self.model.callsign(call)!=self.state.call:
            self.state=self.model.State(call);self.selected=None;self.scroll=0;self.drafts.clear();self.composing=False
            self.bss=self.model.State(call);self.bss_input=None
        before=(tuple(row['raw'] for row in self.state.received),self.model.outbox_document(self.state.outbox),tuple(self.bss.received))
        if outbox is not None:self.state.outbox=self.model.restore_outbox(dict(version=1,outbox=list(outbox)))
        # Providers own polling and history ordering. Keep input and model bounded.
        from collections import deque
        for line in deque(lines,maxlen=200):
            if isinstance(line,str):self.state.add(line)
        if records is not None:
            records=tuple(deque(records,maxlen=200))
            if records!=self.bss_input:
                # Replace the protocol-specific snapshot rather than replaying
                # unknown-time rows as newly received events on every redraw.
                bss=self.model.State(self.state.call)
                for record in records:
                    try:bss.add_record(record)
                    except (KeyError,TypeError,ValueError):continue
                self.bss=bss;self.bss_input=records
        changed=before!=(tuple(row['raw'] for row in self.state.received),self.model.outbox_document(self.state.outbox),tuple(self.bss.received))
        if changed:self.revision+=1
        self.sync()
        return changed
    @property
    def traffic(self):return 'mine' if self.mode=='inbox' else 'all'
    def bind_session(self,callback):
        self._session_callback=callback;self.layout.bind_session(callback)
    def session_state(self):return dict(traffic=self.traffic,panels=self.layout.session_state())
    def restore_session(self,state):
        if isinstance(state,dict) and state.get('traffic') in ('mine','all'):self.mode='inbox' if state['traffic']=='mine' else 'heard'
        if isinstance(state,dict):self.layout.restore_session(state.get('panels',{}))
    def rows(self):return [row for group in self.groups.values() for row in group['received']]
    @staticmethod
    def group_identity(group):
        return group['endpoints'][1] if group['protocol']=='aprs' and group['mine'] else tuple(group['key'])
    def label(self,peer):
        group=self.groups.get(peer)
        if group is None:return str(peer or 'Conversation')
        def endpoint(value):return '(unknown)' if value is None else '(empty)' if value=='' else str(value)
        pair=group['endpoints']
        label=endpoint(pair[1]) if group['mine'] and group['protocol']=='aprs' else endpoint(pair[0])+' → '+endpoint(pair[1])
        if 'unknown_source' in group['key']:label+=' · observation '+str(group['key'][-1]+1)
        return label+' · '+group['protocol'].upper()
    def is_bss(self):return self.groups.get(self.selected,{}).get('protocol')=='bss'
    def can_compose(self):return isinstance(self.selected,str) and self.groups.get(self.selected,{}).get('protocol')=='aprs' and self.groups[self.selected]['mine']
    def selected_entities(self):
        from entity_actions import EntityRef
        if getattr(self,'protocol','aprs')!='aprs':return ()
        group=self.groups.get(self.selected,{})
        if group.get('protocol')!='aprs':return ()
        endpoints=group.get('endpoints',())
        call=self.selected if self.can_compose() else endpoints[0] if endpoints else None
        return (EntityRef('station',call),) if isinstance(call,str) and call else ()
    def entities_at(self,column,row):
        rect=self._rects.get('chat')
        if rect:
            x,y,w,h=rect
            if x<=column<x+w and y<=row<y+h:return self.selected_entities()
        return ()
    def sync(self):
        token=(self.state.call,self.revision,self.mode)
        if token!=self._groups_token:
            # Each protocol retains its own original order; no invented common clock.
            groups=self.model.conversation_groups(self.state.call,self.state.received,self.state.outbox,traffic=self.traffic)
            groups+=self.model.conversation_groups(self.state.call,self.bss.received,traffic=self.traffic)
            self.groups={self.group_identity(group):group for group in groups};self.peers=tuple(self.groups)
            labels=[]
            for peer,group in self.groups.items():
                count=group['counts'];rows=group['received'] or group['outbox'];snippet=str(rows[0].get('text') or rows[0].get('kind') or '') if rows else ''
                status=' · '+str(group['outbox'][0].get('status') or 'Unknown') if group['outbox'] else ''
                labels.append(self.label(peer)+' '+str(count['received']+count['outbox'])+' · '+snippet+status)
            self.list.replace(tuple(labels),self.peers);self._groups_token=token
        if self.selected not in self.groups:self.selected=self.peers[0] if self.peers else None;self.scroll=0
        self.list.index=self.peers.index(self.selected) if self.selected in self.peers else 0
    def choose(self):
        peer=self.peers[self.list.index] if self.peers else None
        if peer!=self.selected:self.scroll=0
        self.selected=peer
    def composer(self):
        if not self.can_compose():return None
        return self.drafts.setdefault(self.selected,TextInput(limit=67))
    def key(self,key):
        self.sync()
        if not self.composing and (self.layout.resizing or key=='\x12' and not self.list.searching) and self.layout.split_key(key,self.width):return True
        if not self.composing and self.layout.focus=='threads' and self.list.search_key(key):
            self.choose();return True
        if key in ('\t','backtab'):
            self.layout.cycle(-1 if key=='backtab' else 1);self.composing=False
        elif self.composing:
            if key=='\x1b':self.composing=False
            elif key in ('\r','\n'):self.notice='Unsaved scratchpad · sending is unavailable'
            elif not self.composer().key(key):return False
        elif key=='c' and self.selected:
            if not self.can_compose():self.notice='BSS receive only · reply/ACK unavailable' if self.is_bss() else 'Observed traffic · read only';return True
            self.layout.select('chat');self.composing=True
        elif key in ('f','i','h'):
            previous=self.traffic
            self.mode=('heard' if self.mode=='inbox' else 'inbox') if key=='f' else 'inbox' if key=='i' else 'heard';self.composing=False;self.sync()
            if self.traffic!=previous and getattr(self,'_session_callback',None):self._session_callback()
        elif self.layout.focus=='threads' and self.list.key(key):self.choose()
        elif self.layout.focus=='chat' and key in ('up','down','j','k','pageup','pagedown','home','end'):
            if key=='home':self.scroll=0
            elif key=='end':self.scroll=self._detail_length
            else:self.scroll=max(0,self.scroll+(-1 if key in ('up','k','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1))
        elif key in ('\r','\n') and self.selected:self.layout.select('chat')
        else:return False
        return True
    def pointer(self,column,row,width,button=0,released=False):
        if self.layout.split_pointer(column,row,width,button,released,top=1,bottom=self.height-2):return True
        if released or button&32:return False
        if button==0 and self._filter_hit and row==0 and self._filter_hit[0]<=column<self._filter_hit[1]:return self.key('f')
        for x,y,w,key in self._tabs:
            if y==row and x<=column<x+w and button==0:self.layout.select(key);self.composing=False;return True
        for key,(x,y,w,h) in self._rects.items():
            if not(x<=column<x+w and y<=row<y+h):continue
            if button&64:
                if key=='threads':self.list.scroll(3 if button&1 else -3,max(1,h-1))
                else:self.scroll=max(0,self.scroll+(1 if button&1 else -1))
                return True
            if button!=0:return False
            self.layout.select(key)
            self.composing=key=='chat' and row==y+h-2 and self.can_compose()
            if key=='threads' and row>y and self.peers:
                if self.list.pointer_at(column-x,row-y-1,w,max(1,h-1)):self.choose()
            return True
        return False
    @property
    def pointer_captured(self):return self.layout.pointer_captured
    @property
    def resizing(self):return self.layout.resizing
    def cancel_pointer(self):self.layout.cancel_pointer()
    def transcript(self,width):
        if not self.selected:return ['No messages yet.','Received conversations appear here.']
        group=self.groups.get(self.selected,{})
        rows=group.get('received',[])
        lines=['Received · newest first',''] if rows else ['No received messages.','']
        for row in rows:
            # Only original time-of-day is available; no inferred date or delivery.
            if row.get('protocol')=='bss':
                destination='(destination absent)' if row['to'] is None else '(empty destination)' if row['to']=='' else row['to']
                lines.append('[BSS] '+(row['time'] or 'Time unknown'))
                lines.append(str(row['source'] if row['source'] is not None else '(source absent)')+' → '+destination)
            else:lines.append(row['time']+'  '+row['source']+' → '+row['to'])
            text=row['text'] if row['kind']=='MSG' else row['kind']+' '+row['id']+' (received evidence)'
            lines.extend('  '+s for s in textwrap.wrap(text,max(1,width-2)) or [''])
            if row.get('protocol')=='bss':
                lines.append('Message ID: '+('absent' if row['id'] is None else str(row['id'])))
                lines.extend('Raw: '+part if n==0 else '     '+part for n,part in enumerate(textwrap.wrap(row['raw_hex'],max(1,width-5))))
            lines.append('')
        outgoing=group.get('outbox',[])
        if outgoing:
            lines+=['Saved outbox · separate order','']
            for row in outgoing:
                lines.append(row['time']+'  To '+row['to']+' · '+row['status'])
                from aprs_internet import outgoing_evidence
                evidence=outgoing_evidence(self.state.call,row)
                if evidence:lines.extend(textwrap.wrap(evidence,max(1,width)))
                lines.extend('  '+s for s in textwrap.wrap(row['text'],max(1,width-2)) or [''])
                lines.append('')
        return lines
    def lines(self):
        self.sync();c=Canvas(self.width,self.height);self._spans=[];self._tabs=[]
        heading='Conversations · '+self.state.call;label='[f Mine]' if self.traffic=='mine' else '[f All observed]'
        c.put(0,0,heading);x=min(len(heading)+2,max(0,self.width-len(label)));c.put(x,0,label);c.role(x,0,len(label),'control');self._filter_hit=(x,x+len(label))
        self._spans.append((0,0,self.width,'toolbar'))
        bodyheight=max(1,self.height-3)
        raw=self.layout.layout(self.width,bodyheight)
        self._rects={k:(x,y+1,w,h) for k,(x,y,w,h) in raw.items()}
        if self.layout.tabbed:
            x=0
            for panel in self.layout.panels:
                title=('['+panel.title+']') if panel.key==self.layout.focus else panel.title
                c.put(x,1,title);self._tabs.append((x,1,len(title),panel.key));x+=len(title)+2
        for key,(x,y,w,h) in self._rects.items():
            title=('> ' if key==self.layout.focus else '')+('Conversations' if key=='threads' else self.label(self.selected) if self.selected is not None else 'Conversation')
            c.pane(x,y,w,h,title.lstrip('> '),key==self.layout.focus,inset=key=='threads')
            if key=='threads':
                self.list.draw(c,x,y+1,w,max(1,h-1))
                if self.list.visible_selection is not None:self._spans.append((y+1+self.list.visible_selection,x,w,'selected'))
                if not self.peers:c.put(x,y+2,'No conversations yet',w)
            else:
                visible=max(0,h-4);body=self.transcript(w);self._detail_length=len(body)
                # Keep logical scroll through resizes; clamp only the rendered view.
                offset=min(self.scroll,max(0,len(body)-visible))
                for n,line in enumerate(body[offset:offset+visible]):c.put(x,y+1+n,line,w)
                c.put(x,y+h-3,'BSS receive only · reply/ACK unavailable' if self.is_bss() else 'Scratchpad · unsaved · no sending' if self.can_compose() else 'Observed traffic · read only',w)
                editor=self.composer();c.put(x,y+h-2,(editor.draw(w) if editor else 'Native BSS record' if self.is_bss() else 'Observed endpoints; no composer' if self.selected else 'Select a conversation'),w)
                self._spans.append((y+h-2,x,w,'input' if self.composing else 'muted'))
        if not self.layout.tabbed:
            for x,y,w,h in list(self._rects.values())[:-1]:
                for row in range(y,y+h):c.put(x+w,row,'│')
        notice='Native BSS receive evidence · RF sender/delivery unverified' if self.is_bss() and self.notice=='Receive only · draft text stays in this window' else self.notice
        if self.traffic=='all' and self.selected and not self.groups[self.selected]['mine'] and notice in ('Receive only','Receive only · draft text stays in this window'):notice='All observed · endpoints retained · receive only'
        c.put(0,self.height-2,notice)
        c.put(0,self.height-1,'←/→ resize split · Enter done · Esc cancel' if self.layout.resizing else 'f Mine/All · Tab pane · Ctrl-R split · BSS receive only' if self.is_bss() else 'f Mine/All · Tab pane · Ctrl-R split · / find · c scratchpad')
        c.role(0,self.height-2,self.width,'muted');c.role(0,self.height-1,self.width,'muted')
        self._spans=c.styled_spans(self._spans)
        return c.lines()
    def spans(self):return tuple(self._spans)


class Messages(ReceiveMessages):
    """One Messages window; protocol-specific conversations retain their own identities."""
    def __init__(self,call,model=None,services=None):
        super().__init__(call,model)
        from chat_view import ChatView
        self.chat_services=services or {};self.protocol='aprs'
        self.chats={name:ChatView(self.chat_services.get(name),name) for name in ('reticulum','meshcore')}
    def navigation_layout(self):
        view=self.chats.get(self.protocol)
        return view.layout if view else self.layout
    def navigation_targets(self):
        from native_navigation import Target
        view=self.chats.get(self.protocol)
        actions=[('p','Protocol')]+(view.actions() if view else [('c','Compose local draft'),('f','Traffic filter')])
        return [Target('pane:'+p.key,p.title,'list' if p.key=='threads' else 'details') for p in self.navigation_layout().panels]+[Target('action:'+key,label,'action',key) for key,label in actions]
    def navigation_list(self,key):
        view=self.chats.get(self.protocol)
        return ((view.list,view.choose) if view else (self.list,self.choose)) if key=='pane:threads' else (None,None)
    def modal(self):
        view=self.chats.get(self.protocol)
        return bool(view.editing or view.confirm or view.discovery) if view else self.composing
    def navigation_modal_hint(self):
        view=self.chats.get(self.protocol)
        if view and (view.confirm or view.discovery):return ('Confirm','Y confirm · Esc cancel')
        return ('Draft','Ctrl-S sends · Tab focus · Esc back') if view else ('Local draft','Tab focus · Esc back · no transmission')
    def navigation_end_input(self):
        view=self.chats.get(self.protocol)
        if view:
            if view.confirm or view.discovery:return False
            view.editing=False
        else:self.composing=False
        return True
    def navigation_action_spans(self,key):
        if key=='p':return ((0,0,min(self.width,30),'input'),)
        view=self.chats.get(self.protocol)
        return tuple((y+1,x,w,'input') for x,y,w,action in view.hits if action==key) if view else ()
    def readiness_sources(self):
        provider=self.chat_services.get(self.protocol)
        if provider is None:return ()
        if hasattr(provider,'readiness_sources'):return provider.readiness_sources(self.chat_ready)
        if getattr(provider,'readable',None) is not None:return ((provider.readable,self.chat_ready),)
        return ()
    def chat_ready(self):
        provider=self.chat_services.get(self.protocol)
        if provider:provider.drain()
    def key(self,key):
        view=self.chats.get(self.protocol)
        if key=='p' and not ((view.editing or view.confirm or view.discovery) if view else self.composing):
            modes=('aprs','reticulum','meshcore');self.protocol=modes[(modes.index(self.protocol)+1)%3]
            if getattr(self,'_session_callback',None):self._session_callback()
            return True
        return view.key(key) if view else super().key(key)
    def lines(self):
        view=self.chats.get(self.protocol)
        if view:
            view.width,view.height=self.width,max(8,self.height-1)
            rows=view.lines()
        else:
            old=self.height;self.height=max(8,old-1)
            try:rows=super().lines()
            finally:self.height=old
        return [(' [P Protocol: '+self.protocol.upper()+']')[:self.width]]+list(rows[:self.height-1])
    def pointer(self,column,row,width,button=0,released=False):
        if row==0 and button==0 and not released:return self.key('p')
        view=self.chats.get(self.protocol)
        return view.pointer(column,row-1,width,button,released) if view else super().pointer(column,row-1,width,button,released)
    def spans(self):
        view=self.chats.get(self.protocol)
        spans=view.spans() if view else super().spans()
        return ((0,0,min(self.width,30),'control'),)+tuple((y+1,x,w,role) for y,x,w,role in spans)
    def session_state(self):return dict(super().session_state(),protocol=self.protocol)
    def restore_session(self,state):
        super().restore_session(state)
        if isinstance(state,dict) and state.get('protocol') in ('aprs','reticulum','meshcore'):self.protocol=state['protocol']
