"""Runtime mailbox paths and atomic JSON handoffs. Never creates directories."""
import json
import os
from pathlib import Path
import stat
import tempfile

LIMIT=65536


def runtime_path(name):
    if not isinstance(name,str) or not name or Path(name).name!=name or name in ('.','..'):
        raise ValueError('Mailbox name must be a basename')
    override=os.environ.get('N810_RUNTIME_DIR')
    root=Path(override) if override else Path('/dev/shm')
    if not root.is_absolute():raise ValueError('N810_RUNTIME_DIR must be absolute')
    info=root.lstat()
    if not stat.S_ISDIR(info.st_mode):raise OSError('Runtime path must be an existing directory')
    if override and (info.st_uid!=os.getuid() or info.st_mode&0o077):
        raise OSError('N810_RUNTIME_DIR must be private and owned by this user')
    return root/name


def read_json(name):
    path=runtime_path(name)
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0))
    with os.fdopen(fd,'rb') as f:
        info=os.fstat(f.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
            raise OSError('Mailbox must be a private regular file owned by this user')
        data=f.read(LIMIT+1)
        if len(data)>LIMIT:raise ValueError('Mailbox exceeds 64 KiB')
        return json.loads(data)


def write_json(name,value):
    target=runtime_path(name)
    data=(json.dumps(value,ensure_ascii=True)+'\n').encode()
    if len(data)>LIMIT:raise ValueError('Mailbox exceeds 64 KiB')
    fd,temp=tempfile.mkstemp(prefix='.'+name+'-',dir=target.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data)
        os.replace(temp,target)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return target
