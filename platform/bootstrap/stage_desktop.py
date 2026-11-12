#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stage a verified ARM Pocket runtime and Nokia-user desktop service in a new root."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def checked_path(root,name):
    relative=Path(name)
    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Invalid runtime path')
    path=root/relative
    if not path.resolve().is_relative_to(root.resolve()):raise ValueError('Runtime path escapes its root')
    return path


def make_readable_tree(root, relative):
    """Installed public code must remain accessible under a private build umask."""
    directory = root / relative
    for path in (directory, *directory.rglob('*')):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() else 0o644)
    for parent in directory.parents:
        if parent == root:
            break
        parent.chmod(0o755)


def stage(root,runtime,user='nokia'):
    if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,30}',user):raise ValueError('Invalid local username')
    manifest=json.loads((runtime/'runtime-profile.json').read_text())
    required={'graphics/nokia.py','graphics/framebuffer_scene.py','shell/desktop.py','shell/client_state.py',
              'build/graphics/renderer.so','build/graphics/window.so','build/graphics/_cellengine.abi3.so',
              'build/graphics/console-font.psf'}
    if not required<=manifest['files'].keys():raise ValueError('Incomplete first-install desktop runtime')
    for name,digest in manifest['files'].items():
        source=checked_path(runtime,name)
        if source.is_symlink() or not source.is_file():raise ValueError('Invalid runtime file')
        raw=source.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Runtime checksum differs: '+name)
        if '.so' in source.name and (raw[:5]!=b'\x7fELF\x01' or raw[18:20]!=b'\x28\x00'):
            raise ValueError('First-install library must be 32-bit ARM: '+name)
    destination=root/'usr/local/share/pocket'
    for name in manifest['files']:
        target=checked_path(destination,name);target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(runtime/name,target);target.chmod(0o644)
    for name,target in manifest.get('aliases',{}).items():
        if Path(target).name!=target:raise ValueError('Invalid runtime alias')
        path=checked_path(destination,name)
        if not (path.parent/target).is_file():raise ValueError('Missing runtime alias target')
        if path.exists() or path.is_symlink():path.unlink()
        path.symlink_to(target)
    shutil.copyfile(runtime/'runtime-profile.json',destination/'runtime-profile.json')
    repository=Path(__file__).resolve().parents[2]
    launcher=root/'usr/local/lib/pocket/bootstrap_desktop.py';launcher.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(repository/'pocket/platform/n810/bootstrap_desktop.py',launcher);launcher.chmod(0o644)
    unit=root/'etc/systemd/system/pocket-desktop.service'
    unit.write_text((repository/'platform/device/pocket-desktop.service').read_text().replace('bootstrap_desktop.py\n','bootstrap_desktop.py --user '+user+'\n'))
    unit.chmod(0o644)
    wants=unit.parent/'multi-user.target.wants';wants.mkdir(exist_ok=True)
    link=wants/unit.name
    if link.exists() or link.is_symlink():link.unlink()
    link.symlink_to('../'+unit.name)
    rules=root/'etc/udev/rules.d/70-pocket-input.rules';rules.parent.mkdir(parents=True,exist_ok=True)
    rules.write_text('SUBSYSTEM=="input", KERNEL=="event*", ATTRS{name}=="TSC2005 touchscreen", GROUP="input", MODE="0660", SYMLINK+="input/n810-touch"\n')
    rules.chmod(0o644)
    for group in ('video','input','tty'):
        subprocess.run(['chroot',str(root),'groupadd','-f',group],check=True)
    subprocess.run(['chroot',str(root),'usermod','-aG','video,input,tty',user],check=True)
    result={'source_commit':manifest['source_commit'],'profile':manifest['profile'],
            'desktop_user':user,'renderer':'native-cpu-framebuffer','autostart':True}
    (root/'usr/local/share/pocket/INSTALL.json').write_text(json.dumps(result,indent=2)+'\n')
    for relative in ('usr/local/share/pocket', 'usr/local/lib/pocket'):
        make_readable_tree(root, relative)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True);p.add_argument('--user',default='nokia')
    a=p.parse_args()
    if os.geteuid()!=0 or a.root.resolve()==Path('/'):p.error('Use a separate build root as root')
    print(json.dumps(stage(a.root.resolve(),a.runtime.resolve(),a.user)))

if __name__=='__main__':main()
