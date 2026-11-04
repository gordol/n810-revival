"""Opt-in hardware Auto acceptance; isolated identities and real native backends.

The external connection is physically opened. A deliberate host-side disconnect
injects failure without rebooting/reflashing the board. Local fallback uses the
supplied native TCP or RNode configuration, without an emulated radio. Neither firmware
nor installed configuration is modified. Run only with exclusive board access.
"""
import argparse,json,os,sys,tempfile,threading,time
from pathlib import Path

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--domain',type=Path,default=Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum')
 parser.add_argument('--endpoint',required=True)
 parser.add_argument('--fallback-config',type=Path,required=True)
 parser.add_argument('--evidence',type=Path,required=True)
 parser.add_argument('--peer-socket',type=Path,help='Isolated stock peer owner; verify real service calls and LXMF receipts at every phase')
 parser.add_argument('--timeout',type=float,default=180)
 args=parser.parse_args();sys.path.insert(0,str(args.domain))
 import external_node
 from session_owner import SessionOwner
 from owner import serve
 from wire import exchange
 from native_radio import configuration
 config=args.fallback_config.read_text();radio=configuration(args.fallback_config)
 if radio.get('type') not in ('TCPClientInterface','RNodeInterface'):raise ValueError('Use an explicit TCPClientInterface or RNodeInterface fallback')
 physical_local=radio['type']=='RNodeInterface'
 local_port=radio['port'] if physical_local else '/dev/null'
 profile=dict(id='network',label='Hardware acceptance',frequency=912345000,bandwidth=500000,txpower=2,spreadingfactor=7,codingrate=5)
 if physical_local:
  for name in ('frequency','bandwidth','txpower','spreadingfactor','codingrate'):profile[name]=int(radio[name])
 blocked=threading.Event();connections=[];original=external_node.Connection
 class Connection(original):
  def __enter__(self):
   if blocked.is_set():raise ConnectionError('Acceptance: external connection deliberately unavailable')
   result=super().__enter__();connections.append(self);return result
 original_probe=external_node.probe
 def probe(address,**kwargs):
  if blocked.is_set():raise ConnectionError('Acceptance: external connection deliberately unavailable')
  return original_probe(address,**kwargs)
 external_node.Connection=Connection;external_node.probe=probe
 owners=[];errors=[];stop=threading.Event();started=time.monotonic();transitions=[];result=dict(passed=False,scope='end-to-end' if args.peer_socket else 'connectivity-only',physical_external=not args.endpoint.startswith('unix://'),local_fallback=radio['type'],manual_recovery_actions=[])
 import native_rpc
 original_library=native_rpc.Library;unexpected=[]
 def record_failure(action,error):
  if not blocked.is_set() and not stop.is_set() and len(unexpected)<8:
   unexpected.append(dict(action=action,error=str(error),elapsed=round(time.monotonic()-started,3)))
 class CheckedLibrary(original_library):
  def exchange(self,action,**data):
   try:return super().exchange(action,**data)
   except (OSError,ValueError,ConnectionError) as error:
    record_failure(action+':'+str(data.get('operation','')),error);raise
  def close(self,*args,**kwargs):
   if self.failure:record_failure('close',self.failure)
   return super().close(*args,**kwargs)
 native_rpc.Library=CheckedLibrary
 with tempfile.TemporaryDirectory(prefix='p-hw-auto-',dir='/tmp') as tmp:
  root=Path(tmp);state=root/'state';state.mkdir(mode=0o700);runtime=root/'run';runtime.mkdir(mode=0o700)
  external_node.save(state/'external-node.msgpack',dict(mode='auto',endpoint=args.endpoint))
  def factory(s,n):
   owner=SessionOwner(s,n,'network','usb',local_port,profile['txpower'],profile['txpower']);owners.append(owner)
   # TCP acceptance uses /dev/null for the serial-management port check only.
   # Its native adapter exchanges actual packets with the configured network peer.
   owner.store.commit({'network':owner.store.validate(profile)},'network')
   owner.store.configuration=lambda **kwargs:config
   return owner
  def run():
   try:serve(runtime/'owner.sock',state,'hardware-auto',factory,stopped=stop)
   except BaseException as error:errors.append(repr(error))
  thread=threading.Thread(target=run,name='hardware-auto-owner',daemon=True);thread.start()
  def request(path,action='snapshot',payload=None):
   return exchange(path,dict(version=1,action=action,request_id=os.urandom(8).hex(),payload=payload or {}))
  def call(action='snapshot',payload=None):
   return request(runtime/'owner.sock',action,dict(station='hardware-auto',radio='network') if action in ('connect','disconnect') else payload)
  def peer(action='snapshot',payload=None):return request(args.peer_socket,action,payload)
  peer_card=None;live_providers=[]

  def wait(predicate,label):
   deadline=time.monotonic()+args.timeout;last={}
   while time.monotonic()<deadline:
    if errors:raise AssertionError(errors)
    if unexpected:raise AssertionError('Unexpected external runtime failure: '+str(unexpected))
    try:
     last=call()
     if predicate(last):return last
    except (OSError,ValueError):pass
    time.sleep(.25)
   raise AssertionError(label+': '+str({k:last.get(k) for k in ('radio_state','error','external_node','last_job')}))
  def phase(name):
   snapshot=wait(lambda s:s['radio_state']=='online' and s['external_node']['selected']==name,name)
   transitions.append(dict(backend=name,elapsed=round(time.monotonic()-started,3)))
   assert snapshot['public_card']['public_key']==identity,'Application identity changed'
   call('announce') # Exercise the selected runtime, not just its cached snapshot.
   if peer_card:
    from service_transport import ReticulumTransport
    remote=ReticulumTransport(runtime/'owner.sock',peer_card['identity'],'reticulum')
    reverse=ReticulumTransport(args.peer_socket,host_card['identity'],'reticulum')
    try:
     service_started=time.monotonic()
     wait(lambda _:remote.exchange(dict(version=1,action='snapshot')).get('owner_online'),'real service call during '+name)
     transitions[-1]['service_seconds']=round(time.monotonic()-service_started,3)
     reverse_started=time.monotonic()
     wait(lambda _:reverse.exchange(dict(version=1,action='snapshot')).get('owner_online'),'hosted service call during '+name)
     transitions[-1]['reverse_service_seconds']=round(time.monotonic()-reverse_started,3)
     if not live_providers:
      from provider import Provider
      live_providers.extend([Provider(runtime/'owner.sock',transport=ReticulumTransport(runtime/'owner.sock',peer_card['identity'],'reticulum')),
                             Provider(args.peer_socket,transport=ReticulumTransport(args.peer_socket,host_card['identity'],'reticulum'))])
     for publisher,subscriber in zip((peer,call),live_providers):
      for enabled in (False,True):
       publisher('message_discovery',dict(enabled=enabled))
       wait(lambda _,p=subscriber,e=enabled:p.snapshot().get('owner_online') and p.snapshot().get('message_discovery') is e,'live app subscription during '+name)
     transitions[-1]['live_subscriptions']=True
     text='Hardware Auto '+str(len(transitions))+' '+os.urandom(4).hex()
     call('message_discovery',dict(enabled=True))
     message_started=time.monotonic();sent_after=time.time()
     call('send',dict(peer=peer_card['identity'],text=text))
     wait(lambda _:any(m.get('text')==text and m.get('direction')=='rx' and m.get('signature_valid') for m in peer()['messages']),'signed LXMF receive during '+name)
     wait(lambda s:any(m.get('text')==text and m.get('state')=='delivered' for m in s['messages']),'LXMF receipt during '+name)
     received=next(m for m in peer()['messages'] if m.get('text')==text and m.get('direction')=='rx')
     stamp=received.get('timestamp')
     assert type(stamp) in (int,float) and sent_after-5<=stamp<=time.time()+5,'Offloaded LXMF timestamp does not match host wall clock'
     if unexpected:raise AssertionError('Unexpected external runtime failure: '+str(unexpected))
     transitions[-1].update(service_call=True,reverse_service_call=True,lxmf_receipt=True,message_seconds=round(time.monotonic()-message_started,3),timestamp_valid=True)
     reverse_text='Hardware Auto reverse '+str(len(transitions))+' '+os.urandom(4).hex();reverse_started=time.monotonic()
     peer('send',dict(peer=host_card['identity'],text=reverse_text))
     wait(lambda s:any(m.get('text')==reverse_text and m.get('direction')=='rx' and m.get('signature_valid') for m in s['messages']),'signed LXMF receive at host during '+name)
     wait(lambda _:any(m.get('text')==reverse_text and m.get('state')=='delivered' for m in peer()['messages']),'reverse LXMF receipt during '+name)
     transitions[-1].update(reverse_lxmf_receipt=True,reverse_message_seconds=round(time.monotonic()-reverse_started,3),verified_elapsed=round(time.monotonic()-started,3))
    finally:remote.close();reverse.close()
   return snapshot
  try:
   wait(lambda s:s.get('external_node',{}).get('offload_ready'),'capable external executor')
   call('connect');snapshot=wait(lambda s:s['radio_state']=='online','first external connection')
   identity=snapshot['public_card']['public_key']
   if args.peer_socket:
    from contacts import fingerprint
    peer_card=peer()['public_card'];host_card=snapshot['public_card']
    for action in (call,peer):
     card=peer_card if action is call else host_card
     action('import_peer',dict(card=json.dumps(card)))
     action('verify_peer',dict(peer=card['identity'],fingerprint=fingerprint(bytes.fromhex(card['public_key']))))
    peer('service_share',dict(peer=host_card['identity'],expected_public_key=host_card['public_key'],service='reticulum',operations=['snapshot','subscribe']))
    call('service_share',dict(peer=peer_card['identity'],expected_public_key=peer_card['public_key'],service='reticulum',operations=['snapshot','subscribe']))
    call('service_discovery',dict(enabled=True))
    peer('service_discovery',dict(enabled=True));peer('message_discovery',dict(enabled=True))
   phase('external')
   blocked.set()
   for connection in list(connections):connection.__exit__(None,None,None)
   phase('local');blocked.clear();phase('external')
   result.update(passed=True,transitions=transitions,identity_preserved=True,node_identity=owners[0].node_preferences.get('node_identity'),python_rns_imported='RNS' in sys.modules)
   assert not result['python_rns_imported']
  except BaseException as error:
   result.update(error=str(error),transitions=transitions);raise
  finally:
   for provider in live_providers:provider.close()
   stop.set();blocked.clear()
   if owners:owners[0].post(dict(kind='shutdown'))
   thread.join(45);external_node.Connection=original;external_node.probe=original_probe;native_rpc.Library=original_library
   result['unexpected_external_errors']=unexpected
   result['owner_stopped']=not thread.is_alive();result['elapsed']=round(time.monotonic()-started,3)
   if unexpected:result['passed']=False
   args.evidence.write_text(json.dumps(result,indent=2)+'\n')
   assert not thread.is_alive(),'Acceptance owner did not stop'
   assert not unexpected,'Unexpected external runtime failure: '+str(unexpected)
 print(json.dumps(result))
def stock_peer():
 # Stock RNS/LXMF reference runs on the laptop only, never inside the host client.
 import signal
 sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum'))
 from owner import serve
 from lxmf_owner import LXMFBackend
 _,_,socket_path,state,config=sys.argv
 def factory(directory,station):
  owner=LXMFBackend(directory,station,Path(config),'reference','loopback');owner._connect();return owner
 signal.signal(signal.SIGTERM,lambda *_:(_ for _ in ()).throw(SystemExit(0)))
 serve(socket_path,state,'stock-peer',factory)

if __name__=='__main__':
 if len(sys.argv)>1 and sys.argv[1]=='--stock-peer':stock_peer()
 else:main()
