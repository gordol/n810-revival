#!/usr/bin/env python3
"""Reviewed, one-shot APRS command owner. Importing never starts a service."""
import copy
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import secrets
import time

_spec=importlib.util.spec_from_file_location('owner_messages_model',Path(__file__).with_name('n810-messages-model.py'))
model=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(model)

class Owner:
    def __init__(self,state,station_id,radio_id,persist,submit,allow_send=False,ready=lambda:False,clock=time.time):
        if not all(isinstance(v,str) and 1<=len(v)<=64 for v in (station_id,radio_id)):raise ValueError('Station and radio identities required')
        self.state=state;self.station_id=station_id;self.radio_id=radio_id
        self.persist=persist;self.submit=submit;self.allow_send=allow_send;self.ready=ready;self.clock=clock
        self.reviews={};self.responses={};self.revision=0

    def capability(self):
        return dict(station_id=self.station_id,radio_id=self.radio_id,source=self.state.call,
                    protocol='aprs',message_kinds=['MSG'],send_enabled=bool(self.allow_send and self.ready()),
                    automatic_retries=False,bss_send=False)

    def snapshot(self):
        return dict(capability=self.capability(),revision=self.revision,
                    outbox=copy.deepcopy(self.state.outbox))

    def changed(self):
        self.persist(self.state.outbox);self.revision+=1

    def row(self,request):
        if not isinstance(request.get('draft_id'),str) or type(request.get('expected_revision')) is not int:raise ValueError('Draft identity and revision required')
        row=next((r for r in self.state.outbox if r.get('draft_id')==request['draft_id']),None)
        if row is None or row.get('station_id')!=self.station_id or row.get('radio_id')!=self.radio_id:raise ValueError('Draft not found for this station/radio')
        if request.get('expected_revision')!=row.get('revision'):raise ValueError('Draft revision conflict')
        return row

    def handle(self,request):
        request_id=request.get('request_id') if isinstance(request,dict) else None
        if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',request_id):
            return dict(version=1,request_id=request_id,ok=False,error='Valid request_id required')
        try:
            if request.get('version',1)!=1:raise ValueError('Unsupported contract version')
            action=request.get('action')
            if action=='snapshot':return dict(version=1,request_id=request_id,ok=True,**self.snapshot())
            fingerprint=hashlib.sha256(json.dumps(request,sort_keys=True).encode()).hexdigest()
            if request_id in self.responses:
                prior_hash,result=self.responses[request_id]
                if fingerprint!=prior_hash:raise ValueError('Request ID reused with different content')
                return copy.deepcopy(result)
            # Persisted intent prevents a lost reply/restarted client causing a resend.
            previous=next((r for r in self.state.outbox if r.get('command_id')==request_id),None)
            if previous:
                if previous.get('command_fingerprint')!=fingerprint:raise ValueError('Request ID conflict')
                return dict(version=1,request_id=request_id,ok=True,duplicate=True,row=copy.deepcopy(previous))
            if action=='draft.save':result=self.save_draft(request)
            elif action=='review':result=self.review(request)
            elif action=='send':result=self.send(request,fingerprint)
            else:raise ValueError('Unsupported command')
            response=dict(version=1,request_id=request_id,ok=True,**result)
            self.responses[request_id]=(fingerprint,copy.deepcopy(response))
            while len(self.responses)>256:del self.responses[next(iter(self.responses))]
            return response
        except (ValueError,OSError,TypeError,KeyError,AttributeError) as exc:
            return dict(version=1,request_id=request_id,ok=False,error=str(exc))

    def save_draft(self,request):
        if request.get('protocol','aprs')!='aprs' or request.get('kind','MSG')!='MSG':raise ValueError('Only APRS text message composition supported')
        if request.get('source')!=self.state.call:raise ValueError('Source differs from owner identity')
        if not isinstance(request.get('path',[]),list):raise ValueError('Path must be a list')
        if not isinstance(request.get('to'),str) or not isinstance(request.get('text'),str):raise ValueError('Recipient and text required')
        path=[model.callsign(c) for c in request.get('path',[])]
        if len(path)>2:raise ValueError('At most two digipeaters')
        to=model.callsign(request['to']);text=request['text']
        if request.get('draft_id'):
            row=self.row(request)
            if row['status']!='Draft':raise ValueError('Create a new draft for a new attempt')
            identifier=row['id'] if (row['to'],row['text'])==(to,text) else secrets.token_hex(2).upper()
            model.payload_for(to,text,identifier)
            row.update(to=to,text=text,id=identifier,path=path,revision=row['revision']+1)
        else:
            used={r['id'] for r in self.state.outbox}
            identifier=secrets.token_hex(2).upper()
            while identifier in used:identifier=secrets.token_hex(2).upper()
            row=self.state.draft(to,text,identifier=identifier)
            row.update(draft_id=secrets.token_hex(16),revision=1,path=path,protocol='aprs',source=self.state.call,
                       station_id=self.station_id,radio_id=self.radio_id)
        self.changed()
        return dict(row=copy.deepcopy(row))

    def review_digest(self,row):
        fields={key:row.get(key) for key in ('source','to','text','id','kind','path','protocol','station_id','radio_id')}
        return hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest()

    def review(self,request):
        row=self.row(request)
        if row['status']!='Draft' or row.get('protocol')!='aprs':raise ValueError('Draft is no longer sendable')
        now=self.clock()
        self.reviews={token:r for token,r in self.reviews.items() if r['expires_at']>=now and r['draft_id']!=row['draft_id']}
        token=secrets.token_hex(24)
        value=dict(draft_id=row['draft_id'],revision=row['revision'],expires_at=now+60,digest=self.review_digest(row))
        self.reviews[token]=value
        while len(self.reviews)>64:del self.reviews[next(iter(self.reviews))]
        return dict(review_token=token,expires_at=value['expires_at'],row=copy.deepcopy(row),
                    payload=model.payload_for(row['to'],row['text'],row['id']).decode('ascii'),capability=self.capability())

    def send(self,request,fingerprint):
        now=self.clock()
        if request.get('confirm') is not True:raise ValueError('A fresh explicit Send action is required')
        issued=request.get('issued_at')
        if not isinstance(issued,(int,float)) or not 0<=now-issued<=30:raise ValueError('Send intent expired')
        for key,expected in [('station_id',self.station_id),('radio_id',self.radio_id),('source',self.state.call)]:
            if request.get(key)!=expected:raise ValueError('Owner identity mismatch: '+key)
        if not self.allow_send or not self.ready():raise ValueError('Send capability unavailable')
        token=request.get('review_token');review=self.reviews.pop(token,None)
        if not review or now>review['expires_at']:raise ValueError('Review expired or already consumed')
        row=self.row(dict(draft_id=review['draft_id'],expected_revision=review['revision']))
        if row['status']!='Draft' or self.review_digest(row)!=review['digest']:raise ValueError('Reviewed message changed or already attempted')
        row.update(status='Submitting',command_id=request['request_id'],command_fingerprint=fingerprint,
                   send_requested_at=now,revision=row['revision']+1)
        # Intent must be durable before any transport side effect. Never enqueue on restart.
        try:self.changed()
        except OSError:
            row['status']='Unconfirmed'
            raise
        try:self.submit(row)
        except (OSError,ValueError) as exc:
            self.state.unconfirmed(row,'Submission uncertain; no automatic retry')
            row['submission_error']=str(exc)
        self.changed()
        return dict(accepted=True,row=copy.deepcopy(row))

    def observe(self,records,describe):
        """Only the owner's trusted raw-source adapter supplies capture evidence."""
        changed=False
        for record in records[:200]:
            try:
                stamp=datetime.datetime.fromisoformat(record['time'])
                if stamp.tzinfo is None:continue
                epoch=stamp.timestamp();frame=bytes.fromhex(record['frame'])
            except (ValueError,TypeError,KeyError):continue
            for row in self.state.outbox:
                if 'send_requested_at' not in row or epoch<row['send_requested_at']:continue
                if record.get('direction')=='host_to_radio_written' and row.get('wire_hex'):
                    wire=bytes.fromhex(row['wire_hex'])[1:-1].replace(b'\xdb\xdc',b'\xc0').replace(b'\xdb\xdd',b'\xdb')
                    if wire==frame and not row.get('serial_written_at'):
                        row['serial_written_at']=record['time'];changed=True
                elif record.get('direction')=='radio_to_host':
                    text=describe(frame)
                    rx=model.parse_message(stamp.strftime('%H:%M:%S')+' '+text) if text else None
                    if rx and row['status'] not in ('Acknowledged','Rejected') and model.apply_peer_ack(row,rx,self.state.call):
                        row['ack_capture']=copy.deepcopy(record);changed=True
        if changed:self.changed()
        return changed


def snapshot_records(path):
    """Read an existing bounded snapshot; never writes to any radio endpoint."""
    import socket
    deadline=time.monotonic()+.3;data=bytearray()
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(.3);client.connect(path)
        while True:
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Snapshot deadline')
            client.settimeout(remaining);chunk=client.recv(8192)
            if not chunk:break
            data.extend(chunk)
            if len(data)>2*1024*1024:raise ValueError('Snapshot exceeds bound')
    lines=data.splitlines()
    header=json.loads(lines[0]);count=header.get('records')
    if header.get('type')!='snapshot' or header.get('version')!=1 or type(count) is not int or not 0<=count<=200 or len(lines)!=count+1:raise ValueError('Invalid snapshot')
    return [json.loads(line) for line in lines[1:]]


def serve_client(peer,owner):
    """One bounded JSON request/result, on an already accepted local socket."""
    peer.settimeout(.3);data=bytearray();deadline=time.monotonic()+.3
    while b'\n' not in data:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('Command deadline')
        peer.settimeout(remaining);chunk=peer.recv(4096)
        if not chunk:raise ValueError('Incomplete command')
        data.extend(chunk)
        if len(data)>16384:raise ValueError('Command too large')
    line,extra=data.split(b'\n',1)
    if extra.strip():raise ValueError('One command per connection')
    request=json.loads(line)
    peer.sendall((json.dumps(owner.handle(request))+'\n').encode())


def main():
    import argparse
    import os
    import socket
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket',required=True)
    parser.add_argument('--station-id',required=True);parser.add_argument('--radio-id',required=True)
    parser.add_argument('--source',required=True)
    parser.add_argument('--store',default=os.path.expanduser('~/.local/state/n810-aprs/messages.json'))
    parser.add_argument('--kiss',default='/dev/shm/n810-kiss.sock')
    parser.add_argument('--snapshot-socket',default='/dev/shm/n810-aprs-replay.sock')
    parser.add_argument('--radio-state')
    parser.add_argument('--enable-send',action='store_true',help='Operator configuration only; still requires fresh UI review/send and verified live radio state')
    args=parser.parse_args()
    if args.enable_send and not args.radio_state:parser.error('--enable-send requires --radio-state')
    import signal
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGHUP,stop)
    source=model.callsign(args.source)
    # Reuse the existing adapter/frame submission owner; no Bluetooth connection here.
    spec=importlib.util.spec_from_file_location('messages_transport',Path(__file__).with_name('n810-aprs-messages.py'))
    app=importlib.util.module_from_spec(spec);spec.loader.exec_module(app)
    monitor_spec=importlib.util.spec_from_file_location('messages_owner_monitor',Path(__file__).with_name('n810-packet-monitor.py'))
    monitor=importlib.util.module_from_spec(monitor_spec);monitor_spec.loader.exec_module(monitor)
    target=Path(args.store);target.parent.mkdir(parents=True,exist_ok=True)
    lock=app.acquire_store(args.store)
    state=app.State(source,args.store)
    transport=app.Transport(state,None,args.kiss,[])
    def ready():
        if not args.enable_send or transport.queue:return False
        try:
            status=json.loads(Path(args.radio_state).read_text());beacon=status.get('beacon') or {}
            call=beacon.get('aprs_callsign');ssid=int(beacon.get('aprs_ssid',0))
            actual=call+('-'+str(ssid) if ssid else '')
            return status.get('connected') is True and 0<=time.time()-status.get('heartbeat',0)<5 and status.get('settings',{}).get('kiss_en') is True and actual==source
        except (OSError,ValueError,TypeError,AttributeError):return False
    def submit(row):transport.path=list(row['path']);transport.submit(row)
    owner=Owner(state,args.station_id,args.radio_id,lambda rows:app.save(rows,args.store),submit,args.enable_send,ready)
    endpoint=Path(args.socket)
    if not endpoint.is_absolute():raise ValueError('Command socket must be absolute')
    # Refuse existing endpoints, including stale ones; do not unlink another owner.
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
        server.bind(str(endpoint));os.chmod(endpoint,0o600);inode=endpoint.stat().st_ino
        server.listen(4);server.settimeout(.1);due=0
        try:
            while True:
                try:peer,_=server.accept()
                except socket.timeout:peer=None
                if peer is not None:
                    with peer:
                        try:serve_client(peer,owner)
                        except (OSError,ValueError,TypeError):pass
                if transport.tick():owner.changed()
                pending=any('send_requested_at' in row and time.time()-row['send_requested_at']<600 and row['status'] not in ('Acknowledged','Rejected') for row in state.outbox)
                if pending and time.monotonic()>=due:
                    due=time.monotonic()+1
                    try:owner.observe(snapshot_records(args.snapshot_socket),monitor.describe)
                    except (OSError,ValueError,KeyError,IndexError):pass
        finally:
            try:transport.close();owner.changed()
            finally:
                try:
                    if endpoint.exists() and endpoint.stat().st_ino==inode:endpoint.unlink()
                finally:lock.close()

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
