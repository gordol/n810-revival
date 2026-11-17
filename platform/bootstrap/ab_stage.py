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
    if not json.loads((kernel/'BUILD.json').read_text()).get('ab_boot'):
        raise ValueError('Rebuild with --ab-boot; forced root command lines cannot select slots')
    config = root/'etc/n810-ab'; config.mkdir(parents=True, exist_ok=True)
    atomic(config/'config.json', c)
    executable = root/'usr/local/sbin/n810-ab'
    shutil.copy2(HERE/'ab_runtime.py', executable); executable.chmod(0o755)
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
    template = root/'usr/lib/n810-ab'; template.mkdir(parents=True, exist_ok=True)
    copy(root/'etc', template/'etc')
    copy(root/'var', template/'var')
    prepare=template/'prepare-data'
    shutil.copy2(HERE/'ab_prepare_data.sh',prepare);prepare.chmod(0o755)
    for relative in ('var/cache/apt/archives', 'var/log', 'var/tmp'):
        p=template/relative
        if p.exists(): shutil.rmtree(p)
        p.mkdir(parents=True)
    (root/'data').mkdir(exist_ok=True)
    script = root/'sbin/n810-slot-init'
    script.write_text('''#!/bin/sh
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
fail() { echo "A/B startup failed: $*; reboot to internal recovery or use this console."; while :; do /bin/sh; done; }
mountpoint -q /proc || mount -t proc proc /proc || fail proc
mountpoint -q /sys || mount -t sysfs sysfs /sys || fail sys
mountpoint -q /dev || mount -t devtmpfs devtmpfs /dev || fail dev
mountpoint -q /run || mount -t tmpfs -o mode=755,size=16m tmpfs /run || fail run
mount -t tmpfs -o mode=1777,size=16m tmpfs /tmp || fail tmp
exec </dev/console >/dev/console 2>&1
DATA=
for arg in $(cat /proc/cmdline); do case "$arg" in n810.data=PARTUUID=????????-04) DATA=${arg#n810.data=};; esac; done
[ -n "$DATA" ] || fail 'missing data identity'
for n in 1 2 3 4 5 6 7 8 9 10; do
 DEV=$(blkid -t "$DATA" -o device)
 [ -b "$DEV" ] && break
 sleep 1
done
[ -b "$DEV" ] || fail 'data partition absent or ambiguous'
/usr/lib/n810-ab/prepare-data "$DEV" || fail 'data filesystem recovery or expansion'
mount -t ext4 -o rw,noatime "$DEV" /data || fail 'data mount'
test -s /data/etc/ssh/ssh_host_ed25519_key || ssh-keygen -q -t ed25519 -N '' -f /data/etc/ssh/ssh_host_ed25519_key || fail 'SSH identity'
test "$(python3 -c 'import json; print(json.load(open("/data/SCHEMA.json"))["version"])')" = 1 || fail 'data schema'
mkdir -p /data/etc-overlay/upper /data/etc-overlay/work || fail 'configuration storage'
mount -t overlay overlay -o lowerdir=/usr/lib/n810-ab/etc,upperdir=/data/etc-overlay/upper,workdir=/data/etc-overlay/work /etc || fail 'persistent configuration overlay'
mount -t tmpfs -o mode=755,size=32m tmpfs /var || fail var
cp -a /usr/lib/n810-ab/var/. /var/ || fail 'var defaults'
while IFS= read -r path; do
 case "$path" in etc/*) :;;
 home|root) mount --bind "/data/$path" "/$path" || fail "$path";;
 *) rm -rf "/$path"; ln -s "/data/$path" "/$path" || fail "$path";; esac
done < /etc/n810-ab/persistent-paths
exec /sbin/init
'''); script.chmod(0o755)
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
    script=root/'etc/init.d/n810-ab-boot'
    script.write_text('''#!/bin/sh
case "$1" in
start)
 echo 'N810 recovery: SD boot starts in 10 seconds; create /run/n810-stay-in-recovery to stay.'
 (sleep 10; test -e /run/n810-stay-in-recovery || test "$(/usr/local/sbin/n810-mode status)" = charging || /usr/local/sbin/n810-ab boot >>/var/log/n810-ab-boot.log 2>&1) &
 ;;
stop) :;;
esac
''');script.chmod(0o755)
    for level in (2,3,4,5):
        (root/f'etc/rc{level}.d/S07n810-ab-boot').symlink_to('../init.d/n810-ab-boot')
    # kexec-tools uses the orderly shutdown path recovered from the original device.
    (root/'etc/default/kexec').write_text('LOAD_KEXEC=false\nUSE_KEXEC=true\n')
