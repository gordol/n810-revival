#!/usr/bin/env python3
"""APRS inbox and explicit-send composer using the existing shared KISS broker."""
import argparse,curses,json,os,pathlib,re,select,socket,tempfile,textwrap,time
from importlib.util import spec_from_file_location,module_from_spec

from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
_runtime_spec=spec_from_file_location('messages_runtime',Path(__file__).with_name('n810-runtime.py'))
runtime=module_from_spec(_runtime_spec);_runtime_spec.loader.exec_module(runtime)
_style_spec=spec_from_file_location('radio_style',Path(__file__).with_name('n810-radio-style.py'))
style=module_from_spec(_style_spec);_style_spec.loader.exec_module(style)

_model_spec=spec_from_file_location('messages_model',Path(__file__).with_name('n810-messages-model.py'))
model=module_from_spec(_model_spec);_model_spec.loader.exec_module(model)
PACKET=model.PACKET
CALL=model.CALL
callsign=model.callsign
parse_message=model.parse_message
address=model.address
payload_for=model.payload_for
kiss_frame=model.kiss_frame
STORE=os.path.expanduser('~/.local/state/n810-aprs/messages.json')


def acquire_store(filename):
    """One cooperating legacy TUI or command owner writes this store at a time."""
    import fcntl
    target=pathlib.Path(filename);target.parent.mkdir(parents=True,exist_ok=True)
    lock=open(str(target)+'.owner-lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        lock.close();raise OSError('Messages store already has a writer')
    return lock


def save(rows,filename=STORE):
    target=pathlib.Path(filename);target.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=target.parent,prefix='.messages-')
    try:
        with os.fdopen(fd,'w') as f:json.dump(model.outbox_document(rows),f)
        os.replace(temp,target)
    finally:
        if os.path.exists(temp):os.unlink(temp)


class State(model.State):
    """TUI persistence adapter around the reusable message model."""
    def __init__(self,call,filename=STORE):
        super().__init__(call);self.store=filename
        try:data=json.loads(pathlib.Path(filename).read_text())
        except (OSError,ValueError,TypeError):data=None
        self.outbox=model.restore_outbox(data)


class Transport:
    def __init__(self,state,feed,duplex,path):
        self.state=state;self.feed_path=feed;self.duplex_path=duplex;self.path=path
        self.feed=None;self.tx=None;self.pending=b'';self.retry=0;self.queue=b'';self.job=None

    def submit(self,row):
        if row.get('protocol','aprs')!='aprs':raise ValueError('Only APRS submission is supported')
        if self.queue:raise ValueError('A submission is already in progress')
        if self.tx is None:
            candidate=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);candidate.settimeout(.5)
            try:
                candidate.connect(self.duplex_path)
                # The broker closes additional owners; check that rejection before writing.
                if select.select([candidate],[],[],.1)[0] and candidate.recv(4096)==b'':
                    raise OSError('Transmit socket is already in use')
            except BaseException:candidate.close();raise
            self.tx=candidate;self.tx.setblocking(False)
        self.queue=self.state.begin_submission(row,self.path)
        self.job=row

    def tick(self):
        changed=False
        if self.feed_path and self.feed is None and time.monotonic()>=self.retry:
            candidate=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);candidate.settimeout(.2)
            try:candidate.connect(self.feed_path)
            except OSError:candidate.close();self.retry=time.monotonic()+2;self.state.status='Feed unavailable - reconnecting'
            else:self.feed=candidate;self.feed.setblocking(False);self.pending=b'';self.state.status='Connected to feed'
            changed=True
        if self.feed is not None:
            try:data=self.feed.recv(8192)
            except BlockingIOError:data=None
            except OSError:data=b''
            if data==b'':self.feed.close();self.feed=None;self.retry=time.monotonic()+2;self.state.status='Feed disconnected - reconnecting';changed=True
            elif data:
                self.pending+=data;changed=True
                while b'\n' in self.pending:
                    line,self.pending=self.pending.split(b'\n',1);self.state.add(line.decode('utf-8','replace'))
        if self.tx is not None:
            try:
                data=self.tx.recv(8192)
                if not data:raise ConnectionError('Radio transmit connection closed')
            except BlockingIOError:pass
            except OSError:
                self.tx.close();self.tx=None
                if self.job:self.state.unconfirmed(self.job);self.job=None
                self.queue=b'';self.state.notice='Transmit connection closed; no automatic resend';changed=True
            if self.tx is not None and self.queue:
                try:n=self.tx.send(self.queue)
                except BlockingIOError:n=0
                except OSError:
                    self.tx.close();self.tx=None;n=0
                    self.state.unconfirmed(self.job);self.job=None;self.queue=b''
                    self.state.notice='Submission interrupted; delivery unknown';changed=True
                self.queue=self.queue[n:]
                if not self.queue and self.job:
                    self.state.submitted(self.job);self.job=None;changed=True
        return changed

    def close(self):
        if self.job:self.state.unconfirmed(self.job)
        for stream in (self.feed,self.tx):
            if stream is not None:stream.close()


def put(win,y,x,text,width,attr=0):
    h,w=win.getmaxyx()
    if 0<=y<h and 0<=x<w:
        try:win.addnstr(y,x,str(text),max(0,min(width,w-x-1)),attr)
        except curses.error:pass


def friendly(text):
    if 'Listening' in text or text.startswith('UV-PRO connected') or text.startswith('Radio settings unchanged'):return 'Radio connected'
    return text


def peer_label(value):
    return '<absent>' if value is None else '<empty>' if value=='' else value


def draw(win,state,tab,selected,compose,path,debug=False):
    h,w=win.getmaxyx();win.erase()
    put(win,0,1,'MESSAGES',w-2,curses.A_BOLD)
    labels = ['i Inbox (%d)' % len(state.rows(0)), 'e Heard (%d)' % len(state.received), 'o Outbox (%d)' % len(state.outbox)]
    if sum(len(label)+5 for label in labels) > w-1: labels=['i Inbox','e Heard','o Outbox']
    x=1
    for index,label in enumerate(labels):
        active=index==tab;edge,face=style.tab_styles(active)
        size=len(label)+2
        put(win,1,x,'┌'+'─'*size+'┐',w-x-1,edge)
        put(win,2,x,'│ '+label+' │',w-x-1,face)
        put(win,6,x,'+'+'-'*size+'+',w-x-1,edge)
        x+=size+3
    put(win,4,1,friendly(state.status),w-2)
    if compose is not None:
        put(win,6,1,'COMPOSE / '+compose['phase'].upper(),w-2,curses.A_BOLD)
        put(win,8,2,'To: '+compose['to'],w-4,curses.A_REVERSE if compose['field']==0 else 0)
        put(win,10,2,'Text (%d/67):'%len(compose['text']),w-4)
        for y,line in enumerate(textwrap.wrap(compose['text'],max(10,w-6)) or [''],11):put(win,y,3,line,w-6)
        put(win,h-7,2,'Path: '+(','.join(path) or 'direct'),w-4)
        put(win,h-6,2,'From: '+state.call,w-4)
        put(win,h-5,2,'APRS ID: '+(compose.get('id') or 'assigned when saved'),w-4)
        put(win,h-3,1,state.notice,w-2)
        if compose['phase']=='edit':
            put(win,h-2,1,'Tab next field │ Enter review │ Esc cancel',w-2)
            if compose['field']==0:cursor=(8,min(w-2,6+len(compose['to'])))
            else:cursor=(11,min(w-2,3+len(compose['text'])))
            try:win.move(*cursor);curses.curs_set(1)
            except curses.error:pass
        else:
            curses.curs_set(0)
            put(win,h-2,1,'s SEND over radio │ d save draft │ e edit │ Esc cancel',w-2,curses.A_BOLD)
        return
    curses.curs_set(0);rows=state.rows(tab);selected=min(selected,max(0,len(rows)-1))
    if debug and rows:
        row=rows[selected]
        lines=model.detail_lines(row,outgoing=tab==2,source=state.call,path=path)
        y=6
        for line in lines:
            for part in textwrap.wrap(line,max(10,w-4),replace_whitespace=False) or ['']:
                put(win,y,1,part,w-2);y+=1
                if y>=h-3:break
            if y>=h-3:break
        put(win,h-2,1,'x back │ q quit',w-2);return
    split=max(24,w//3)
    put(win,6,1,('INBOX','HEARD MESSAGES','OUTBOX / DRAFTS')[tab],split-2,curses.A_BOLD)
    visible=max(1,h-13);start=max(0,selected-visible+1)
    for y,(i,row) in enumerate(list(enumerate(rows))[start:start+visible],8):
        who=peer_label(row['to'] if tab==2 else row['source'])
        label=row['status'] if tab==2 else ('from '+who if tab==0 else who+' > '+peer_label(row['to']))
        prefix='[BSS] ' if row.get('protocol')=='bss' else ''
        put(win,y,1,prefix+str(row['time'] or 'time unknown')+' '+label,split-2,style.selection() if i==selected else 0)
    for y in range(6,h-5):put(win,y,split,'│',1)
    if rows:
        row=rows[selected];x=split+3
        put(win,6,x,('TO '+row['to']) if tab==2 else peer_label(row['source'])+' → '+peer_label(row['to']),w-x-2,curses.A_BOLD)
        put(win,8,x,('Status: '+row['status']) if tab==2 else ('BSS / receive only' if row.get('protocol')=='bss' else row['kind']),w-x-2)
        text=row['text'] or (row['kind']+' '+str(row['id'] if row['id'] is not None else 'absent'))
        for y,line in enumerate(textwrap.wrap(text,max(10,w-x-3)),10):put(win,y,x,line,w-x-2)
        put(win,h-7,x,'Message ID: '+str(row['id'] if row['id'] is not None and row['id']!='' else 'absent')+'  / attempts: '+str(row.get('attempts',0)),w-x-2)
        if tab==2 and row['status']=='Submitted':put(win,h-6,x,'Broker submission is not RF delivery confirmation.',w-x-2)
    else:put(win,9,split+3,'No messages here yet.',w-split-5)
    put(win,h-4,1,state.notice,w-2)
    put(win,h-3,1,'─'*(w-3),w-2)
    put(win,h-2,1,'n compose │ r reply/edit │ t retry │ x details │ a acknowledge │ j/k select │ v map │ q quit',w-2)
    put(win,h-1,1,'i/e/o tabs | h/l switch | g nets | no auto ACKs/retries',w-2)


def composer_request(path=None, now=None):
    """Consume a short-lived local navigation request, never a send command."""
    now=time.time() if now is None else now
    try:
        if path is None:
            request=runtime.read_json('n810-message-request.json')
            path=runtime.runtime_path('n810-message-request.json')
        else:
            with open(path) as stream:request=json.load(stream)
        recipient=request.get('to','')
        valid=isinstance(recipient,str) and re.fullmatch(r'[A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?',recipient)
        fresh=0 <= now-float(request.get('created',0)) <= 120
        os.unlink(path)
        return recipient if valid and fresh else None
    except (OSError,ValueError,TypeError,AttributeError):
        return None


def run(win,args):
    try:lock=acquire_store(args.store)
    except OSError as exc:raise SystemExit(str(exc)) from exc
    with lock:return run_owned(win,args)


def run_owned(win,args):
    style.init_screen(win)
    win.timeout(100);win.keypad(True)
    state=State(args.call,args.store);transport=Transport(state,args.socket,args.kiss,args.path)
    tab=0;selected=0;compose=None;dirty=True;size=None;debug=False;request_check=0
    def begin(to='',text='',kind='MSG',identifier=None):
        return dict(to=to,text=text,kind=kind,id=identifier,field=0 if not to else 1,phase='edit',original_to=to,original_text=text)
    try:
        while True:
            dirty=transport.tick() or dirty
            if compose is None and time.monotonic() >= request_check:
                request_check=time.monotonic()+.5
                recipient=composer_request()
                if recipient:
                    compose=begin(recipient)
                    state.notice='Directory recipient selected. Compose, review, then explicitly send.'
                    dirty=True
            if dirty or size!=win.getmaxyx():draw(win,state,tab,selected,compose,args.path,debug);win.refresh();dirty=False;size=win.getmaxyx()
            key=win.getch()
            if key==-1:continue
            dirty=True
            if compose is not None:
                if key==27:compose=None;state.notice='';continue
                if compose['phase']=='review':
                    if key==ord('e'):compose.pop('row',None);compose['phase']='edit';continue
                    if key in (ord('s'),ord('d')):
                        try:
                            row=compose.get('row')
                            if row is None:row=state.draft(compose['to'],compose['text'],compose['kind'],compose.get('id'))
                            if key==ord('s'):transport.submit(row)
                            else:save(state.outbox,state.store);state.notice='Draft saved'
                        except (ValueError,OSError) as exc:state.notice=str(exc);continue
                        compose=None;tab=2;selected=0
                    continue
                if key in (10,13,curses.KEY_ENTER):
                    try:
                        if compose['kind']=='MSG' and (compose['to']!=compose['original_to'] or compose['text']!=compose['original_text']):compose['id']=None
                        payload_for(compose['to'],compose['text'],compose.get('id') or 'TEST',compose['kind'])
                        compose['phase']='review';state.notice='Review recipient and text before sending'
                    except ValueError as exc:state.notice=str(exc)
                elif key==9:compose['field']=1-compose['field']
                elif key in (curses.KEY_BACKSPACE,127,8):
                    field='to' if compose['field']==0 else 'text';compose[field]=compose[field][:-1]
                elif 32<=key<=126 and compose['kind']=='MSG':
                    field='to' if compose['field']==0 else 'text';limit=9 if field=='to' else 67
                    if len(compose[field])<limit:compose[field]+=chr(key).upper() if field=='to' else chr(key)
                continue
            if key==ord('g'):
                spec=spec_from_file_location('ui_window',Path(__file__).with_name('n810-ui-window.py'))
                helper=module_from_spec(spec);spec.loader.exec_module(helper)
                try:helper.open_window('Nets')
                except (OSError,RuntimeError) as exc:state.notice=str(exc)
                continue
            if key in (ord('q'),27):break
            if key==ord('x'):debug=not debug;continue
            if debug:continue
            if key in (ord('1'),ord('2'),ord('3'),ord('i'),ord('e'),ord('o')):
                tab={ord('1'):0,ord('2'):1,ord('3'):2,ord('i'):0,ord('e'):1,ord('o'):2}[key];selected=0
            elif key in (ord('h'),curses.KEY_LEFT,ord('l'),curses.KEY_RIGHT,9):
                tab=(tab+(-1 if key in (ord('h'),curses.KEY_LEFT) else 1))%3;selected=0
            elif key in (ord('j'),curses.KEY_DOWN):selected=min(max(0,len(state.rows(tab))-1),selected+1)
            elif key in (ord('k'),curses.KEY_UP):selected=max(0,selected-1)
            elif key==ord('n'):compose=begin();state.notice=''
            elif key==ord('v'):
                try:
                    spec=spec_from_file_location('windows',os.path.join(os.path.dirname(__file__),'n810-ui-window.py'));module=module_from_spec(spec);spec.loader.exec_module(module);module.open_window('APRS')
                except (OSError,RuntimeError) as exc:state.notice=str(exc)
            elif key==ord('t'):
                rows=state.rows(tab)
                if tab!=2 or not rows:state.notice='Select an outbox message to retry';continue
                row=rows[min(selected,len(rows)-1)]
                if row['status'] in ('Acknowledged','Rejected','Submitting') or row['kind']!='MSG':
                    state.notice='This message does not need a retry';continue
                compose=begin(row['to'],row['text'],row['kind'],row['id'])
                compose['phase']='review';compose['row']=row
                state.notice='Retry: same text and message ID; s sends once'
            elif key in (ord('r'),ord('a')):
                rows=state.rows(tab)
                if not rows:continue
                row=rows[min(selected,len(rows)-1)]
                if row.get('protocol','aprs')!='aprs':
                    state.notice='BSS receive only; APRS reply/ACK does not apply';continue
                if key==ord('a'):
                    if tab==2 or row['to']!=state.call or row['kind']!='MSG' or not row['id']:state.notice='Select an addressed message with an ID';continue
                    compose=begin(row['source'],'','ACK',row['id']);compose['phase']='review'
                elif tab==2:
                    if row['status']=='Acknowledged':state.notice='Already acknowledged';continue
                    compose=begin(row['to'],row['text'],row['kind'],row['id'])
                else:compose=begin(row['source'])
    finally:
        transport.close();save(state.outbox,state.store)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--call',default='N0ANT')
    p.add_argument('--socket',default='/dev/shm/n810-aprs.sock');p.add_argument('--kiss',default='/dev/shm/n810-kiss.sock')
    p.add_argument('--path',default='WIDE1-1,WIDE2-1');p.add_argument('--store',default=STORE)
    args=p.parse_args();args.call=callsign(args.call);args.path=[callsign(c) for c in args.path.split(',') if c]
    if len(args.path)>2:p.error('At most two digipeaters')
    curses.wrapper(run,args)
