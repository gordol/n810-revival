"""Private device catalogue and system owner using the existing binary owner protocol."""
import os
import sys

def identity():
    from build_identity import release_id
    # Installed releases already have a verified immutable source identity.
    # Keep file hashing only for unpackaged development trees.
    release=release_id()
    if release!='UNKNOWN':return release
    import hashlib
    with open(__file__,'rb') as source:
        return hashlib.sha256(source.read()).hexdigest()[:16]

def validate_runtime(root):
    import stat
    st=os.lstat(root)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode&0o077:
        raise ValueError('Unsafe device runtime')

def validate_release(result):
    from build_identity import release_id
    if result.get('implementation')!=identity() or result.get('release')!=release_id():
        raise ValueError('Device catalogue uses a previous release; restart it before attaching')

# A live directory needs only its wire client. Do not import server classes,
# pathlib or service factories for every SSH attachment.
if __name__=='__main__' and sys.argv[1:]==['--ensure']:
    root=os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0,root)
    sys.path.insert(0,os.path.join(root,'vendor/apps/domains/reticulum'))
    from wire import encode,exchange
    runtime='/tmp/pocket-device-'+str(os.getuid())
    try:
        validate_runtime(runtime)
        endpoint=runtime+'/owner.sock'
        result=exchange(endpoint,dict(version=1,action='snapshot',scope='directory'))
    except (OSError,ConnectionError,EOFError):pass
    else:
        try:validate_release(result)
        except ValueError:pass  # Recover under the existing startup lock below.
        else:
            if result.get('services'):
                result['socket']=endpoint
                sys.stdout.buffer.write(encode(result));sys.stdout.buffer.flush()
                raise SystemExit(0)

import _socket as socket
import time
ROOT=os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0,str(ROOT))
sys.path.insert(0,os.path.join(ROOT,'vendor/apps/domains/reticulum'))
from owner import ServiceOwner,serve,exchange
from wire import encode
from service_catalog import OWNER_IDS,owner_factory,saved_owner

def configuration():
    from pathlib import Path
    preferred=Path.home()/'.local/state/current-world'
    portable=Path.home()/'.local/state/pocket/default'
    return preferred if any((preferred/name).exists() for name in ('reticulum-owner.msgpack','reticulum-owner.json','meshcore-owner.toml')) else portable

class DeviceOwner(ServiceOwner):
    def __init__(self,state,station):
        import threading
        super().__init__(state,station)
        self.implementation=identity()
        from build_identity import release_id
        self.release=release_id()
        self.providers={};self.telemetry={}
        self.services=[dict(id='system',available=True,state='ready'),
                       dict(id='receive',available=False,state='starting')]+[
                           dict(id=name,available=False,state='starting') for name in OWNER_IDS]
        self.starting={}
        self.stopped=threading.Event();self.changed=threading.Event();self.guard=threading.RLock()
        self.receive=None
        self.worker=None;self.samples=None
    def response_sent(self):
        """Start optional work only after the directory's first reply is sent."""
        if self.worker is not None:return
        import threading
        self.worker=threading.Thread(target=self.collect,daemon=True)
        self.samples=threading.Thread(target=self.sample,daemon=True)
        self.worker.start();self.samples.start()
    def notify(self):
        self.changed.set()
        self.post(dict(state='complete',action='services'))
    def sample(self):
        import importlib.util
        from pathlib import Path
        # Telemetry and receive history must never gate the directory listener.
        try:
            spec=importlib.util.spec_from_file_location('device_collector',Path(ROOT)/'vendor/packet-console/web-console/read-state.py')
            collector=importlib.util.module_from_spec(spec);spec.loader.exec_module(collector)
            while not self.stopped.is_set():
                try:
                    telemetry=collector.host_status()
                except Exception as error:telemetry=dict(telemetry_error=str(error)[:200])
                with self.guard:self.telemetry=telemetry
                self.post(dict(state='complete',action='sample'))
                if self.receive is None:
                    from device_feed import RawReceive
                    receive=RawReceive('/dev/shm/n810-aprs.sock','/dev/shm/n810-aprs-replay.sock')
                    self.receive=receive
                    receive.bind_wakeup(self.notify)
                self.stopped.wait(5)
        except Exception as error:
            with self.guard:self.telemetry=dict(telemetry_error=str(error)[:200])
            self.post(dict(state='complete',action='sample'))
    def collect(self):
        import threading
        from pathlib import Path
        from app_registry import Registry
        self.registry=Registry(ROOT)
        while not self.stopped.is_set():
            self.changed.clear()
            services=[dict(id='system',available=True,state='ready')]
            online=Path('/dev/shm/n810-aprs.sock').is_socket()
            services.append(dict(id='receive',available=online,state='ready' if online else 'unavailable'))
            for name in OWNER_IDS:
                try:
                    selection=saved_owner(name,configuration())
                    if selection is None or selection['mode']!='local':
                        services.append(dict(id=name,available=False,state='unavailable',reason='No local owner configured'));continue
                    state_path=Path(selection['state'])
                    runtime='meshcore-runtime' if name=='meshcore' else 'carrier-runtime' if 'carriers' in selection else 'management-runtime'
                    row=dict(id=name,available=False,state='starting',socket=str(state_path/runtime/'owner.sock'),reason='Starting local owner')
                    # Publish the configured endpoint before importing its adapter.
                    provider=self.providers.get(name)
                    if provider is None:
                        known={item['id'] for item in services+[row]}
                        with self.guard:self.services=services+[row]+[item for item in self.services if item['id'] not in known]
                        self.post(dict(state='complete',action='services'))
                        pending=self.starting.get(name)
                        if pending is None:
                            pending={'done':False}
                            def start(name=name,selection=selection,pending=pending):
                                try:
                                    factory=owner_factory(self.registry,name)
                                    pending['provider']=factory(local_state=selection['state'],local_options={k:v for k,v in selection.items() if k not in ('mode','state')},register=False,availability_only=True)
                                except Exception as error:pending['error']=error
                                finally:
                                    pending['done']=True
                                    self.changed.set()
                            pending['thread']=threading.Thread(target=start,name='device-owner-'+name,daemon=True)
                            self.starting[name]=pending
                            pending['thread'].start()
                        if not pending['done']:
                            services.append(row);continue
                        del self.starting[name]
                        if 'error' in pending:raise pending['error']
                        provider=pending['provider']
                        self.providers[name]=provider
                        provider.bind_wakeup(self.notify)
                    state=provider.snapshot()
                    ready=bool(state.get('owner_online'))
                    row.update(available=ready,state='ready' if ready else 'starting',socket=provider.path,
                               reason='' if ready else state.get('error','Owner reconnecting'))
                    phase=state.get('radio_state',state.get('connection_state'))
                    if phase is not None:row['radio_state']=phase
                    services.append(row)
                except Exception as error:services.append(dict(id=name,available=False,state='unavailable',reason=str(error)[:200]))
            with self.guard:self.services=services
            self.post(dict(state='complete',action='services'))
            self.changed.wait(5)
    def snapshot(self, *, directory=False):
        receive=None if directory else self.receive
        if receive is not None:
            from device_feed import bounded_receive
            received=bounded_receive(receive.state,encode)
        else:received=dict(online=False,error='Receive service starting',revision=0,raw_records=[],omitted_records=0)
        with self.guard:result=dict(version=1,owner_online=True,device=socket.gethostname(),implementation=self.implementation,release=self.release,pid=os.getpid(),revision=self.revision,capabilities=[],services=list(self.services),telemetry=dict(self.telemetry))
        if not directory:result['receive']=received
        return result
    def dispatch(self,request):
        if request.get('action')=='snapshot' and request.get('scope')=='history':
            from device_retained import owner
            return owner('n810-frame-history.py').page((request.get('payload') or {}).get('before'),anchor=(request.get('payload') or {}).get('anchor'))
        if request.get('action')!='snapshot':raise ValueError('Device catalogue is read only')
        scope=request.get('scope')
        if scope not in (None,'directory'):raise ValueError('Unknown snapshot scope')
        return self.snapshot(directory=scope=='directory')
    def close(self):
        self.stopped.set();self.changed.set()
        for worker in (self.worker,self.samples):
            if worker is not None:worker.join(45)
        if self.receive is not None:self.receive.close()
        for pending in self.starting.values():
            pending['thread'].join()
            if 'provider' in pending:pending['provider'].close()
        for provider in self.providers.values():provider.close()

def retire_stale(endpoint,result,root):
    """Retire only the same-user Linux process proven to own this directory."""
    import signal,struct
    from contextlib import closing
    from pathlib import Path
    pid=result.get('pid')
    if type(pid) is not int or pid<=1 or pid==os.getpid():raise ValueError('Cannot verify stale device owner')
    with closing(socket.socket(socket.AF_UNIX)) as peer:
        peer.settimeout(3);peer.connect(endpoint)
        actual,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
    if (actual,uid)!=(pid,os.getuid()):raise ValueError('Stale directory process ownership changed')
    proc=Path('/proc')/str(pid)
    args=(proc/'cmdline').read_bytes().split(b'\0')
    script=os.path.realpath(__file__).encode()
    if proc.stat().st_uid!=os.getuid() or script not in args:raise ValueError('Stale directory is not the installed device service')
    index=args.index(script)
    tail=[arg.decode() for arg in args[index+1:] if arg]
    valid=tail==['--serve',os.fspath(root)] or tail==['--ensure'] and os.fspath(root)=='/tmp/pocket-device-'+str(os.getuid())
    if not valid:raise ValueError('Stale directory arguments do not match its runtime')
    # Recheck kernel peer identity immediately before signalling. No other
    # service, shell, radio owner or unverified PID is eligible for retirement.
    with closing(socket.socket(socket.AF_UNIX)) as peer:
        peer.settimeout(3);peer.connect(endpoint)
        again=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if again[:2]!=(pid,os.getuid()):raise ValueError('Stale directory changed during recovery')
        os.kill(pid,signal.SIGTERM)


def ensure(root=None, timeout=90, *, inherit=False):
    """Start once, then tolerate transient snapshot failures until ready.

    A timeout means the listener may still be alive: only a refused/missing
    endpoint permits creation, never a slow response from an existing owner.
    """
    root=os.fspath(root) if root is not None else '/tmp/pocket-device-'+str(os.getuid())
    try:os.mkdir(root,mode=0o700)
    except FileExistsError:pass
    validate_runtime(root)
    from owner import private_lock as _lock
    deadline=time.monotonic()+timeout
    with _lock(os.path.join(root,'lock')) as lock_fd:
        endpoint=os.path.join(root,'owner.sock')
        process=None;retired=None
        while True:
            try:
                result=exchange(endpoint,dict(version=1,action='snapshot',scope='directory'))
            except (ConnectionRefusedError,FileNotFoundError):
                if process is None:
                    if retired is not None:
                        # The old owner unlinks its socket before joining its
                        # workers. Wait for its lifetime lock, not just EOF.
                        try:
                            with _lock(os.path.splitext(endpoint)[0]+'.lifetime.lock',blocking=False):pass
                        except BlockingIOError:
                            if time.monotonic()>=deadline:raise TimeoutError('Previous device directory did not finish stopping')
                            time.sleep(.2);continue
                    if os.path.lexists(endpoint):
                        from receive_bridge import _socket_owned
                        if not _socket_owned(endpoint):raise ValueError('Unsafe device endpoint')
                        os.unlink(endpoint)
                    fd=os.open(os.path.join(root,'owner.log'),os.O_WRONLY|os.O_APPEND|os.O_CREAT|os.O_NOFOLLOW,0o600)
                    with os.fdopen(fd,'ab') as log:
                        if inherit:
                            # Only the fresh, single-threaded --ensure entry uses fork.
                            # Reuse its imported protocol instead of executing Python twice.
                            process=os.fork()
                            if process==0:
                                try:
                                    os.close(lock_fd)
                                    os.setsid()
                                    null=os.open(os.devnull,os.O_RDONLY)
                                    os.dup2(null,0);os.close(null)
                                    os.dup2(log.fileno(),1);os.dup2(log.fileno(),2)
                                    import signal
                                    signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
                                    serve(os.path.join(root,'owner.sock'),os.path.join(root,'state'),'device',owner_factory=DeviceOwner)
                                except BaseException as error:
                                    if not isinstance(error,SystemExit) or error.code not in (None,0):
                                        import traceback
                                        traceback.print_exc()
                                        os._exit(1)
                                finally:os._exit(0)
                        else:
                            import subprocess
                            process=subprocess.Popen([sys.executable,os.path.realpath(__file__),'--serve',str(root)],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
            except (BlockingIOError,TimeoutError,ConnectionError,EOFError):
                pass
            else:
                try:validate_release(result)
                except ValueError:
                    if retired is None:
                        retire_stale(endpoint,result,root);retired=result.get('pid')
                    elif result.get('pid')!=retired:raise ValueError('Another incompatible device directory appeared during recovery')
                else:
                    if result.get('services'):
                        result['socket']=str(endpoint)
                        return result
            exited=(os.waitpid(process,os.WNOHANG)[0]!=0 if isinstance(process,int) else process is not None and process.poll() is not None)
            if exited:
                raise RuntimeError('Device owner exited during startup; see '+str(os.path.join(root,'owner.log')))
            if time.monotonic()>=deadline:raise TimeoutError('Device catalogue did not become ready')
            time.sleep(.2)

if __name__=='__main__':
    if sys.argv[1:]==['--ensure']:
        sys.stdout.buffer.write(encode(ensure(inherit=True)));sys.stdout.buffer.flush();raise SystemExit(0)
    import argparse
    import signal
    parser=argparse.ArgumentParser();parser.add_argument('--serve');parser.add_argument('--ensure',action='store_true');args=parser.parse_args()
    if args.serve:
        signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
        serve(os.path.join(args.serve,'owner.sock'),os.path.join(args.serve,'state'),'device',owner_factory=DeviceOwner)
    elif args.ensure:sys.stdout.buffer.write(encode(ensure()));sys.stdout.buffer.flush()
