"""Protocol-neutral conversation controls over the existing owner/provider contract."""
import hashlib
import textwrap
from app_widgets import AdaptivePanels,PanelSpec,Canvas,SelectList,TextInput


class ChatView:
    def __init__(self,provider,protocol):
        self.provider,self.protocol=provider,protocol
        self.width,self.height=84,25
        self.layout=AdaptivePanels((PanelSpec('threads','Contacts / channels',20,28),PanelSpec('chat','Conversation',30,60)))
        self.list=SelectList(());self.rows=[];self.selected=None;self.state={};self.drafts={};self.context=None
        self.editing=False;self.notice='';self.confirm=None;self.discovery=False;self.hits=[];self.rects={};self._spans=[];self.scroll=0;self.pending_drafts={}
    def refresh(self):
        state=self.provider.snapshot() if self.provider else {}
        context=(state.get('local_identity') or (state.get('public_card') or {}).get('identity'),getattr(self.provider,'label',None))
        if self.context!=context:self.selected=None;self.editing=False;self.context=context;self.confirm=None
        self.state=state
        job=state.get('last_job') or {}
        pending=self.pending_drafts.pop(job.get('id'),None) if job.get('state')=='failed' else None
        if pending:
            context,key,text=pending;editor=self.drafts.setdefault((context,key),TextInput(limit=240))
            if not editor.text:editor.text=text;editor.cursor=len(text)
            self.notice='Not confirmed: '+str(job.get('error','send failed'))+'; draft retained.'
        for message in state.get('messages',()):
            if message.get('state') not in ('queued','failed','unconfirmed'):
                self.pending_drafts.pop(message.get('id'),None)
        rows=[dict(p,key=('peer',p['identity'])) for p in state.get('peers',())]
        channels=[dict(c,key=('channel',c['index'])) for c in state.get('channels',())]
        rows=channels+rows if self.protocol=='meshcore' else rows+channels
        known={r['key'] for r in rows}
        for message in state.get('messages',()):
            key=('channel',message['channel']) if message.get('channel') is not None else ('peer',message.get('peer'))
            if key[1] and key not in known:
                rows.append(dict(key=key,label=str(key[1]),pinned=False));known.add(key)
        self.rows=rows
        keys=[r['key'] for r in rows]
        if self.selected not in keys:self.selected=keys[0] if keys else None
        self.list.replace(tuple(str(r.get('label') or r['key'][1])+(' · '+r.get('privacy','channel') if r['key'][0]=='channel' else ' ✓' if r.get('pinned') else ' · unverified') for r in rows),tuple(keys))
        if self.selected in keys:self.list.index=keys.index(self.selected)
    def row(self):return next((r for r in self.rows if r['key']==self.selected),{})
    def editor(self):return self.drafts.setdefault((self.context,self.selected),TextInput(limit=240 if self.protocol=='reticulum' else 160))
    def request(self,action,**payload):
        if not self.provider or action not in self.state.get('capabilities',()):self.notice='Action unavailable; connect the owner in Connections.';return False
        try:self.last_request=self.provider.request(action,payload);return True
        except (ValueError,OSError) as error:self.notice=str(error);return False
    def send(self):
        row=self.row();text=self.editor().text
        if len(self.pending_drafts)>=8:self.notice='Waiting for pending sends; inspect their status first.';return True
        if not self.selected or not text:return False
        if self.selected[0]=='peer':
            if not row.get('pinned'):self.notice='Compare and verify this peer first.';return True
            sent=self.request('send',peer=self.selected[1],text=text)
        else:sent=self.request('send_channel',channel=self.selected[1],text=text)
        if sent:
            if self.last_request:self.pending_drafts[self.last_request]=(self.context,self.selected,text)
            self.editor().text='';self.editor().cursor=0;self.editing=False;self.notice='Submitted; awaiting owner delivery status.'
        return True
    def choose(self):
        if self.rows:self.selected=self.rows[self.list.index]['key'];self.scroll=0
    def actions(self):
        pages=([('[','Prev contacts'),(']','Next contacts')] if self.protocol=='meshcore' and self.state.get('peers_total',0)>self.state.get('peers_page_size',32) else [])
        return pages+[('o','Connect'),('c','Compose'),('s','Send'),('v','Verify')]+([('d','Disconnect')] if self.protocol=='meshcore' else [('a','Hide presence' if self.state.get('message_discovery') else 'Discovery')])
    def key(self,key):
        self.refresh()
        if self.discovery:
            if key=='\x1b':self.discovery=False
            elif key.lower()=='y':
                if self.request('message_discovery',enabled=True):self.discovery=False
            return True
        if self.confirm:
            if key=='\x1b':self.confirm=None
            elif key.lower()=='y':
                if self.request('verify_peer',peer=self.confirm[0],fingerprint=self.confirm[1]):self.confirm=None
            return True
        if key=='\x13':return self.send()
        if self.editing:
            if key=='\x1b':self.editing=False
            elif key in ('\r','\n'):self.notice='Ctrl-S or Send submits; Enter keeps the draft.'
            else:return self.editor().key(key)
            return True
        if key in ('[',']') and self.protocol=='meshcore':
            size=self.state.get('peers_page_size',32);total=self.state.get('peers_total',0)
            offset=self.state.get('peers_offset',0)+(-size if key=='[' else size)
            offset=max(0,min(offset,max(0,((total-1)//size)*size)))
            self.request('contacts_page',offset=offset);return True
        if key=='a' and self.protocol=='reticulum':
            if self.state.get('message_discovery'):self.request('message_discovery',enabled=False)
            else:self.discovery=True
            return True
        if key=='c' and self.selected:self.editing=True;self.layout.select('chat');return True
        if key=='s':return self.send()
        if key=='v' and self.selected and self.selected[0]=='peer':
            row=self.row();keyvalue=row.get('public_key')
            if self.protocol=='reticulum' and keyvalue:
                digest=hashlib.sha256(bytes.fromhex(keyvalue)).hexdigest().upper();fingerprint=' '.join(digest[i:i+8] for i in range(0,64,8))
            elif self.protocol=='meshcore':fingerprint=self.selected[1]
            else:self.notice='Import this peer in Reticulum first.';return True
            self.confirm=(self.selected[1],fingerprint);return True
        if key=='o':
            if self.protocol=='meshcore':self.request('connect')
            else:
                radio=next(iter(self.state.get('radios',())),{})
                if radio:self.request('connect',station=radio['station_id'],radio=radio['radio_id'])
            return True
        if key=='d' and self.protocol=='meshcore':self.request('disconnect');return True
        if key in ('\t','backtab'):self.layout.cycle(-1 if key=='backtab' else 1);return True
        if self.layout.focus=='threads' and self.list.key(key):
            if self.rows:self.selected=self.rows[self.list.index]['key'];self.scroll=0
            return True
        if key in ('up','down','pageup','pagedown'):
            self.scroll=max(0,self.scroll+(1 if key in ('up','pageup') else -1)*(5 if 'page' in key else 1));return True
        return False
    def pointer(self,x,y,width,button=0,released=False):
        if button or released:return False
        for hx,hy,hw,key in self.hits:
            if y==hy and hx<=x<hx+hw:return self.key(key)
        for name,(px,py,w,h) in self.rects.items():
            if px<=x<px+w and py<=y<py+h:
                self.layout.select(name)
                if name=='threads' and self.list.pointer_at(x-px,y-py-1,w,max(1,h-1)) and self.rows:self.selected=self.rows[self.list.index]['key'];self.scroll=0
                elif name=='chat' and y==py+h-2:self.editing=True
                return True
        return False
    def prompt(self,lines):
        canvas=Canvas(self.width,self.height);self.hits=[]
        row=0
        for line in lines:
            for part in textwrap.wrap(line,self.width):
                if row>=self.height-2:break
                canvas.put(0,row,part);row+=1
        row=min(row+1,self.height-1)
        for x,label,key in ((0,'[Y Confirm]','y'),(14,'[Esc Cancel]','\x1b')):
            canvas.put(x,row,label);canvas.role(x,row,len(label),'control');self.hits.append((x,row,len(label),key))
        self._spans=canvas.styled_spans([]);return canvas.lines()
    def lines(self):
        self.refresh();canvas=Canvas(self.width,self.height);self.hits=[]
        if self.discovery:
            return self.prompt(('Publish messaging presence?', 'Reachable Reticulum nodes can discover this identity. Messages remain encrypted. Previously published routes cannot be recalled.'))
        if self.confirm:
            lines=['Compare the full fingerprint through a trusted channel:',self.confirm[1],'Y Verify · Esc Cancel']
            return self.prompt(lines[:2])
        controls=[(label,key) for key,label in self.actions()]
        x=0;y=0
        for label,key in controls:
            label='['+key.upper()+' '+label+']'
            if x+len(label)>self.width:x=0;y+=1
            canvas.put(x,y,label);canvas.role(x,y,len(label),'control');self.hits.append((x,y,len(label),key));x+=len(label)+1
        top=y+2;body=max(5,self.height-top-2)
        self.rects={k:(x,y+top,w,h) for k,(x,y,w,h) in self.layout.layout(self.width,body).items()}
        if self.layout.tabbed:
            canvas.put(0,top-1,'Tab: '+self.layout.focus+' / other pane')
        for name,(x,y,w,h) in self.rects.items():
            canvas.pane(x,y,w,h,(('Contacts '+str(self.state.get('peers_offset',0)+1)+'–'+str(min(self.state.get('peers_offset',0)+self.state.get('peers_page_size',32),self.state.get('peers_total',0)))+' / '+str(self.state['peers_total'])) if self.protocol=='meshcore' and self.state.get('peers_total') else 'Contacts / channels') if name=='threads' else str(self.row().get('label') or 'Conversation'),self.layout.focus==name)
            if name=='threads':self.list.draw(canvas,x,y+1,w,max(1,h-1))
            else:
                transcript=[]
                for message in self.state.get('messages',()):
                    key=('channel',message['channel']) if message.get('channel') is not None else ('peer',message.get('peer'))
                    if key!=self.selected:continue
                    outgoing=message.get('direction')=='tx'
                    sender='You' if outgoing else str(self.row().get('label') or message.get('peer') or 'Channel')
                    state=str(message.get('state','unknown'))
                    # Ordinary received/delivered messages need no repeated status row.
                    prefix=sender+': '
                    text=str(message.get('text',''))
                    transcript+=textwrap.wrap(prefix+text,max(1,w-2),subsequent_indent='  ') or ['']
                    if outgoing and state not in ('delivered','acknowledged'):
                        transcript.append('  '+state)
                    transcript.append('')
                visible=max(1,h-4);start=max(0,len(transcript)-visible-self.scroll)
                for dy,line in enumerate(transcript[start:start+visible]):canvas.put(x+1,y+1+dy,line,max(1,w-2))
                if self.selected:canvas.put(x+1,y+h-2,self.editor().draw(max(1,w-2)),max(1,w-2));canvas.role(x+1,y+h-2,max(1,w-2),'input')
        canvas.put(0,self.height-2,self.notice or self.state.get('error') or ('Connect an owner in Connections' if not self.state else 'Drafts stay local · Ctrl-S sends'))
        canvas.put(0,self.height-1,str(self.row().get('privacy') or ('Verified peer' if self.row().get('pinned') else 'Unverified peer')))
        self._spans=canvas.styled_spans([]);return canvas.lines()
    def spans(self):return tuple(self._spans)
