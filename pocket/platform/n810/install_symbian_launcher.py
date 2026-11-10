#!/usr/bin/env python3
"""Install the managed launcher into an existing N810 GPU desktop."""
from pathlib import Path
import fcntl
import hashlib
import os
import tempfile


def install():
    if os.geteuid()!=0:raise PermissionError('Run as root on the N810')
    base=Path('/usr/local/lib/n810-pocket')
    source=Path('/usr/local/share/pocket-gui/managed-native/source')
    if not (base/'native_owner.py').is_file() or not (source/'shell/app_registry.py').is_file():
        raise RuntimeError('Install the managed GPU desktop first')
    # The owner's persistent lock excludes an active desktop and GPU session.
    with open('/run/n810-pocket-native/owner.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        expected_owner='2a96cda6083372313d7d5b72747a12d36e8955406fbaca595ec8d8201d2586fd'
        current_owner=hashlib.sha256((base/'native_owner.py').read_bytes()).hexdigest()
        incoming_owner=hashlib.sha256(Path(__file__).with_name('native_owner.py').read_bytes()).hexdigest()
        if current_owner not in (expected_owner,incoming_owner,'642ebb57d42f00b12cef7206d596d54295c2fe36126f80618b0d7dbf2f1778d2'):
            raise RuntimeError('Installed graphics owner changed; reconcile it before installing')
        here=Path(__file__).resolve().parent
        pocket=here.parents[1]
        files={base/'native_owner.py':here/'native_owner.py',base/'symbian_session.py':here/'symbian_session.py',
               source/'shell/symbian_launch.py':pocket/'shell/symbian_launch.py',
               source/'shell/apps/symbian/registration.py':pocket/'shell/apps/symbian/registration.py'}
        registry=source/'shell/app_registry.py'
        text=registry.read_text()
        entry="('apps/symbian/registration.py','descriptor'),"
        if entry not in text:
            if text.count('BUILTINS=(')!=1:raise RuntimeError('Unsupported application registry')
            text=text.replace('BUILTINS=(', 'BUILTINS=('+entry+'\n          ',1)
        backup=Path(tempfile.mkdtemp(prefix='symbian-launcher-',dir='/var/backups'))
        originals={path:path.read_bytes() if path.exists() else None for path in [*files,registry]}
        for n,(path,data) in enumerate(originals.items()):
            if data is not None:(backup/str(n)).write_bytes(data)
        (backup/'paths.txt').write_text('\n'.join(map(str,originals))+'\n')
        try:
            for path,original in files.items():
                path.parent.mkdir(parents=True,exist_ok=True)
                raw=original.read_bytes();compile(raw,str(path),'exec')
                path.write_bytes(raw);path.chmod(0o644)
            compile(text,str(registry),'exec');registry.write_text(text)
        except BaseException:
            for path,data in originals.items():
                if data is None:path.unlink(missing_ok=True)
                else:path.write_bytes(data)
            raise
        print('Launcher installed; previous files:',backup)

if __name__=='__main__':install()
