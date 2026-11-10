"""Serialize Pocket and native Symbian applications under one graphics owner."""
import os
import select
import signal
import socket
import struct
import subprocess
from pathlib import Path

APPS={'chess':'ChessGenius_20036D63.exe','snakes':'6r45_1b.exe'}

class Session:
    def __init__(self,directory,uid,gid):
        self.path=Path(directory)/'symbian.sock';self.uid=uid
        if self.path.exists():raise RuntimeError('Symbian launch socket already exists')
        self.server=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        self.server.bind(str(self.path));os.chown(self.path,uid,gid);os.chmod(self.path,0o600)
        self.server.listen(1)
    def wait(self,child,ready):
        """Wait for process exit or a validated request; never poll the device."""
        pidfd=os.pidfd_open(child.pid)
        try:
            while True:
                readable,_,_=select.select([pidfd,self.server],[],[])
                if pidfd in readable:return None
                with self.server.accept()[0] as request:
                    request.settimeout(2)
                    _,uid,_=struct.unpack('3i',request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    try:
                        application=request.recv(32).decode('ascii')
                        if uid!=self.uid or application not in APPS:raise ValueError('Invalid Symbian request')
                        ready(application)
                    except (OSError,ValueError,RuntimeError) as error:
                        try:request.sendall(str(error).encode()[:256])
                        except OSError:pass
                        continue
                    try:request.sendall(b'accepted')
                    except OSError:continue
                    return application
        finally:os.close(pidfd)
    def close(self):self.server.close();self.path.unlink(missing_ok=True)

def command(application,home):
    if application not in APPS:raise ValueError('Unknown Symbian application')
    private=Path(home)/'.local/share/symbian-private'
    # Paths are fixed; the unprivileged client cannot choose an executable.
    executable=private/'code/symbian-runtime';root=private/'runtime'
    if not (private/'code/lib/libOSMesa.so.8').is_file():raise RuntimeError('Install the matching private Symbian Mesa library first')
    if not executable.is_file() or not (root/'data/drives/c/sys/bin'/APPS[application]).is_file():
        raise RuntimeError('Install the native runtime and application in private storage first')
    return [str(executable),str(root),'C:\\sys\\bin\\'+APPS[application],'900']

def keyboard_device():
    names=[p.parent.parent.name for p in Path('/sys/class/input').glob('event*/device/name') if p.read_text().strip()=='N810 internal keyboard']
    if len(names)!=1:raise RuntimeError('Expected one N810 internal keyboard')
    return '/dev/input/'+names[0]

def run(application,account,fb,gpu,env,tty,drop,started=lambda child:None):
    argv=command(application,account.pw_dir)
    reader,writer=os.pipe2(os.O_CLOEXEC)
    keyboard=-1
    try:
        keyboard=os.open(keyboard_device(),os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
        child_env={k:v for k,v in env.items() if not k.startswith(('POCKET_','N810_SYMBIAN_','N810_MBX_'))}
        for name in ('N810_MBX_DESKTOP_TARGET','N810_MBX_WINDOW_IMAGES','N810_MBX_RESOURCE_REFERENCES','N810_MBX_TEXTURE_SUBSET','N810_MBX_TEXTURE_RESIDENCY'):
            child_env.pop(name,None)
        library=Path(account.pw_dir)/'.local/share/symbian-private/code/lib'
        child_env.update(LD_PRELOAD=str(library/'libOSMesa.so.8'),LD_LIBRARY_PATH=str(library))
        child_env.update(GALLIUM_DRIVER='softpipe',N810_MBX_DEVICE='1',N810_MBX_GPU_VERTEX='1',N810_MBX_EXPERIMENTAL_SCISSOR='1',N810_MBX_EXPERIMENTAL_2D='1',N810_MBX_MULTI_TEXTURE='1',N810_MBX_NATIVE32_LAYOUT='bgra',N810_MBX_EXPERIMENTAL_BLEND='1',N810_MBX_EXPERIMENTAL_TEXTURE='1',N810_MBX_TEXTURE_CACHE='1',N810_MBX_TEMPLATE='0',N810_MBX_ASYNC='0',N810_MBX_SHARED_IMAGE='0',N810_MBX_SEPARATE_ALPHA='1',N810_MBX_LINEAR_TEXTURE='1',N810_MBX_SURFACE_CHECKPOINT='1')
        child_env.update(N810_MBX_RESERVED_RESOURCES='1',N810_MBX_OPAQUE_BLEND_COPY='1',N810_MBX_SURFACE_RECOVERY='1',N810_SYMBIAN_BATCH_REGION_STATE='1',N810_SYMBIAN_MASK_CACHE='1',N810_SYMBIAN_REGION_REJECT='1',N810_SYMBIAN_GPU_MASK='1',N810_SYMBIAN_REGION_SCISSOR='1',N810_SYMBIAN_AFFINE_FILTER='1',N810_SYMBIAN_QUIET_DRAWS='1',N810_SYMBIAN_BATCH_CACHE_HITS='0',N810_MBX_TEXTURE_RESIDENCY='0',N810_MBX_RETAINED_TEXTURE_REUSE='0')
        child_env.update(N810_SYMBIAN_CPU='native',N810_SYMBIAN_FIXED_FUNCTION='gpu',N810_SYMBIAN_AUDIO='none',N810_SYMBIAN_FAST_TLS='1',N810_SYMBIAN_DIRECT_PRESENT='top-down',N810_SYMBIAN_FB_FD=str(fb),N810_SYMBIAN_DISPLAY_GRANT_FD=str(reader),N810_SYMBIAN_KEYBOARD_FD=str(keyboard),N810_MBX_RENDER_FD=str(gpu),N810_SYMBIAN_WORKER_PREFIX=str(Path(account.pw_dir)/'.local/share/symbian-private/runtime/native-workers'))
        os.write(writer,b'G')
        child=subprocess.Popen(argv,env=child_env,stdin=tty,preexec_fn=drop,pass_fds=(fb,gpu,reader,keyboard))
        started(child)
        return child.wait()
    finally:
        os.close(reader);os.close(writer)
        if keyboard>=0:os.close(keyboard)
