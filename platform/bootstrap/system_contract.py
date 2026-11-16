"""Reject a staged internal image with an incomplete system dependency closure."""
import hashlib
import os
from pathlib import Path

# Deliberately excludes personal state, identities, pairing records and map data.
COMMANDS = {
 '/usr/local/sbin/n810-provision',
 '/usr/local/sbin/n810-wake', '/usr/local/sbin/n810-console-power-menu',
 '/usr/local/sbin/n810-power-overlay', '/usr/local/sbin/n810-screen',
 '/usr/local/sbin/n810-mode', '/usr/local/sbin/n810-radio',
 '/usr/local/sbin/n810-cpu-policy', '/usr/local/bin/n810-power',
 '/usr/local/sbin/n810-displayd', '/usr/local/sbin/n810-rnode-configure',
 '/usr/local/sbin/n810-rnode-spp-prepare', '/usr/local/sbin/n810-wifi-service',
 '/usr/bin/openvt', '/usr/bin/whiptail', '/usr/bin/flock', '/usr/bin/timeout',
 '/usr/bin/bluetoothctl', '/usr/bin/rfcomm', '/usr/bin/fuser', '/usr/bin/rsync',
 '/usr/sbin/chronyd', '/etc/init.d/chrony', '/etc/init.d/bluetooth',
 '/etc/init.d/n810-wifi', '/etc/init.d/n810-wake',
}
FILES = {
 '/usr/local/lib/n810-platform/rnode_spp_prepare.py',
 '/etc/sudoers.d/n810-power', '/etc/sudoers.d/n810-radio',
 '/usr/local/lib/n810-radio/n810-aprs-feed.py',
 '/usr/local/lib/n810-radio/uvpro-aprs-listen.py',
 '/usr/local/lib/n810-radio/n810-aprs-directory.py',
}


def resolve(root, name):
    """Resolve Linux absolute links inside the build root, never against the host."""
    pending=list(Path(name).parts[1:]);done=[];links=0
    while pending:
        part=pending.pop(0)
        if part=='.':continue
        if part=='..':
            if done:done.pop()
            continue
        p=root.joinpath(*done,part)
        if p.is_symlink():
            links+=1
            if links>40:raise ValueError('System dependency symlink loop: '+name)
            target=p.readlink()
            if target.is_absolute():done=[]
            pending=list(target.parts[1:] if target.is_absolute() else target.parts)+pending
        else:done.append(part)
    return root.joinpath(*done)


def validate(root):
    root=Path(root);manifest={}
    for name in sorted(COMMANDS|FILES):
        p=resolve(root,name)
        if not p.is_file():raise ValueError('Missing system dependency: '+name)
        info=p.stat()
        if os.geteuid()==0 and info.st_uid!=0:raise ValueError('System dependency is not root-owned: '+name)
        mode=info.st_mode
        if mode&0o022:raise ValueError('System dependency is writable by group/others: '+name)
        if name in COMMANDS and not mode&0o111:raise ValueError('System command is not executable: '+name)
        manifest[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    groups={line.split(':')[0]:line.split(':')[-1].split(',') for line in (root/'etc/group').read_text().splitlines()}
    for name in ('n810-power','n810-radio','dialout','bluetooth'):
        if 'nokia' not in groups.get(name,[]):raise ValueError('Missing nokia system group: '+name)
    for runlevel in (2,3,4,5):
        directory=root/f'etc/rc{runlevel}.d'
        if not list(directory.glob('S??n810-wake')):raise ValueError('Wake event owner is not enabled')
        if list(directory.glob('S??n810-display-keys')):raise ValueError('Duplicate Power/brightness event owner')
    return manifest
