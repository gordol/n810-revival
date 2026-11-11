"""Broker one native Symbian window under Pocket's existing GPU ownership."""
import array,os,signal,socket,subprocess,struct,stat,errno
from symbian_session import command,environment,session_log

def retire_stale_control(path,uid):
    try:previous=path.lstat()
    except FileNotFoundError:return
    if not stat.S_ISSOCK(previous.st_mode) or previous.st_uid!=uid:
        raise RuntimeError('Unexpected desktop control socket owner or type')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
        peer.settimeout(.5)
        try:peer.connect(str(path))
        except OSError as error:
            if error.errno!=errno.ECONNREFUSED:raise
        else:raise RuntimeError('Desktop control socket is still active')
    current=path.lstat()
    if (current.st_dev,current.st_ino)!=(previous.st_dev,previous.st_ino):
        raise RuntimeError('Desktop control socket changed during cleanup')
    path.unlink()

class Broker:
    def __init__(self,account,gpu,job_lock,env,drop,status_directory=None,code=None):
        self.account=account;self.gpu=gpu;self.job_lock=job_lock;self.env=env;self.drop=drop;self.active=None;self.faulted=False;self.status_directory=status_directory;self.code=code
    def sources(self):return () if self.active is None else tuple(x for x in (self.active['pidfd'],self.active['control']) if x is not None)
    def start(self,application,request):
        if self.faulted:raise RuntimeError('Previous GPU window did not retire safely; graphics owner review required')
        if self.active is not None:raise RuntimeError('Close the active Symbian window first')
        argv=command(application,self.account.pw_dir,code=self.code)
        consumer,producer=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        control,parent_control=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        reader,writer=os.pipe2(os.O_CLOEXEC|os.O_NONBLOCK)
        child=None;pidfd=None
        try:
            env=environment(self.account.pw_dir,self.env,code=self.code)
            env.update(N810_SYMBIAN_WINDOW_FD=str(producer.fileno()),N810_SYMBIAN_KEYBOARD_FD=str(reader),N810_MBX_RENDER_FD=str(self.gpu),N810_MBX_JOB_LOCK_FD=str(self.job_lock),N810_MBX_WINDOW_IMAGES='1',N810_MBX_NATIVE_WINDOWS='1',N810_MBX_WINDOW_FIRST='0',N810_MBX_WINDOW_COUNT='6',N810_MBX_SEPARATE_ALPHA='1')
            for legacy in ('N810_MBX_SURFACE_CHECKPOINT','N810_MBX_RESIDENT_CHECKPOINT','N810_MBX_RESIDENT_ALPHA'):env.pop(legacy,None)
            with session_log(self.account,'window-session.log') as log:
                child=subprocess.Popen(argv,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,pass_fds=(self.gpu,self.job_lock,producer.fileno(),reader),preexec_fn=self.drop)
            pidfd=os.pidfd_open(child.pid)
            fds=array.array('i',(consumer.fileno(),writer,control.fileno()))
            request.sendmsg([b'window'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,fds)])
            self.active=dict(child=child,pidfd=pidfd,control=parent_control,stopped=False,consumer_retired=False,application=application)
            parent_control=None;pidfd=None
        except BaseException:
            if child is not None:
                child.terminate();child.wait()
            raise
        finally:
            consumer.close();producer.close();control.close();os.close(reader);os.close(writer)
            if parent_control is not None:parent_control.close()
            if pidfd is not None:os.close(pidfd)
    def service(self,ready):
        current=self.active
        if current is None:return
        child=current['child']
        # Consume retirement before exit when both descriptors became ready.
        if current['control'] in ready:
            message=current['control'].recv(8)
            if message in (b'C',b'F'):current['consumer_retired']=True
            if message==b'S':
                if child.poll() is None:child.send_signal(signal.SIGSTOP);current['stopped']=True
            elif message==b'R':
                if child.poll() is None:child.send_signal(signal.SIGCONT);current['stopped']=False
            else:
                if child.poll() is None:
                    if current['stopped']:child.send_signal(signal.SIGCONT);current['stopped']=False
                    if message!=b'F':child.terminate()
                current['control'].close();current['control']=None
        if current['pidfd'] in ready:
            result=child.wait()
            if not current['consumer_retired']:self.faulted=True
            if self.status_directory is not None:
                status=self.status_directory/'symbian-result';status.write_text(str(result)+'\t'+current['application']+'\n');status.chmod(0o644)
            if current['control'] is not None:
                try:current['control'].sendall(b'E'+struct.pack('<i',result))
                except OSError:pass
                current['control'].close()
            os.close(current['pidfd']);self.active=None
            return result
    def close(self):
        if self.active is None:return
        current=self.active;child=current['child']
        if child.poll() is None:
            if current['stopped']:child.send_signal(signal.SIGCONT)
            child.terminate()
        # Keep the GPU/session owner alive until the guest has actually exited.
        # A host timeout must not strand its inherited render descriptor.
        child.wait()
        if current['control'] is not None:current['control'].close()
        os.close(current['pidfd']);self.active=None
