"""Start/reuse the existing cached-API producer; never read its credentials here."""
import os
from pathlib import Path
import stat
import subprocess
import sys


def ensure(sources, output, access=None):
    output=Path(output).expanduser().resolve()
    access=Path(access).expanduser() if access else output.parent/'api-access.json'
    if not access.exists():return False
    info=access.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
        raise ValueError('Radio API access file must be private and owned by you.')
    script=Path(sources)/'radio-snapshot-source.py'
    if not script.is_file():raise ValueError('Existing radio snapshot updater is unavailable.')
    output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    info=output.parent.stat()
    if info.st_uid!=os.getuid() or info.st_mode&0o077:
        raise ValueError('Radio snapshot directory must be private and owned by you.')
    fd=os.open(output.parent/(output.name+'.updater.log'),os.O_CREAT|os.O_APPEND|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
            raise ValueError('Radio updater log must be private and owned by you.')
        process=subprocess.Popen([sys.executable,str(script),'--access',str(access),'--output',str(output),'--watch'],
                                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=fd,
                                 start_new_session=True,close_fds=True)
    finally:os.close(fd)
    try:code=process.wait(timeout=.1)
    except subprocess.TimeoutExpired:return True
    if code:raise RuntimeError('Radio snapshot updater could not start; retained observations remain available.')
    return True  # The existing owner already holds the producer lock.
