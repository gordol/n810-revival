"""Serialize Pocket and native Symbian applications under one graphics owner."""
import os
import re
import select
import signal
import stat
import socket
import struct
import subprocess
from pathlib import Path
from symbian_catalog import resolve,packages

APPS={'chess':'ChessGenius_20036D63.exe','snakes':'6r45_1b.exe'}

class Session:
    def __init__(self,directory,uid,gid,windows=None):
        self.path=Path(directory)/'symbian.sock';self.uid=uid;self.windows=windows
        if self.path.exists():raise RuntimeError('Symbian launch socket already exists')
        self.server=socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        self.server.bind(str(self.path));os.chown(self.path,uid,gid);os.chmod(self.path,0o600)
        self.server.listen(1)
    def wait(self,child,ready):
        """Wait for process exit or a validated request; never poll the device."""
        pidfd=os.pidfd_open(child.pid)
        try:
            while True:
                readable,_,_=select.select([pidfd,self.server,*self.windows.sources()] if self.windows else [pidfd,self.server],[],[])
                if self.windows:self.windows.service(readable)
                if pidfd in readable:return None
                if self.server not in readable:continue
                with self.server.accept()[0] as request:
                    request.settimeout(2)
                    _,uid,_=struct.unpack('3i',request.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    try:
                        application=request.recv(256).decode('ascii')
                        if application.startswith('window:'):
                            if uid!=self.uid or not re.fullmatch(r'window:[0-9a-f]{8}',application,re.I):raise ValueError('Invalid Symbian window request')
                            if self.windows is None:raise RuntimeError('GPU window broker is not enabled')
                            self.windows.start(application[7:],request);continue
                        if uid!=self.uid or (application not in APPS and not re.fullmatch(r'(?:[0-9a-f]{8}|install:[A-Za-z0-9 _().-]{1,160}\.sisx?)',application,re.I)):raise ValueError('Invalid Symbian request')
                        if self.windows and self.windows.active is not None:raise RuntimeError('Close the Symbian window before a fullscreen launch or installation')
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

def command(application,home,code=None):
    private=Path(home)/'.local/share/symbian-private'
    code=Path(code) if code is not None else private/'code'
    executable=code/'symbian-runtime';root=private/'runtime'
    if not executable.is_file() or not (code/'lib/libOSMesa.so.8').is_file():
        raise RuntimeError('Install the matching native runtime and private Mesa library first')
    if application.startswith('install:'):
        package=next((p for p in packages(home) if p['id']==application),None)
        if package is None:raise ValueError('Installer is missing from the private inbox')
        return [str(executable),str(root),'--catalog','900',package['path']]
    entry=resolve(application,home)
    if entry is None:raise ValueError('Unknown or uninstalled Symbian application')
    return [str(executable),str(root),entry['path'],'900']

def keyboard_device():
    names=[p.parent.parent.name for p in Path('/sys/class/input').glob('event*/device/name') if p.read_text().strip()=='N810 internal keyboard']
    if len(names)!=1:raise RuntimeError('Expected one N810 internal keyboard')
    return '/dev/input/'+names[0]

def environment(home,env,code=None):
    child_env={k:v for k,v in env.items() if not k.startswith(('POCKET_','N810_SYMBIAN_','N810_MBX_'))}
    for name in ('N810_MBX_DESKTOP_TARGET','N810_MBX_WINDOW_IMAGES','N810_MBX_RESOURCE_REFERENCES','N810_MBX_TEXTURE_SUBSET','N810_MBX_TEXTURE_RESIDENCY'):
        child_env.pop(name,None)
    library=Path(code)/'lib' if code is not None else Path(home)/'.local/share/symbian-private/code/lib'
    child_env.update(LD_PRELOAD=str(library/'libOSMesa.so.8'),LD_LIBRARY_PATH=str(library))
    child_env.update(GALLIUM_DRIVER='softpipe',N810_MBX_DEVICE='1',N810_MBX_GPU_VERTEX='1',N810_MBX_EXPERIMENTAL_SCISSOR='1',N810_MBX_EXPERIMENTAL_2D='1',N810_MBX_MULTI_TEXTURE='1',N810_MBX_NATIVE32_LAYOUT='bgra',N810_MBX_EXPERIMENTAL_BLEND='1',N810_MBX_EXPERIMENTAL_TEXTURE='1',N810_MBX_TEXTURE_CACHE='1',N810_MBX_TEMPLATE='0',N810_MBX_ASYNC='0',N810_MBX_SHARED_IMAGE='0',N810_MBX_SEPARATE_ALPHA='1',N810_MBX_LINEAR_TEXTURE='1',N810_MBX_SURFACE_CHECKPOINT='1')
    child_env.update(N810_MBX_RESERVED_RESOURCES='1',N810_MBX_OPAQUE_BLEND_COPY='1',N810_MBX_SURFACE_RECOVERY='1',N810_SYMBIAN_BATCH_REGION_STATE='1',N810_SYMBIAN_SPRITE_BATCH='1',N810_SYMBIAN_BATCH_LISTS='0',N810_SYMBIAN_MASK_CACHE='1',N810_SYMBIAN_REGION_REJECT='1',N810_SYMBIAN_GPU_MASK='1',N810_SYMBIAN_REGION_SCISSOR='1',N810_SYMBIAN_AFFINE_FILTER='1',N810_SYMBIAN_QUIET_DRAWS='1',N810_MBX_TEXTURE_RESIDENCY='0',N810_MBX_RETAINED_TEXTURE_REUSE='0')
    child_env.update(N810_SYMBIAN_CPU='native',N810_SYMBIAN_FIXED_FUNCTION='gpu',N810_SYMBIAN_AUDIO='none',N810_SYMBIAN_FAST_TLS='1',N810_SYMBIAN_COMPACT_ATLAS='1',N810_SYMBIAN_COMPACT_COMMANDS='1',N810_SYMBIAN_WORKER_PREFIX=str(Path(home)/'.local/share/symbian-private/runtime/native-workers'))
    return child_env

def session_log(account,name='session.log'):
    """Open only a private user-owned directory, without following symlinks."""
    directory=os.open(account.pw_dir,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        for component in ('.local','share','symbian-private','runtime'):
            child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
            os.close(directory);directory=child
            if os.fstat(directory).st_uid!=account.pw_uid:raise PermissionError('Private runtime directory owner mismatch')
        try:previous=os.stat(name,dir_fd=directory,follow_symlinks=False)
        except FileNotFoundError:previous=None
        if previous is not None:
            if not stat.S_ISREG(previous.st_mode) or previous.st_uid!=account.pw_uid or previous.st_nlink!=1:raise PermissionError('Unsafe runtime log')
            os.rename(name,name.removesuffix('.log')+'.previous.log',src_dir_fd=directory,dst_dir_fd=directory)
        fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=directory)
        try:os.fchown(fd,account.pw_uid,account.pw_gid)
        except BaseException:os.close(fd);raise
        return os.fdopen(fd,'w')
    finally:os.close(directory)

def run(application,account,fb,gpu,env,tty,drop,started=lambda child:None):
    argv=command(application,account.pw_dir)
    reader,writer=os.pipe2(os.O_CLOEXEC)
    keyboard=-1
    try:
        keyboard=os.open(keyboard_device(),os.O_RDONLY|os.O_NONBLOCK|os.O_CLOEXEC)
        child_env=environment(account.pw_dir,env)
        child_env.update(N810_SYMBIAN_DIRECT_PRESENT='top-down',N810_SYMBIAN_FB_FD=str(fb),N810_SYMBIAN_DISPLAY_GRANT_FD=str(reader),N810_SYMBIAN_KEYBOARD_FD=str(keyboard),N810_MBX_RENDER_FD=str(gpu))
        os.write(writer,b'G')
        # Keep startup, guest-exit and fatal diagnostics off the physical console.
        # Two session files retain the preceding failure across relaunches.
        with session_log(account) as log:
            child=subprocess.Popen(argv,env=child_env,stdin=tty,stdout=log,stderr=subprocess.STDOUT,preexec_fn=drop,pass_fds=(fb,gpu,reader,keyboard))
            started(child)
            result=child.wait()
            log.write('launcher_exit_status='+str(result)+'\n')
            return result
    finally:
        os.close(reader);os.close(writer)
        if keyboard>=0:os.close(keyboard)
