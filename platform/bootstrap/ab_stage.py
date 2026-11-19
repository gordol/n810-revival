#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stage read-only slot startup and explicit persistent state, separate from OS code."""
import json
from pathlib import Path
import shutil
import subprocess
from ab_runtime import atomic, digest

HERE = Path(__file__).resolve().parent


def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['cp', '-a', str(source), str(target)], check=True)


def stage(root, data, kernel, c):
    root, data, kernel = map(Path, (root, data, kernel))
    if json.loads((kernel/'BUILD.json').read_text()).get('boot_method') != 'same-kernel-root-switch':
        raise ValueError('Rebuild with --ab-boot for same-kernel root selection')
    config = root/'etc/n810-ab'; config.mkdir(parents=True, exist_ok=True)
    atomic(config/'config.json', c)
    executable = root/'usr/local/sbin/n810-ab'
    shutil.copy2(HERE/'ab_runtime.py', executable); executable.chmod(0o755)
    (root/'etc/default/kexec').write_text('LOAD_KEXEC=false\nUSE_KEXEC=false\n')
    # Persist user state and service databases, never package-manager metadata or app code.
    paths = ['etc/n810-ab/config.json', 'home', 'root', 'var/log', 'var/spool', 'etc/wpa_supplicant', 'etc/n810',
             'etc/default', 'etc/network', 'etc/bluetooth', 'var/lib/pocket', 'var/lib/n810-radio',
             'var/lib/n810-maintenance', 'var/lib/n810-bluetooth', 'var/lib/bluetooth', 'var/lib/dhcp', 'var/lib/chrony', 'var/lib/dbus']
    excluded = {'dpkg', 'apt', 'ucf', 'initramfs-tools', 'systemd', 'debconf'}
    paths += [str(p.relative_to(root)) for p in sorted((root/'var/lib').iterdir()) if p.name not in excluded]
    paths += ['etc/'+n for n in ('passwd','shadow','group','gshadow','machine-id','hostname','n810-idle.conf') if (root/'etc'/n).exists()]
    paths += [str(p.relative_to(root)) for p in root.glob('etc/n810-*.conf')]
    paths += ['etc/ssh/ssh_host_ed25519_key', 'etc/ssh/ssh_host_ed25519_key.pub']
    paths=sorted(set(paths))
    for relative in paths:
        src = root/relative; dst = data/relative
        if src.exists() or src.is_symlink(): copy(src, dst)
        elif relative.endswith(('key', 'key.pub')): dst.parent.mkdir(parents=True, exist_ok=True)
        else: dst.mkdir(parents=True, exist_ok=True)
    # Generate a unique persistent SSH identity without placing private keys in an OS slot.
    subprocess.run(['chroot',str(root),'/usr/bin/ssh-keygen','-q','-t','ed25519','-N','','-f','/tmp/n810-ab-hostkey'],check=True)
    for suffix in ('','.pub'):
        shutil.move(root/('tmp/n810-ab-hostkey'+suffix),data/('etc/ssh/ssh_host_ed25519_key'+suffix))
    data.chmod(0o755)
    atomic(data/'SCHEMA.json', {'version':c['data_schema']})
    (config/'persistent-paths').write_text('\n'.join(paths)+'\n')
    # Templates live on the immutable image. /etc and /var are volatile views;
    # only the declared state is linked into the persistent data filesystem.
    health=root/'usr/local/sbin/n810-ab-health'
    shutil.copy2(HERE/'ab_health.py',health);health.chmod(0o755)
    init=root/'etc/init.d/n810-ab-health'
    init.write_text('#!/bin/sh\ncase "$1" in start) /usr/local/sbin/n810-ab-health >>/var/log/n810-ab-health.log 2>&1 &;; esac\n');init.chmod(0o755)
    for level in (2,3,4,5):
        (root/f'etc/rc{level}.d/S09n810-ab-health').symlink_to('../init.d/n810-ab-health')
    swap = root/'etc/init.d/n810-sd-swap'
    shutil.copyfile(HERE/'ab_sd_swap.sh', swap)
    swap.chmod(0o755)
    for level in (2,3,4,5):
        (root/f'etc/rc{level}.d/S02n810-sd-swap').symlink_to('../init.d/n810-sd-swap')
    template = root/'usr/lib/n810-ab'; template.mkdir(parents=True, exist_ok=True)
    copy(root/'etc', template/'etc')
    copy(root/'var', template/'var')
    prepare=template/'prepare-data'
    shutil.copy2(HERE/'ab_prepare_data.sh',prepare);prepare.chmod(0o755)
    for relative in ('var/cache/apt/archives', 'var/log', 'var/tmp'):
        p=template/relative
        if p.exists(): shutil.rmtree(p)
        p.mkdir(parents=True)
    for name in ('data', 'old-root', 'proc', 'sys', 'dev', 'run'):
        (root/name).mkdir(exist_ok=True)
    script = root/'sbin/n810-slot-init'
    shutil.copy2(HERE/'ab_slot_init.sh',script); script.chmod(0o755)
    # The package's fstab must not remount the immutable slot writable.
    for base in (root, template):
        (base/'etc/fstab').write_text('# A/B root and data are mounted by n810-slot-init.\n')
        for p in base.glob('etc/rc*.d/*pocket-expand-internal-root'): p.unlink()
        defaults=base/'etc/default/rcS'
        with defaults.open('a') as f: f.write('\nRAMTMP=yes\nRAMLOCK=yes\n')
    # Seed-only settings and identities belong exclusively to data, not update images.
    for base in (root,template):
        for relative in paths:
            if not relative.startswith(('etc/','var/')):continue
            p=base/relative
            if p.is_dir() and not p.is_symlink():shutil.rmtree(p)
            elif p.exists() or p.is_symlink():p.unlink()
            p.parent.mkdir(parents=True,exist_ok=True);p.symlink_to('/data/'+relative)
    boot=root/'boot'; boot.mkdir(exist_ok=True)
    for name in ('zImage','omap2420-n810.dtb'): shutil.copy2(kernel/name,boot/name)
    atomic(boot/'n810-slot.json', {'data_schema':c['data_schema'],
        'kernel_release':(kernel/'KERNELRELEASE').read_text().strip(),
        'boot_method':'same-kernel-root-switch', 'kernel_notes_sha256':digest(kernel/'kernel.notes'),
        'files':{n:digest(boot/n) for n in ('zImage','omap2420-n810.dtb')}})


def recovery(root, c):
    root=Path(root)
    cfg=root/'etc/n810-ab'; cfg.mkdir(parents=True, exist_ok=True)
    atomic(cfg/'config.json',c); (cfg/'recovery').touch()
    target=root/'usr/local/sbin/n810-ab'
    shutil.copy2(HERE/'ab_runtime.py',target); target.chmod(0o755)
    # Recovery boots normally without a card and provides USB SSH and a local login.
    for pattern in ('*pocket-desktop','*pocket-services','*n810-setup-touch','*pocket-expand-internal-root'):
        for p in root.glob('etc/rc*.d/'+pattern): p.unlink()
    for p in root.glob('etc/rc*.d/*n810-ab-boot'): p.unlink()
    (root/'etc/init.d/n810-ab-boot').unlink(missing_ok=True)
    (root/'new-root').mkdir(exist_ok=True)
    lib=root/'usr/lib/n810-ab'; lib.mkdir(parents=True,exist_ok=True)
    for name in ('ab_early.py', 'ab_runtime.py'):
        shutil.copy2(HERE/name, lib/name)
    script=root/'sbin/n810-recovery-init'
    script.write_text('#!/bin/sh\nexec /usr/bin/python3 /usr/lib/n810-ab/ab_early.py\n')
    script.chmod(0o755)
    (root/'etc/default/kexec').write_text('LOAD_KEXEC=false\nUSE_KEXEC=false\n')
