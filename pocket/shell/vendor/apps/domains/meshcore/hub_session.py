"""One physical hub connection, independent explicitly attached local services."""
from collections import deque
import os
import queue
import select
import socket
import struct
import threading
import time

if __package__:
    from .hub_transport import Link, Endpoint, CompanionDecoder, check_reply, PhysicalLinkError
    from .rnode_adapter import Adapter
else:
    from hub_transport import Link, Endpoint, CompanionDecoder, check_reply, PhysicalLinkError
    from rnode_adapter import Adapter


class HubSession:
    """The worker alone reads/writes Link and allocates framed request IDs."""
    def __init__(self, port, publish, link_factory=Link, endpoint_factory=Endpoint):
        self.port,self.publish=port,publish
        self.link_factory,self.endpoint_factory=link_factory,endpoint_factory
        self.commands=queue.Queue(maxsize=16)
        self.wake_read,self.wake_write=socket.socketpair()
        self.wake_read.setblocking(False);self.wake_write.setblocking(False)
        self.link=None;self.generation=0;self.host_id=None;self.capabilities=0
        self.services={};self.pending={};self.mesh_claimed=False
        self.mesh_renewed=0;self.lease_ack_at=None;self.status_at=0
        self.ble_deadline=None;self.radio=None;self.stopping=False;self.closing=False
        self.thread=threading.Thread(target=self.run,name='hub-connection',daemon=True)
        self.thread.start()

    def command(self, action, **data):
        if self.stopping or not self.thread.is_alive():raise ValueError('Hub worker stopped; restart its owner')
        try:self.commands.put_nowait((action,data))
        except queue.Full:raise ValueError('Hub control queue full') from None
        try:self.wake_write.send(b'x')
        except BlockingIOError:pass

    def abort(self):
        self.stopping=True
        try:self.wake_write.send(b'x')
        except BlockingIOError:pass

    def close(self):
        self.abort()
        self.thread.join(20)
        if self.thread.is_alive():raise RuntimeError('Hub worker did not stop')
        self.wake_read.close();self.wake_write.close()

    def event(self, kind, **data):self.publish(dict(kind=kind,**data))

    def service_event(self, item, state, error=None):
        item['state']=state
        self.event('attachment',token=item['token'],service=item['service'],state=state,
                   generation=self.generation,port=os.ttyname(item['endpoint'].slave) if item.get('endpoint') else None,
                   error=str(error)[:512] if error else None)

    def open(self):
        if self.link:return
        self.event('physical',state='opening',generation=self.generation,error=None)
        link=None
        try:
            link=self.link_factory(self.port)
            hello=link.hello()
            if len(hello)!=3 or hello[0]!=1:raise ValueError('Unsupported hub protocol')
        except BaseException as error:
            if link:link.close()
            self.event('physical',state='error',generation=self.generation,error=str(error)[:512])
            raise
        self.link=link;self.host_id=hello[1];self.capabilities=hello[2];self.generation+=1
        self.status_at=time.monotonic()
        self.event('physical',state='online',generation=self.generation,host_id=self.host_id,
                   service_bitmap=self.capabilities,error=None)

    def request(self,service,op,data=b'',purpose='',owner=None,timeout=12):
        ident=self.link.send(service,op,data)
        self.pending[ident]=(service,op,purpose,owner,time.monotonic()+timeout)
        return ident

    def attach(self,token,service,options):
        if service in self.services:raise ValueError('Hub service already attached')
        item=dict(token=token,service=service,options=options,endpoint=None,state='opening',queue=deque())
        self.services[service]=item;self.service_event(item,'opening')
        try:
            self.open()
            if service==1:
                item['decoder']=CompanionDecoder()
                self.request(0,7,purpose='claim',owner=1,timeout=20)
            elif service==3:
                if not self.capabilities&8:raise ValueError('Hub firmware lacks onboard LoRa')
                item['endpoint']=self.endpoint_factory('RNODE_PORT')
                self.radio=Adapter(self.link,item['endpoint'])
                self.service_event(item,'ready')
            elif service==2:
                if options['peer']==self.host_id:raise ValueError('Peer cannot be this host')
                item['endpoint']=self.endpoint_factory('PEER_PORT');self.service_event(item,'ready')
            else:raise ValueError('Unsupported hub service')
        except PhysicalLinkError as error:self.close_link(error)
        except Exception as error:self.fail(service,error)

    def detach(self,token):
        item=next((v for v in self.services.values() if v['token']==token),None)
        if item:self.drop(item['service'])

    def drop(self,service):
        item=self.services.pop(service,None)
        if item is None:return
        claim_pending=service==1 and any(v[2]=='claim' and v[3]==1 for v in self.pending.values())
        self.pending={ident:value for ident,value in self.pending.items() if value[3]!=service}
        physical_error=None
        if service==1:
            self.ble_deadline=None
            if self.link and (self.mesh_claimed or claim_pending):
                try:self.link.send(0,8)
                except PhysicalLinkError as error:physical_error=error
                except OSError:pass
            self.mesh_claimed=False;self.lease_ack_at=None
        if service==3:
            if self.link and self.radio:
                try:self.radio.off()
                except PhysicalLinkError as error:physical_error=error
                except OSError:pass
            self.radio=None
        if item.get('endpoint'):
            try:item['endpoint'].close()
            except OSError:pass
            item['endpoint']=None
        item['queue'].clear()
        self.service_event(item,'detached')
        if physical_error and not self.closing:raise physical_error

    def fail(self,service,error):
        item=self.services.get(service)
        if item is None:return
        self.drop(service)
        self.service_event(item,'error',error)

    def close_link(self,error=None):
        self.closing=True
        try:
            for service in tuple(self.services):
                if error:self.fail(service,error)
                else:self.drop(service)
            if self.link:
                try:self.link.close()
                except OSError:pass
        finally:self.link=None;self.closing=False
        self.pending.clear();self.host_id=None;self.capabilities=0
        self.event('physical',state='error' if error else 'idle',generation=self.generation,error=str(error)[:512] if error else None)

    def mesh_ready(self):
        item=self.services.get(1)
        if item and item['endpoint'] is None:
            item['endpoint']=self.endpoint_factory('MESHCORE_PORT')
            self.ble_deadline=None;self.service_event(item,'ready')

    def frame(self,frame):
        if frame.service==3:
            if self.radio:
                try:self.radio.frame(frame)
                except PhysicalLinkError:raise
                except (OSError,ValueError,RuntimeError,BufferError) as error:self.fail(3,error)
            return
        request=self.pending.pop(frame.id,None) if frame.op&0x80 and frame.op<0x90 else None
        if request:
            service,op,purpose,owner,deadline=request
            try:
                if frame.service!=service or frame.op!=op|128:raise ValueError('Unexpected hub reply')
                check_reply(frame)
                if purpose in ('claim','renew'):
                    self.mesh_claimed=True;self.mesh_renewed=time.monotonic();self.lease_ack_at=time.time()
                    if purpose=='claim':
                        options=self.services[1]['options']
                        self.request(0,4,bytes([options['address_type']])+bytes.fromhex(options['ble'].replace(':','')),purpose='connect',owner=1)
                elif purpose=='connect':self.ble_deadline=time.monotonic()+75
                elif purpose=='status':
                    raw=frame.data[1:]
                    if len(raw)!=8:raise ValueError('Invalid hub status')
                    self.event('bridge',observed_at=time.time(),classic_connected=True,
                               ble_ready=bool(raw[1]),ble_connected=bool(raw[2]),mtu=int.from_bytes(raw[4:6],'little'),
                               owner=raw[0],spp1=bool(raw[6]),spp2=bool(raw[7]),lease_ack_at=self.lease_ack_at)
                    if raw[1] and self.mesh_claimed:self.mesh_ready()
            except PhysicalLinkError:raise
            except (OSError,ValueError,RuntimeError) as error:
                if owner is not None:self.fail(owner,error)
                else:self.event('diagnostic',error=str(error)[:512])
            return
        if frame.service==0:
            if frame.op==0x93 and self.mesh_claimed:self.mesh_ready()
            elif frame.op==0x92 and 1 in self.services:self.fail(1,frame.data.decode('utf8',errors='replace'))
            elif frame.op==0x94 and 1 in self.services:self.fail(1,'BLE pairing requires a passkey; pair explicitly before attaching')
        elif frame.op==0x90 and frame.service in self.services:
            item=self.services[frame.service];endpoint=item.get('endpoint')
            if endpoint:
                try:
                    if frame.service==1:endpoint.queue(b'>'+struct.pack('<H',len(frame.data))+frame.data)
                    elif frame.data and frame.data[0]==item['options']['peer']:endpoint.queue(frame.data[1:])
                except BufferError as error:self.fail(frame.service,error)

    def endpoint_io(self,service,readable,writable):
        item=self.services.get(service)
        if not item or not item.get('endpoint'):return
        endpoint=item['endpoint']
        try:
            if endpoint.master in writable:endpoint.flush()
            if endpoint.master not in readable:return
            data=os.read(endpoint.master,511 if service==2 else 1024)
            if not data:raise OSError('Local hub endpoint closed')
            if service==3:
                for command,payload in self.radio.decoder.feed(data):self.radio.command(command,payload)
            else:
                packets=item['decoder'].feed(data) if service==1 else [bytes([item['options']['peer']])+data]
                item['queue'].extend(packets)
                if len(item['queue'])>64:raise BufferError('Hub service queue full; no replay')
        except PhysicalLinkError:raise
        except (OSError,ValueError,RuntimeError,BufferError) as error:self.fail(service,error)

    def tick(self):
        now=time.monotonic()
        for ident,(service,op,purpose,owner,deadline) in tuple(self.pending.items()):
            if deadline<=now:
                self.pending.pop(ident,None)
                if owner is not None:self.fail(owner,'Hub '+purpose+' acknowledgement missing; no replay')
        if self.ble_deadline and now>self.ble_deadline:self.fail(1,'BLE setup timed out')
        if self.mesh_claimed and now-self.mesh_renewed>=10 and not any(purpose=='renew' for _,_,purpose,_,_ in self.pending.values()):
            self.request(0,7,purpose='renew',owner=1,timeout=20)
        if self.services and now-self.status_at>=5 and not any(purpose=='status' for _,_,purpose,_,_ in self.pending.values()):
            self.status_at=now;self.request(0,2,purpose='status')
        for service,item in tuple(self.services.items()):
            if service in (1,2) and item['queue'] and not any(s==service for s,_,_,_,_ in self.pending.values()):
                self.request(service,1,item['queue'].popleft(),purpose='packet',owner=service)
        if self.radio:
            try:self.radio.tick()
            except PhysicalLinkError:raise
            except (OSError,ValueError,RuntimeError,BufferError) as error:self.fail(3,error)

    def timeout(self):
        deadlines=[value[4] for value in self.pending.values()]
        if self.services:deadlines.append(self.status_at+5)
        if self.ble_deadline:deadlines.append(self.ble_deadline)
        if self.mesh_claimed and not any(p=='renew' for _,_,p,_,_ in self.pending.values()):deadlines.append(self.mesh_renewed+10)
        if self.radio:
            if self.radio.claimed:deadlines.append(self.radio.last_renew+10)
            deadlines.extend(start+65 for _,_,start in self.radio.pending.values())
        return max(.01,min(deadlines)-time.monotonic()) if deadlines else None

    def run(self):
        try:
            while not self.stopping:
                readers=[self.wake_read];writers=[]
                if self.link:readers.append(self.link.serial.fileno())
                for item in self.services.values():
                    if item.get('endpoint'):
                        readers.append(item['endpoint'].master)
                        if item['endpoint'].output:writers.append(item['endpoint'].master)
                try:readable,writable,_=select.select(readers,writers,[],self.timeout())
                except (OSError,ValueError) as error:
                    self.close_link(error);continue
                if self.wake_read in readable:
                    self.wake_read.recv(4096)
                    while True:
                        try:action,data=self.commands.get_nowait()
                        except queue.Empty:break
                        try:
                            if action=='stop':self.stopping=True;break
                            if action=='connect':self.open()
                            elif action=='disconnect':self.close_link()
                            elif action=='attach':self.attach(**data)
                            elif action=='detach':self.detach(**data)
                        except PhysicalLinkError as error:self.close_link(error)
                        except Exception as error:self.event('diagnostic',error=str(error)[:512])
                    # Attach/detach can reuse a descriptor number. Rebuild the
                    # poll set before acting on readiness from the old set.
                    if not self.stopping:continue
                if self.stopping:break
                if self.link:
                    try:
                        if self.link.serial.fileno() in readable:self.link.read()
                        for service in tuple(self.services):self.endpoint_io(service,readable,writable)
                        while self.link.inbox:self.frame(self.link.inbox.popleft())
                        self.tick()
                    except (OSError,ValueError,RuntimeError,BufferError) as error:self.close_link(error)
        finally:self.close_link()
