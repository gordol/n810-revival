"""Managed physical HTIT owner; local attachments have separate lifetimes."""
import argparse
import hashlib
import importlib.util
import queue
import re
import secrets
import signal
import sys
from pathlib import Path

if __package__:from .hub_session import HubSession
else:from hub_session import HubSession

RETICULUM=Path(__file__).resolve().parents[1]/'reticulum'
sys.path.insert(0,str(RETICULUM))
# This executable has a distinct name, but MeshCore's owner.py may already be
# imported by its caller. Load the shared server by its reviewed file path.
_spec=importlib.util.spec_from_file_location('pocket_hub_owner_server',RETICULUM/'owner.py')
_server=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_server)


def canonical_port(port):
    if not isinstance(port,str):raise ValueError('Choose a hub device')
    match=re.fullmatch(r'rfcomm://((?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2})/([0-9]{1,2})',port)
    if match and 1<=int(match[2])<=30:return 'rfcomm://'+match[1].upper()+'/'+str(int(match[2]))
    if re.fullmatch(r'/dev/[A-Za-z0-9_.-]{1,128}',port):
        resolved=str(Path(port).resolve())
        if re.fullmatch(r'/dev/(?:[A-Za-z0-9_.-]{1,128}|pts/[0-9]+)',resolved):return resolved
    raise ValueError('Choose an explicit USB device or RFCOMM address/channel')


def hub_identity(port):return hashlib.sha256(canonical_port(port).encode()).hexdigest()[:24]


class HubOwner:
    def __init__(self,state,station,port,session_factory=HubSession):
        self.port=canonical_port(port);self.hub_id=hub_identity(self.port)
        self.station=station;self.instance=secrets.token_hex(8)
        self.revision=0;self.wake=None;self.events=queue.Queue(maxsize=128);self.overflow=False
        self.clients={};self.attachments={};self.connection_state='idle';self.generation=0
        self.host_id=None;self.service_bitmap=0;self.bridge={};self.error=None;self.last_job=None
        self.worker=session_factory(self.port,self.post)

    def post(self,event):
        try:self.events.put_nowait(event)
        except queue.Full:self.overflow=True
        if self.wake:
            try:self.wake.send(b'x')
            except (BlockingIOError,OSError):pass

    def drain(self):
        while True:
            try:event=self.events.get_nowait()
            except queue.Empty:break
            kind=event['kind']
            if kind=='physical':
                self.connection_state=event['state'];self.generation=event['generation']
                self.host_id=event.get('host_id');self.service_bitmap=event.get('service_bitmap',0)
                self.error=event.get('error')
                if self.connection_state!='online':self.bridge={}
            elif kind=='attachment' and event['token'] in self.attachments:
                self.attachments[event['token']].update({k:v for k,v in event.items() if k!='kind'})
            elif kind=='bridge':self.bridge={k:v for k,v in event.items() if k!='kind'}
            elif kind=='diagnostic':self.error=event['error']
            self.revision+=1
        if self.overflow:
            self.overflow=False
            try:self.worker.command('disconnect')
            except ValueError:self.worker.abort()
            self.error='Hub state queue overflow; connection closed without replay'
            for item in self.attachments.values():item.update(state='error',port=None,error=self.error)
            self.revision+=1

    def snapshot(self):
        return dict(version=1,owner_online=True,service_type='wireless-hub',hub_id=self.hub_id,
                    station_id=self.station,port=self.port,instance=self.instance,
                    revision=self.revision,connection_state=self.connection_state,
                    generation=self.generation,host_id=self.host_id,service_bitmap=self.service_bitmap,
                    capabilities=['connect','disconnect','attach'],attachments=list(self.attachments.values()),
                    bridge=dict(self.bridge),error=self.error,last_job=self.last_job)

    @staticmethod
    def options(payload):
        if not isinstance(payload,dict) or type(payload.get('service')) is not int:raise ValueError('Choose a hub service')
        service=payload['service']
        if service==1:
            if set(payload)!={'service','ble','address_type'} or not isinstance(payload['ble'],str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}',payload['ble']):raise ValueError('Choose an exact BLE address')
            if type(payload['address_type']) is not int or payload['address_type'] not in (0,1):raise ValueError('Choose BLE address type')
            return service,dict(ble=payload['ble'].upper(),address_type=payload['address_type'])
        if service==2:
            if set(payload)!={'service','peer'} or type(payload['peer']) is not int or payload['peer'] not in (0,1,2):raise ValueError('Choose a peer host ID')
            return service,dict(peer=payload['peer'])
        if service==3 and set(payload)=={'service'}:return service,{}
        raise ValueError('Unsupported hub attachment')

    def attach_client(self,client,request):
        if not isinstance(request,dict) or type(request.get('version')) is not int or request['version']!=1 or request.get('action')!='attach':raise ValueError('Unsupported hub request version')
        if client in self.clients:raise ValueError('Client already attached')
        service,options=self.options(request.get('payload'))
        if any(item['service']==service for item in self.attachments.values()):raise ValueError('Hub service already has a consumer')
        token=secrets.token_hex(12)
        self.worker.command('attach',token=token,service=service,options=options)
        self.clients[client]=token
        self.attachments[token]=dict(token=token,service=service,state='opening',port=None,
                                     generation=self.generation,error=None)
        self.revision+=1
        return dict(version=1,token=token,hub_id=self.hub_id,instance=self.instance)

    def detach_client(self,client):
        token=self.clients.pop(client,None)
        if token is None:return
        self.attachments.pop(token,None);self.revision+=1
        try:self.worker.command('detach',token=token)
        except ValueError:
            # Never leave a service attached after its control stream vanished.
            self.worker.abort()
            self.connection_state='error';self.error='Hub control queue full; connection closed'

    def dispatch(self,request):
        if not isinstance(request,dict) or type(request.get('version')) is not int or request['version']!=1:raise ValueError('Unsupported hub request')
        action=request.get('action')
        if action=='snapshot':return self.snapshot()
        if action not in ('connect','disconnect') or request.get('payload',{})!={}:raise ValueError('Unknown hub action')
        self.worker.command(action)
        self.last_job=dict(id=request.get('request_id'),action=action,state='queued');self.revision+=1
        return dict(version=1,job=self.last_job)

    def close(self):self.worker.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('socket','state','station','port'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--ready-fd',type=int)
    args=parser.parse_args()
    def stop(signum,frame):raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    _server.serve(args.socket,args.state,args.station,
                  lambda state,station:HubOwner(state,station,args.port),args.ready_fd)


if __name__=='__main__':main()
