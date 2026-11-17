# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile
p=argparse.ArgumentParser(description='Build the private RAM environment for the automatic N810 internal installer.')
for name in ('rootfs','module-root','kernel-build','kernel','busybox-package','owner-key','output'):
 p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args()
config=(a.kernel_build/'.config').read_text()
if (not all(flag in config for flag in ('CONFIG_BLK_DEV_INITRD=y\n','CONFIG_RD_XZ=y\n')) or
        'root=/dev/ram0 rw rdinit=/init' not in config):
 raise ValueError('RAM installer requires NOLO external initramfs and XZ support')
os.umask(0o077)
a.output.mkdir(parents=True,exist_ok=False)
root=a.rootfs.resolve();Path('/work').mkdir(exist_ok=True)
out=Path(tempfile.mkdtemp(prefix='n810-ram-',dir='/work'))
if a.kernel.stat().st_size>2097152:raise ValueError('Installer kernel exceeds the NOLO 2 MiB limit')
subprocess.run(['dpkg-deb','-x',str(a.busybox_package),str(out)],check=True)
for name in ('bin','sbin','usr/bin','usr/sbin','proc','sys','dev','tmp','run','root/.ssh','etc/dropbear','mnt'):
 (out/name).mkdir(parents=True,exist_ok=True)
for program in ('usr/sbin/dropbear','usr/bin/dropbearkey'):
 source=root/program;target=out/program;shutil.copy2(source,target)
 deps=subprocess.check_output(['chroot',str(root),'/usr/bin/ldd','/'+program],text=True)
 for path in re.findall(r'(?:=>\s+|^\s*)(/[^\s]+)',deps,re.M):
  target=out/path.lstrip('/');target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/path.lstrip('/'),target)
  target.chmod(0o755)
subprocess.run(['chroot',str(out),'/bin/busybox','--install','-s'],check=True)
release=(a.kernel_build/'include/config/kernel.release').read_text().strip()
module_root=a.module_root.resolve()
module_dir=out/'lib/modules'/release;module_dir.mkdir(parents=True,exist_ok=True)
exports={line.split()[1]:line.split()[0] for line in (a.kernel_build/'Module.symvers').read_text().splitlines()}
for source in (module_root/'lib/modules'/release).glob('modules.*'):
 if source.is_file():shutil.copy2(source,module_dir/source.name)
for module in ('tusb6010','musb_hdrc'):
 deps=subprocess.check_output(['modprobe','--show-depends','-d',str(module_root),'-S',release,module],text=True)
 for line in deps.splitlines():
  if line.startswith('insmod '):
   source=Path(line.split()[1])
   versions=subprocess.check_output(['modprobe','--dump-modversions',str(source)],text=True)
   if any(exports.get(row.split()[1])!=row.split()[0] for row in versions.splitlines()):
    raise ValueError('Installer USB module does not match kernel: '+source.name)
   target=out/source.relative_to(module_root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
(out/'etc/passwd').write_text('root::0:0:Installer:/root:/bin/sh\n')
(out/'etc/pocket-installer').write_text('Pocket RAM installer version 1\n')
(out/'etc/group').write_text('root:x:0:\n')
(out/'etc/shells').write_text('/bin/sh\n')
(out/'root/.ssh/authorized_keys').write_text(__import__('build_sd').public_key(a.owner_key));(out/'root/.ssh').chmod(0o700);(out/'root/.ssh/authorized_keys').chmod(0o600)
if not (out/'etc/dropbear/dropbear_ed25519_host_key').exists():
 subprocess.run(['chroot',str(out),'/usr/bin/dropbearkey','-t','ed25519','-f','/etc/dropbear/dropbear_ed25519_host_key'],check=True,stdout=subprocess.DEVNULL)
pub=subprocess.check_output(['chroot',str(out),'/usr/bin/dropbearkey','-y','-f','/etc/dropbear/dropbear_ed25519_host_key'],text=True)
(a.output/'installer-host.pub').write_text(next(line for line in pub.splitlines() if line.startswith('ssh-ed25519 '))+'\n')
(out/'init').write_text('''#!/bin/sh
export PATH=/bin:/sbin:/usr/bin:/usr/sbin
mount -t proc proc /proc
mount -t sysfs sysfs /sys
mount -t devtmpfs devtmpfs /dev
mkdir -p /dev/pts /run /tmp
mount -t devpts devpts /dev/pts
exec </dev/console >/dev/console 2>&1
echo 'Pocket automatic installer: running from RAM; internal storage unchanged.'
for device in /dev/watchdog /dev/watchdog0; do
 if [ -c "$device" ]; then
  watchdog -T 60 -t 15 "$device" &
  echo "Hardware watchdog keepalive active on $device."
  break
 fi
done
modprobe tusb6010
modprobe musb_hdrc
for i in 1 2 3 4 5 6 7 8 9 10; do
 ifconfig usb0 169.254.81.1 netmask 255.255.0.0 up 2>/dev/null && break
 sleep 1
done
/usr/sbin/dropbear -s -F -E -r /etc/dropbear/dropbear_ed25519_host_key &
echo 'Installer ready on USB 169.254.81.1. Waiting for the host.'
while :; do /bin/sh; sleep 1; done
''');(out/'init').chmod(0o755)
initfs=a.output/'initramfs.cpio.xz'
with initfs.open('wb') as target:
 subprocess.run('find . -print0 | cpio --null -o --format=newc --owner=0:0 | xz --check=crc32 --lzma2=dict=1MiB -c',
                shell=True,cwd=out,stdout=target,check=True)
if initfs.stat().st_size>4194304 or initfs.read_bytes()[:6]!=b'\xfd7zXZ\x00':
 raise ValueError('Installer initramfs exceeds the NOLO 4 MiB limit or is not XZ')
shutil.copy2(a.kernel,a.output/'kernel.bin')
(a.output/'installer-known-hosts').write_text('169.254.81.1 '+(a.output/'installer-host.pub').read_text())
files=('kernel.bin','initramfs.cpio.xz','installer-host.pub','installer-known-hosts')
kernel_report=json.loads((a.kernel.parent/'BUILD.json').read_text())
(a.output/'BUILD.json').write_text(json.dumps(dict(kind='n810-ram-installer',kernel_release=release,
 filesystem_format='cpio-xz',root_device='initramfs:/init',
 kernel_config_sha256=hashlib.sha256((a.kernel_build/'.config').read_bytes()).hexdigest(),
 kernel_source=dict(maintained_commit=kernel_report['maintained_commit'],upstream_sha256=kernel_report['upstream_sha256'],
                    source_lock_sha256=kernel_report['source_lock_sha256']),
 files={n:hashlib.sha256((a.output/n).read_bytes()).hexdigest() for n in files},
 owner_public_key_sha256=hashlib.sha256(a.owner_key.read_bytes()).hexdigest(),device_action=False),indent=2)+'\n')
shutil.rmtree(out)
print('INSTALLER_RAM_IMAGE_BUILT')
