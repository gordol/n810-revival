"""Install the reviewed Nokia network hardening files with rollback on failure."""
from datetime import datetime,timezone
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys


HERE=Path(__file__).resolve().parent
SSHD=Path('/etc/ssh/sshd_config.d/10-n810-usb-recovery.conf')
SYSCTL=Path('/etc/sysctl.d/60-n810-radio-hardening.conf')
BACKUPS=Path('/var/backups/n810-radio-hardening')


def protected_file(path):
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
        raise ValueError('Unsafe existing configuration: '+str(path))


def write_file(path,raw):
    path.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    temporary=path.with_name('.'+path.name+'.'+str(os.getpid()))
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.chown(temporary,0,0);os.chmod(temporary,0o644);os.replace(temporary,path)
        directory=os.open(path.parent,os.O_RDONLY|os.O_CLOEXEC)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if temporary.exists():temporary.unlink()


def effective_password(local_address):
    result=subprocess.check_output(['/usr/sbin/sshd','-T','-C',
        'user=nokia,host=n810,addr=192.168.10.2,laddr='+local_address+',lport=22'],text=True)
    values=dict(line.split(None,1) for line in result.splitlines() if ' ' in line)
    return values.get('passwordauthentication')


def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        raise SystemExit('Run as root without arguments')
    payloads={SSHD:(HERE/SSHD.name).read_bytes(),SYSCTL:(HERE/SYSCTL.name).read_bytes()}
    previous={}
    for path in payloads:
        if path.exists() or path.is_symlink():protected_file(path);previous[path]=path.read_bytes()
        else:previous[path]=None
    backup=BACKUPS/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup.mkdir(mode=0o700,parents=True)
    for path,raw in previous.items():
        if raw is not None:
            target=backup/path.name;target.write_bytes(raw);target.chmod(0o600)
    try:
        for path,raw in payloads.items():write_file(path,raw)
        subprocess.run(['/usr/sbin/sshd','-t'],check=True)
        if effective_password('192.168.10.1')!='yes' or effective_password('10.10.30.80')!='no':
            raise RuntimeError('SSH address policy did not take effect')
        subprocess.run(['/usr/sbin/sysctl','--system'],check=True)
        subprocess.run(['/usr/sbin/service','ssh','reload'],check=True)
    except BaseException:
        for path,raw in previous.items():
            if raw is None:path.unlink(missing_ok=True)
            else:write_file(path,raw)
        subprocess.run(['/usr/sbin/sshd','-t'],check=False)
        subprocess.run(['/usr/sbin/sysctl','--system'],check=False)
        raise
    print('Nokia radio/network hardening installed; backup: '+str(backup))


if __name__=='__main__':main()
