#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build a private internal-MMC install kit from staged Debian and ARM Pocket roots."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
from build_sd import sha256


def checked_package(package):
    report=json.loads((package/'BUILD.json').read_text())
    match=re.fullmatch(r'PARTUUID=([0-9a-f]{8})-01',report['root_device'])
    if not match:raise ValueError('Internal kernel must boot its stable PARTUUID partition')
    for name,digest in report['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid kernel package path')
        if sha256(package/relative)!=digest:raise ValueError('Kernel package checksum differs: '+name)
    return report,match[1]


def load_plan(path):
    requested=Path(path).expanduser()
    if requested.is_symlink() or not requested.is_file() or requested.stat().st_size>16384:
        raise ValueError('Choose a regular internal build-plan JSON file no larger than 16 KiB')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('Duplicate build-plan field: '+key)
            result[key]=value
        return result
    plan=json.loads(requested.read_text(),object_pairs_hook=unique)
    paths=('root','kernel_package','gpu_runtime','gpu_module_package','gpu_mesa_package')
    if not isinstance(plan,dict) or not set(paths)<=plan.keys() or set(plan)-set(paths)-{'size_mib','recovery'}:
        raise ValueError('Build plan needs root, kernel, Pocket GPU runtime, MBX module and Mesa paths')
    for name in (*paths,*(['recovery'] if 'recovery' in plan else [])):
        value=plan[name]
        if not isinstance(value,str) or not value:raise ValueError('Build plan needs a local '+name+' path')
        path=Path(value).expanduser().resolve()
        if not path.is_dir():raise ValueError('Build-plan '+name+' must be an existing directory')
        plan[name]=path
    size=plan.get('size_mib',1536)
    if type(size) is not int or not 1024<=size<=1900:
        raise ValueError('Build plan size_mib must be 1024–1900')
    plan['size_mib']=size
    return plan


def restore_owner(output):
    if not os.environ.get('SUDO_UID') or not os.environ.get('SUDO_GID'):
        return
    owner=(int(os.environ['SUDO_UID']),int(os.environ['SUDO_GID']))
    if not output.exists():return
    for path in (output,*output.rglob('*')):
        os.chown(path,*owner,follow_symlinks=False)
        if path.is_dir() and not path.is_symlink():path.chmod(0o700)
        elif not path.is_symlink():path.chmod(0o600)


def build(root,package,recovery,output,size_mib,gpu=None):
    root=root.resolve();package=package.resolve();recovery=recovery.resolve() if recovery else None;output=output.expanduser().absolute()
    if root==Path('/') or not 1024<=size_mib<=1900:
        raise ValueError('Use a separate Debian build root and 1024–1900 MiB filesystem')
    if output==Path('/') or output==Path('/dev') or output.is_relative_to('/dev'):
        raise ValueError('Choose an ordinary local kit folder, not a device path')
    if not output.parent.is_dir():raise ValueError('The internal kit parent folder must already exist')
    report,disk_id=checked_package(package)
    if gpu is not None:
        from stage_desktop import stage as stage_desktop
        from stage_gpu import stage as stage_gpu
        stage_desktop(root,gpu['gpu_runtime'])
        stage_gpu(root,gpu['gpu_runtime'],gpu['gpu_module_package'],
                  gpu['gpu_mesa_package'],package)
    install=json.loads((root/'usr/local/share/pocket/INSTALL.json').read_text())
    if install.get('autostart') is not True or install.get('desktop_user')!='nokia':
        raise ValueError('Pocket desktop must autostart as the normal user nokia')
    if install.get('renderer')!='native-mbx-gpu':
        raise ValueError('Internal image needs the staged MBX GPU desktop; run stage_gpu.py')
    if not (root/'home/nokia').is_dir():raise ValueError('Debian root has no local nokia account home')
    runtime=root/'usr/local/share/pocket'
    payload=json.loads((runtime/'runtime-profile.json').read_text())
    for name,digest in payload['files'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts:raise ValueError('Invalid runtime path')
        if sha256(runtime/path)!=digest:raise ValueError('Staged runtime checksum differs: '+name)
    gpu_root=root/'usr/local/lib/n810-graphics'
    gpu_release=install.get('gpu_release','')
    if not re.fullmatch(r'bootstrap-[0-9a-f]{12}',gpu_release):
        raise ValueError('Invalid staged GPU release')
    gpu=gpu_root/'releases'/gpu_release
    if (gpu_root/'current').readlink()!=Path('releases')/gpu_release:
        raise ValueError('The staged GPU release is not selected')
    gpu_manifest=json.loads((gpu/'MANIFEST.json').read_text())
    if gpu_manifest.get('kernel_release')!=report['release']:
        raise ValueError('GPU owner and kernel releases differ')
    for name,digest in gpu_manifest['files'].items():
        if Path(name).name!=name or sha256(gpu/name)!=digest:
            raise ValueError('GPU release checksum differs: '+name)
    if gpu_manifest['files'].get('n810_mbx_gpu_probe.ko')!=install.get('module_sha256') or \
            gpu_manifest['files'].get('libOSMesa.so.8')!=install.get('mesa_sha256'):
        raise ValueError('GPU install record differs from staged release')
    desktop_unit=(root/'etc/systemd/system/pocket-desktop.service').read_text()
    if 'ExecStart=/usr/bin/python3 -I /usr/local/lib/n810-pocket/native_owner.py' not in desktop_unit or \
            'Restart=no' not in desktop_unit:
        raise ValueError('GPU desktop owner is not selected for boot')
    flasher=root/'usr/local/bin/0xFFFF'
    flasher_record=json.loads((root/'usr/local/share/doc/0xffff/BUILD.json').read_text())
    if flasher_record['identity'].get('usb_only') is not True or flasher_record['identity'].get('target')!='armel':
        raise ValueError('Stage the USB-only ARM flasher before building the image')
    if sha256(flasher)!=flasher_record['binary_sha256']:
        raise ValueError('Staged flasher checksum differs')
    source_identity={name:report[name] for name in ('maintained_commit','upstream_sha256','source_lock_sha256')}
    recovery_report=None
    if recovery:
        recovery_report=json.loads((recovery/'BUILD.json').read_text())
        for name,digest in recovery_report['files'].items():
            if Path(name).name!=name or sha256(recovery/name)!=digest:raise ValueError('RAM-installer checksum differs')
        if (recovery_report.get('kind')!='n810-ram-installer' or
                recovery_report.get('filesystem_format')!='cpio-xz' or
                recovery_report.get('root_device')!='initramfs:/init' or
                recovery_report.get('kernel_source')!=source_identity):
            raise ValueError('RAM installer is not the matching-source N810 initramfs recovery build')
    if not (root/'etc/systemd/system/multi-user.target.wants/pocket-desktop.service').is_symlink():
        raise ValueError('Desktop service is not enabled')
    # Refresh first-boot integration even when reusing a staged Debian root.
    from first_boot import configure_first_boot
    configure_first_boot(root)
    output.mkdir(exist_ok=False,mode=0o700)
    release=report['release']
    modules_root=root/'lib/modules'
    modules_root.mkdir(parents=True,exist_ok=True)
    for stale in modules_root.iterdir():
        if stale.is_dir() and not stale.is_symlink():shutil.rmtree(stale)
        else:stale.unlink()
    destination=modules_root/release
    shutil.copytree(package/'root/lib/modules'/release,destination,symlinks=True)
    filesystem_uuid=str(uuid.uuid4())
    fstab=root/'etc/fstab'
    lines=[line for line in fstab.read_text().splitlines() if not (len(line.split())>=2 and line.split()[1]=='/')]
    fstab.write_text('\n'.join([f'UUID={filesystem_uuid} / ext4 defaults,noatime 0 1',*lines])+'\n')
    network=root/'etc/network/interfaces'
    network.write_text(network.read_text().replace('address 192.168.10.1','address 169.254.81.1').replace('netmask 255.255.255.0','netmask 255.255.0.0'))
    marker=root/'var/lib/pocket';marker.mkdir(parents=True,exist_ok=True)
    service=root/'etc/systemd/system/pocket-expand-internal-root.service'
    service.write_text('[Unit]\nDescription=Expand Pocket root filesystem to the internal MMC\n'
        'After=local-fs.target systemd-udev-settle.service\n'
        'ConditionPathExists=!/var/lib/pocket/internal-root-expanded\n\n'
        '[Service]\nType=oneshot\n'
        f"ExecStart=/bin/sh -c '/usr/sbin/resize2fs /dev/disk/by-partuuid/{disk_id}-01 && touch /var/lib/pocket/internal-root-expanded'\n\n"
        '[Install]\nWantedBy=multi-user.target\n')
    wants=root/'etc/systemd/system/multi-user.target.wants/pocket-expand-internal-root.service'
    if wants.exists() or wants.is_symlink():wants.unlink()
    wants.symlink_to('../pocket-expand-internal-root.service')
    installed = root / 'etc/n810-image/bootstrap.json'
    installed.parent.mkdir(parents=True, exist_ok=True)
    installed.parent.chmod(0o755)
    installed.write_text(json.dumps({
        'version': 1,
        'kind': 'n810-internal-root',
        'kernel_release': release,
        'kernel_sha256': sha256(package/'zImage-omap2420-n810'),
        'kernel_source': source_identity,
        'pocket_source_commit': install['source_commit'],
        'pocket_profile': install['profile'],
        'desktop_user': install['desktop_user'],
        'renderer': install['renderer'],
        'gpu_module_sha256': install['module_sha256'],
        'gpu_mesa_sha256': install['mesa_sha256'],
        'root_filesystem_uuid': filesystem_uuid,
        'keyboard_remapper_sha256': sha256(root/'usr/local/sbin/n810-fn-remap'),
        'keyboard_backlight_sha256': sha256(root/'usr/local/sbin/n810-backlightd'),
        'enabled_n810_services': sorted(path.name for path in
            (root/'etc/systemd/system/multi-user.target.wants').iterdir()
            if path.name.startswith(('n810-', 'pocket-'))),
        'builder_sha256': sha256(Path(__file__)),
        'first_boot_sha256': sha256(Path(__file__).with_name('first_boot.py')),
    },indent=2)+'\n')
    installed.chmod(0o644)
    first_boot_record=json.loads(installed.read_text())
    image=output/'root.ext4'
    with image.open('wb') as stream:stream.truncate(size_mib*1024*1024)
    image.chmod(0o600)
    subprocess.run(['mkfs.ext4','-F','-d',str(root),'-U',filesystem_uuid,'-L','n810-root',
                    '-E','lazy_itable_init=0,lazy_journal_init=0',str(image)],check=True)
    subprocess.run(['e2fsck','-fn',str(image)],check=True)
    compressed=output/'root.ext4.gz'
    with image.open('rb') as source,compressed.open('wb') as target:
        with gzip.GzipFile(fileobj=target,mode='wb',compresslevel=1,mtime=0,filename='') as archive:
            shutil.copyfileobj(source,archive,4*1024*1024)
    compressed.chmod(0o600)
    root_bytes=image.stat().st_size
    root_digest=sha256(image)
    image.unlink()
    shutil.copyfile(package/'zImage-omap2420-n810',output/'kernel.bin')
    shutil.copyfile(package/'BUILD.json',output/'KERNEL-BUILD.json')
    if recovery:
        shutil.copyfile(recovery/'BUILD.json',output/'INSTALLER-BUILD.json')
        for source,target in (('kernel.bin','installer-kernel.bin'),('initramfs.cpio.xz','installer-initramfs.cpio.xz'),
                              ('installer-known-hosts','installer-known-hosts')):
            shutil.copyfile(recovery/source,output/target)
    manifest=dict(kind='n810-internal',disk_id=disk_id,filesystem_uuid=filesystem_uuid,
                  kernel_release=release,kernel_sha256=sha256(output/'kernel.bin'),
                  install_transport='maemo-usb-mass-storage' if not recovery else 'ram-installer-or-maemo-usb',
                  root_bytes=root_bytes,root_sha256=root_digest,
                  compressed_root_sha256=sha256(compressed),desktop_ready=True,desktop=install,
                  kernel_package_manifest_sha256=sha256(package/'BUILD.json'),
                  first_boot=dict(profile='n810-internal-v3',
                      root_manifest_sha256=sha256(installed),
                      enabled_services=first_boot_record['enabled_n810_services'],
                      keyboard_remapper_sha256=first_boot_record['keyboard_remapper_sha256'],
                      keyboard_backlight_sha256=first_boot_record['keyboard_backlight_sha256']),
                  device_action=False,hardware_acceptance=False)
    if recovery:
        manifest.update(installer_kernel_release=recovery_report['kernel_release'],
                        installer_kernel_sha256=sha256(output/'installer-kernel.bin'),
                        ram_installer_manifest_sha256=sha256(recovery/'BUILD.json'))
    (output/'INTERNAL.json').write_text(json.dumps(manifest,indent=2)+'\n')
    guide=output/'INSTALL.txt'
    guide_text=('Pocket internal installation kit\n\n'
        'This private kit replaces the target N810 internal MMC; no SD card is required.\n'
        'On macOS, stock Maemo exports internal storage over USB for the guarded full-disk write.\n'
        'The root includes the Pocket release runtime and GUI autostart as the local account.\n'
        'The first-install renderer is the staged native MBX GPU service; verify it on the tablet.\n'
        'Write the root and verify its readback, then return the same tablet to Nokia update mode.\n'
        'Use the separately identified target to flash the matching permanent kernel and request reboot.\n')
    if recovery:guide_text+='This kit also contains the optional RAM installer.\n'
    guide.write_text(guide_text+'Keep the kit private: its filesystem contains the local account password hash.\n')
    roles={'root-filesystem':'root.ext4.gz','kernel':'kernel.bin','install-plan':'INTERNAL.json',
           'kernel-build-manifest':'KERNEL-BUILD.json','install-guide':'INSTALL.txt'}
    if recovery:
        roles.update({'installer-kernel':'installer-kernel.bin',
                      'installer-filesystem':'installer-initramfs.cpio.xz',
                      'installer-build-manifest':'INSTALLER-BUILD.json',
                      'installer-host-key':'installer-known-hosts'})
    (output/'INSTALLATION.json').write_text(json.dumps(dict(version=1,kind='n810-internal',
        release='bookworm-internal-'+release,kernel_release=release,
        files=[dict(role=role,path=name,bytes=(output/name).stat().st_size,sha256=sha256(output/name))
               for role,name in roles.items()]),indent=2)+'\n')
    restore_owner(output)
    result=dict(state='internal_kit_built',output=str(output),root_bytes=root_bytes,
                compressed_bytes=compressed.stat().st_size,device_action=False)
    print(json.dumps(result))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,help='JSON with root, kernel and GPU build paths; recovery is optional')
    p.add_argument('--root',type=Path);p.add_argument('--kernel-package',type=Path);p.add_argument('--recovery',type=Path)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--size-mib',type=int)
    a=p.parse_args()
    if sys.platform!='linux' or os.geteuid()!=0:p.error('Run on a Linux builder as root')
    os.umask(0o077)
    if a.plan:
        if any(value is not None for value in (a.root,a.kernel_package,a.recovery,a.size_mib)):
            p.error('Use --plan instead of individual source paths and --size-mib')
        plan=load_plan(a.plan)
        existed=a.output.expanduser().absolute().exists()
        try:build(plan['root'],plan['kernel_package'],plan.get('recovery'),a.output,plan['size_mib'],plan)
        finally:
            if not existed:restore_owner(a.output.expanduser().absolute())
    else:
        if any(value is None for value in (a.root,a.kernel_package)):
            p.error('Provide --plan or both --root and --kernel-package')
        build(a.root,a.kernel_package,a.recovery,a.output,1536 if a.size_mib is None else a.size_mib)

if __name__=='__main__':main()
