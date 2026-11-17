#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stage an isolated console/SSH bootstrap; normal slot graphics remain unchanged."""
import json
from pathlib import Path
import shutil
import subprocess
from ab_runtime import digest

SCRIPT='''#!/bin/sh
set -eu
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
[ "$(uname -r)" = "@RELEASE@" ]
case " $(cat /proc/cmdline) " in *" n810.install=sd "*) :;; *) exit 1;; esac
echo 'Pocket SD installer: internal storage unchanged; starting USB SSH.'
# Slot init has mounted persistent data. This installer runs no Pocket/radio services.
for device in /dev/watchdog /dev/watchdog0; do
 if [ -c "$device" ]; then /bin/busybox watchdog -T 60 -t 15 "$device" & break; fi
done
mount -t tmpfs -o mode=700,size=1m tmpfs /root
mkdir -m 700 /root/.ssh
cp /home/nokia/.ssh/authorized_keys /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys
# Permit key-only root access in this temporary environment; do not alter saved accounts.
python3 - <<'SHADOW'
from pathlib import Path
rows=Path('/etc/shadow').read_text().splitlines()
password=next(r.split(':')[1] for r in rows if r.startswith('nokia:'))
assert password and password[0] not in '! *'
Path('/run/bootstrap.shadow').write_text('\\n'.join('root:'+password+':'+':'.join(r.split(':')[2:]) if r.startswith('root:') else r for r in rows)+'\\n')
Path('/run/bootstrap.shadow').chmod(0o600)
SHADOW
mount --bind /run/bootstrap.shadow /etc/shadow
/usr/bin/dropbearconvert openssh dropbear /etc/ssh/ssh_host_ed25519_key /run/bootstrap.hostkey
modprobe tusb6010
modprobe musb_hdrc
for n in 1 2 3 4 5 6 7 8 9 10; do
 if ip link show usb0 >/dev/null 2>&1; then break; fi
 sleep 1
done
ip address replace 169.254.81.1/16 dev usb0
ip link set usb0 up
touch /run/n810-sd-installer
/usr/sbin/dropbear -s -j -k -F -E -r /run/bootstrap.hostkey &
echo 'SD installer ready on USB 169.254.81.1; waiting for laptop.'
while :; do /bin/sh; sleep 1; done
'''


def stage(root, package):
    root,package=Path(root),Path(package)
    report=json.loads((package/'BUILD.json').read_text())
    if report.get('kind')!='n810-sd-installer-kernel' or not report['release'].endswith('-n810-sd-installer'):
        raise ValueError('A separately identified SD installer kernel is required')
    exports={r.split()[1]:r.split()[0] for r in (package/'Module.symvers').read_text().splitlines()}
    source=package/'root/lib/modules'/report['release'];checks=0
    modules=list(source.rglob('*.ko'))
    if not modules or len(modules)!=report['kernel_modules']:
        raise ValueError('Incomplete bootstrap module package')
    for module in modules:
        for row in subprocess.check_output(['modprobe','--dump-modversions',str(module)],text=True).splitlines():
            crc,name=row.split()
            if exports.get(name)!=crc:raise ValueError('Bootstrap module ABI mismatch: '+module.name+' '+name)
            checks+=1
    target=root/'lib/modules'/report['release']
    shutil.copytree(source,target,symlinks=True)
    script=root/'usr/local/sbin/n810-sd-installer'
    script.write_text(SCRIPT.replace('@RELEASE@',report['release']));script.chmod(0o755)
    subprocess.run(['sh','-n',str(script)],check=True)
    init=root/'sbin/n810-slot-init';text=init.read_text()
    before='exec /sbin/init\n'
    if text.count(before)!=1:raise ValueError('Unexpected slot init')
    text=text.replace(before,'case " $(cat /proc/cmdline) " in *" n810.install=sd "*) exec /usr/local/sbin/n810-sd-installer;; esac\n'+before)
    init.write_text(text)
    for name in ('usr/sbin/dropbear','usr/bin/dropbearconvert','bin/busybox'):
        if not (root/name).is_file():raise ValueError('Missing bootstrap tool: '+name)
    return dict(release=report['release'],module_crc_checks=checks,kernel_sha256=digest(package/'zImage-omap2420-n810'))
