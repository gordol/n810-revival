"""MeshCore companion owner: official binary client, explicit connect, no automatic TX."""
import argparse
import hashlib
import os
from pathlib import Path
import queue
import re
import signal
import sys
import tempfile
import threading
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'reticulum'))
# Import by filename because this executable is also named owner.py.
import importlib.util
_spec=importlib.util.spec_from_file_location('pocket_station_owner',Path(__file__).resolve().parents[1]/'reticulum/owner.py')
_station=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_station)
from wire import encode,decode,LIMIT
_history_spec=importlib.util.spec_from_file_location('pocket_meshcore_history',Path(__file__).with_name('history.py'))
_history=importlib.util.module_from_spec(_history_spec);_history_spec.loader.exec_module(_history)

MAX_CONTACTS=512
MAX_LABEL_BYTES=96
MAX_MESSAGE_BYTES=512
_PUBLIC_KEY=re.compile(r'[0-9a-fA-F]{64}')
_PREFIX=re.compile(r'[0-9a-fA-F]{12}')


def bounded_text(value,limit):
    text=''.join(char if char.isprintable() else '?' for char in str(value))
    return text.encode('utf-8')[:limit].decode('utf-8',errors='ignore')


def public_key(value):
    return value.lower() if isinstance(value,str) and _PUBLIC_KEY.fullmatch(value) else ''


class MeshOwner(_station.Owner):
    def __init__(self,state,station,port,baudrate=115200,trusted_peripheral=False,client_factory=None):
        super().__init__(state,station)
        self.port,self.baudrate,self.trusted_peripheral=port,baudrate,trusted_peripheral
        self.client_factory=client_factory
        self.bridge={}
        self.online=False;self.phase='idle';self.error='';self.peers=[];self.ambiguous=set();self.channels=[];self.messages=[];self.pins=[]
        self.peer_offset=0;self.receive_error='';self.unsaved_receive=None
        self.local_identity='';self.fetch_pending=False;self.pending={};self.early_acks=set();self.client=None
        self.storage=Path(state)/'chat.msgpack'
        if self.storage.exists():
            info=self.storage.lstat()
            if self.storage.is_symlink() or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>LIMIT:raise ValueError('Unsafe chat store')
            saved=decode(self.storage.read_bytes());self.pins=saved.get('pins',[])[:64];self.messages=saved.get('messages',[])[-32:]
            for row in self.messages:
                if row.get('state') in ('queued','sent'):row['state']='unconfirmed after restart'
        self.history=_history.History(Path(state)/'messages.sqlite3')
        for row in self.messages:self.history.put(row,replace=False)
        self.messages=self.history.latest()
        for row in self.messages:
            if row.get('state') in ('queued','sent'):
                row['state']='unconfirmed after restart';self.history.put(row)
        self.commands=queue.Queue(maxsize=8)
        self.events=queue.Queue(maxsize=256)
        self.stopping=threading.Event();self.loop=None;self.kick=None
        self.worker=None
        self.configure_connection_recovery(lambda:dict(station=self.station,port=self.port,
            baudrate=self.baudrate,trusted_peripheral=self.trusted_peripheral),{})

    def capabilities(self):
        caps=['connect','disconnect'] if self.phase=='error' else ['connect'] if self.phase=='idle' else ['disconnect']
        if self.online:caps+=['send','send_channel','verify_peer','refresh','contacts_page']
        return caps

    def snapshot(self):
        return self.bounded_snapshot()[0]

    def snapshot_frame(self):
        return self.bounded_snapshot()[1]

    def bounded_snapshot(self):
        peers=[dict(p,pinned=p['identity'] in self.pins) for p in self.peers[self.peer_offset:self.peer_offset+32]]
        state=dict(version=1,station_id=self.station,owner_online=True,protocol='meshcore',service_type='meshcore-companion',
                   bridge=dict(self.bridge),port=self.port,baudrate=self.baudrate,trusted_peripheral=self.trusted_peripheral,
                   revision=self.revision,local_identity=self.local_identity,capabilities=self.capabilities(),peers=peers,channels=self.channels,
                   peers_total=len(self.peers),peers_offset=self.peer_offset,peers_page_size=32,
                   messages=list(self.messages),last_job=self.last_job,error=self.error,connection_state=self.phase,
                   device_link_security='trusted peripheral; serial is not encrypted')
        while True:
            try:return state,encode(state)
            except ValueError:
                if state['messages']:state['messages'].pop(0)
                elif state['peers']:state['peers'].pop()
                else:raise

    def save(self):
        raw=encode(dict(version=1,pins=self.pins,messages=self.messages[-32:]))
        fd,name=tempfile.mkstemp(dir=self.storage.parent,prefix='.chat-')
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(raw);stream.flush();os.fsync(stream.fileno())
            os.replace(name,self.storage)
        finally:
            if os.path.exists(name):os.unlink(name)

    def dispatch(self,request):
        if not isinstance(request,dict) or type(request.get('version')) is not int or request['version']!=1:raise ValueError('Invalid owner request')
        action=request.get('action');payload=request.get('payload',{})
        if action=='snapshot':return self.snapshot()
        if not isinstance(payload,dict) or action not in self.capabilities():raise ValueError('Operation unavailable')
        if action=='contacts_page':
            offset=payload.get('offset')
            if type(offset) is not int or offset<0 or offset>=max(1,len(self.peers)):raise ValueError('Invalid contacts page')
            self.peer_offset=offset;self.revision+=1
            return dict(version=1,offset=offset)
        if action=='verify_peer':
            peer=payload.get('peer');fingerprint=payload.get('fingerprint')
            if not any(p['identity']==peer for p in self.peers) or fingerprint!=peer:raise ValueError('Compare the full MeshCore public key')
            if peer not in self.pins:
                if len(self.pins)>=64:raise ValueError('Verified contact limit reached')
                self.pins.append(peer);self.save();self.revision+=1
            return dict(version=1,verified=True)
        if action=='connect' and not self.trusted_peripheral:raise ValueError('MeshCore serial is cleartext to the attached radio; explicitly configure trusted_peripheral for a physically trusted device')
        if action in ('send','send_channel'):
            text=payload.get('text')
            if not isinstance(text,str) or not 1<=len(text.encode())<=160 or not text.isprintable():raise ValueError('Message must contain 1–160 printable UTF-8 bytes')
            if action=='send' and str(payload.get('peer',''))[:12] in self.ambiguous:raise ValueError('Ambiguous MeshCore key prefix; refusing send')
            if action=='send' and (payload.get('peer') not in self.pins or not any(p['identity']==payload['peer'] for p in self.peers)):raise ValueError('Verify the full peer key before sending')
            if action=='send_channel' and not any(c['index']==payload.get('channel') for c in self.channels):raise ValueError('Select an existing channel')
        identifier=request.get('request_id')
        if not isinstance(identifier,str) or not identifier:raise ValueError('Request identity required')
        try:self.commands.put_nowait((action,dict(payload),identifier))
        except queue.Full:raise ValueError('MeshCore command queue full') from None
        if action in ('connect','disconnect'):self.connection_requested(action=='connect')
        if action=='connect':self.phase='opening'
        self._start_worker()
        if self.loop and self.kick:self.loop.call_soon_threadsafe(self.kick.set)
        self.revision+=1
        return dict(version=1,job=dict(id=identifier,state='queued'))

    def receive(self,event):
        from meshcore import EventType
        data=event.payload
        if not isinstance(data,dict):return
        if event.type==EventType.ACK:
            code=data.get('code')
            if not isinstance(code,str) or not re.fullmatch(r'[0-9a-fA-F]{8}',code):return
            code=code.lower();identifier=self.pending.pop(code,None)
            if identifier:self.post(dict(kind='delivery',id=identifier,state='acknowledged'))
            else:
                if len(self.early_acks)>=64:self.early_acks.clear()
                self.early_acks.add(code)
        elif event.type in (EventType.CONTACT_MSG_RECV,EventType.CHANNEL_MSG_RECV):
            prefix=data.get('pubkey_prefix','')
            prefix=prefix.lower() if isinstance(prefix,str) and _PREFIX.fullmatch(prefix) else ''
            matches=[p['identity'] for p in self.peers if prefix and p['identity'].startswith(prefix)]
            peer=matches[0] if len(matches)==1 else 'unresolved:'+prefix
            channel=data.get('channel_idx') if event.type==EventType.CHANNEL_MSG_RECV else None
            if type(channel) is not int or not 0<=channel<40:channel=None
            timestamp=data.get('sender_timestamp')
            if type(timestamp) is not int or not 0<=timestamp<=0xffffffff:timestamp=None
            row=dict(direction='rx',peer=peer,channel=channel,text=bounded_text(data.get('text',''),MAX_MESSAGE_BYTES),
                     timestamp=timestamp,state='received',sender_verified=channel is None and peer in self.pins)
            row['id']=hashlib.sha256(encode(dict(version=1,**row))).hexdigest()
            try:
                self.history.put(row)
            except Exception as error:
                self.unsaved_receive=row
                self.receive_error='Message storage failed; automatic retrieval stopped: '+str(error)[:120]
                self.fetch_pending=False
                return
            self.post(dict(kind='message',row=row))

    async def refresh(self):
        from meshcore import EventType
        result=await self.client.commands.get_contacts(timeout=60)
        if result is None or result.type==EventType.ERROR:raise ValueError('Contact query failed')
        if not isinstance(result.payload,dict) or len(result.payload)>MAX_CONTACTS:raise ValueError('Invalid contact list')
        from collections import Counter
        contacts=[]
        for identity,value in result.payload.items():
            identity=public_key(identity)
            if not identity or not isinstance(value,dict):continue
            contacts.append(dict(identity=identity,label=bounded_text(value.get('adv_name') or identity,MAX_LABEL_BYTES),type=value.get('type')))
        self.ambiguous={p for p,n in Counter(row['identity'][:12] for row in contacts).items() if n>1}
        self.peers=contacts
        self.peer_offset=min(self.peer_offset,max(0,((len(self.peers)-1)//32)*32))
        info=await self.client.commands.send_device_query()
        device=info.payload if info and info.type!=EventType.ERROR and isinstance(info.payload,dict) else {}
        maximum=device.get('max_channels',0)
        if type(maximum) is not int:maximum=0
        self.channels=[]
        for index in range(max(0,min(40,maximum))):
            channel=await self.client.commands.get_channel(index)
            if channel and channel.type==EventType.CHANNEL_INFO and isinstance(channel.payload,dict) and channel.payload.get('channel_name'):
                data=channel.payload
                name=bounded_text(data['channel_name'],MAX_LABEL_BYTES);secret=data.get('channel_secret',b'')
                if not isinstance(secret,bytes) or len(secret)!=16:secret=b''
                public=secret in (b'\0'*16,bytes.fromhex('8b3387e9c5cdea6ac9e5edbaa115cd72')) or name.startswith('#')
                self.channels.append(dict(index=index,label=name,privacy='public' if public else 'shared key; members may impersonate names'))
        self.post(dict(kind='ready'))

    def _start_worker(self):
        if self.worker is None:
            self.worker=threading.Thread(target=self._work,daemon=True,name='meshcore-owner')
            self.worker.start()

    def _work(self):
        import asyncio
        asyncio.run(self.run())

    async def run(self):
        import asyncio
        self.loop=asyncio.get_running_loop();self.task=asyncio.current_task();self.kick=asyncio.Event()
        try:
            while not self.stopping.is_set():
                try:action,payload,identifier=self.commands.get_nowait()
                except queue.Empty:
                    if self.fetch_pending and self.client:action,payload,identifier='fetch',{},'receive'
                    else:
                        self.kick.clear()
                        if not self.commands.empty():continue
                        await self.kick.wait();continue
                try:
                    if action=='connect':
                        if self.unsaved_receive:
                            self.history.put(self.unsaved_receive)
                            self.post(dict(kind='message',row=self.unsaved_receive))
                            self.unsaved_receive=None
                        self.receive_error=''
                        if self.client:await self.client.disconnect();self.client=None
                        if self.client_factory:
                            factory=self.client_factory
                        else:
                            spec=importlib.util.spec_from_file_location('pocket_meshcore_serial_client',Path(__file__).with_name('serial_client.py'))
                            adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
                            factory=adapter.create_serial_client
                        options=dict(auto_reconnect=False,default_timeout=5)
                        if not self.client_factory:
                            def bridge_changed(status):
                                self.bridge=status
                                self.post(dict(kind='bridge_status'))
                            options['bridge_status_callback']=bridge_changed
                        self.client=await factory(self.port,self.baudrate,**options)
                        if self.client is None:raise ValueError('No MeshCore companion response')
                        from meshcore import EventType
                        self.local_identity=public_key(self.client.self_info.get('public_key',''))
                        for event in (EventType.ACK,EventType.CONTACT_MSG_RECV,EventType.CHANNEL_MSG_RECV):self.client.subscribe(event,self.receive)
                        def waiting(event):
                            if not self.receive_error:self.fetch_pending=True;self.kick.set()
                        self.client.subscribe(EventType.MESSAGES_WAITING,waiting)
                        def disconnected(event):
                            self.online=False;self.phase='idle';self.fetch_pending=False
                            for pending in self.pending.values():self.post(dict(kind='delivery',id=pending,state='unconfirmed'))
                            self.pending.clear();self.early_acks.clear()
                            self.post(dict(kind='job',action='disconnect',state='complete',reason=str(event.payload.get('reason',''))))
                        self.client.subscribe(EventType.DISCONNECTED,disconnected)
                        await self.refresh();self.fetch_pending=True
                        self.online=True;self.phase='online';self.error=''
                    elif action=='disconnect':
                        if self.client:await self.client.disconnect()
                        self.client=None;self.online=False;self.phase='idle'
                        for pending in self.pending.values():self.post(dict(kind='delivery',id=pending,state='unconfirmed'))
                        self.pending.clear()
                    elif action=='refresh':await self.refresh()
                    elif action=='fetch':
                        from meshcore import EventType
                        result=await self.client.commands.get_msg()
                        if self.receive_error:
                            self.fetch_pending=False
                            raise OSError(self.receive_error)
                        self.fetch_pending=bool(result and result.type not in (EventType.NO_MORE_MSGS,EventType.ERROR))
                    else:
                        from meshcore import EventType
                        row=dict(id=identifier,direction='tx',peer=payload.get('peer'),channel=payload.get('channel'),
                                 text=payload['text'],timestamp=int(time.time()),state='queued')
                        self.post(dict(kind='message',row=row))
                        result=await (self.client.commands.send_msg(payload['peer'],payload['text'],timestamp=row['timestamp']) if action=='send'
                                      else self.client.commands.send_chan_msg(payload['channel'],payload['text'],timestamp=row['timestamp']))
                        if result is None:raise ValueError('Send timed out; outcome unknown; not retried')
                        if result.type==EventType.ERROR:raise ValueError('Radio rejected message: '+str(result.payload))
                        code=result.payload.get('expected_ack',b'');code=code.hex() if isinstance(code,bytes) else code
                        status='sent; no group receipt' if action=='send_channel' else 'sent'
                        if action=='send':
                            if code in self.early_acks:self.early_acks.discard(code);status='acknowledged'
                            else:
                                if not code or code in self.pending:
                                    previous=self.pending.pop(code,None)
                                    if previous:self.post(dict(kind='delivery',id=previous,state='unconfirmed'))
                                    status='unconfirmed'
                                else:
                                    if len(self.pending)>=32:
                                        previous=self.pending.pop(next(iter(self.pending)))
                                        self.post(dict(kind='delivery',id=previous,state='unconfirmed'))
                                    self.pending[code]=identifier
                        self.post(dict(kind='delivery',id=identifier,state=status))
                    if action!='fetch':self.post(dict(kind='job',id=identifier,action=action,state='complete'))
                except Exception as error:
                    if action=='fetch':self.fetch_pending=False
                    if action=='connect' or (action=='fetch' and self.receive_error):
                        if self.client:await self.client.disconnect()
                        self.client=None;self.online=False;self.phase='error';self.fetch_pending=False
                    self.error=str(error)[:240]
                    self.post(dict(kind='job',id=identifier,action=action,state='failed',error=self.error))
                    if action in ('send','send_channel'):self.post(dict(kind='delivery',id=identifier,state='unconfirmed',error=self.error))
        except asyncio.CancelledError:pass
        finally:
            if self.client:await self.client.disconnect()

    def drain(self):
        changed=False
        while True:
            try:event=self.events.get_nowait()
            except queue.Empty:break
            kind=event.get('kind')
            if kind=='message':
                row=event['row']
                self.history.put(row)
                if not any(r['id']==row['id'] for r in self.messages):self.messages.append(row);self.messages=self.messages[-32:];changed=True
            elif kind=='delivery':
                for row in self.messages:
                    if row['id']==event['id']:
                        row.update({k:v for k,v in event.items() if k not in ('kind','id')});self.history.put(row);changed=True
            elif kind=='job':self.last_job=event
            self.revision+=1
        if changed:self.save()

    def close(self):
        self.stop_connection_recovery()
        self.stopping.set()
        if self.loop and self.kick:self.loop.call_soon_threadsafe(self.task.cancel)
        if self.worker is not None:
            self.worker.join(15)
            if self.worker.is_alive():raise RuntimeError('MeshCore shutdown did not complete')
        self.drain()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('socket','state','station','port'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--baudrate',type=int,default=115200);parser.add_argument('--trusted-peripheral',action='store_true')
    parser.add_argument('--ready-fd',type=int)
    args=parser.parse_args()
    def stop(*_):raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    _station.serve(args.socket,args.state,args.station,lambda state,station:MeshOwner(state,station,args.port,args.baudrate,args.trusted_peripheral),ready_fd=args.ready_fd)

if __name__=='__main__':main()
