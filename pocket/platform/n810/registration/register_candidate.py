#!/usr/bin/python3 -I
"""Fixed installed-version selector for original reviewed Pocket releases. No profile/input/font writes."""
import fcntl,hashlib,json,os,shutil,stat,sys,types
from pathlib import Path
from contextlib import ExitStack
INPUT=Path('/tmp/touch-process-79d1867-register')
ASSETS=Path('/usr/local/share/n810-pocket')
RUNTIME=Path('/run/n810-pocket-console')
BACKUP=Path('/var/backups/n810-pocket-console/session-notifications-cb97ead')
PINS={'package': 'd5652a66d215f4815d727f41d4b130a9fb46aecf0a18f573e305f8a2bfa75aaf', 'primitives': 'eba67d87812486f5d40f50a80f7f3468e8785916819e723c4dc5a5501ed4938c', 'old_manifest': 'f4b683c77b43d8354ebb0ad9f7ae3c0e8d796692c59df17f37b410b6001d9505', 'new_manifest': '957abfa7ccb131417cfec9e9e504d8ee1ddb888ab537925819fe6f591d415f00'}
CONTRACTS={'/usr/local/bin/n810-pocket': 'f9e4b91f166ba5d685d1057d43f42defb4ef089f6805741be4f44020f1e7af49', '/usr/local/sbin/n810-pocket-console': '3541fdee15f048339ea45bf534a3274d95fc940c6748d8b195bec51aea29e445', '/usr/local/lib/n810-pocket/console_helper.py': 'e92248ae39ac4d93abaf313e61268ff9e25b879466b11322b8734fb616db3538', '/usr/local/libexec/n810-pocket-session': '44810f2369cfbf8908a6a590b83e875ece59c4e5825ebe91ef8c37a5f51931f8', '/usr/local/lib/n810-pocket/keyboard.json': '8c511f6e826f6444ce82be5b519739844b45b8498d2c032b192675737f07368c'}
def pinned(path,digest):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size>10*1024*1024:raise ValueError('Unexpected payload file: '+str(path))
        data=stream.read(10*1024*1024+1)
    if len(data)>10*1024*1024 or hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Pinned hash mismatch: '+str(path))
    return data

def primitives(data):
    module=types.ModuleType('reviewed_install_primitives')
    exec(compile(data,'<reviewed-install-primitives>','exec'),module.__dict__)
    return module

def acquire(path):
    if path.is_symlink():raise PermissionError('Unexpected lock symlink')
    lock=path.open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BaseException:lock.close();raise
    return lock

def contracts(lib):
    for name,digest in CONTRACTS.items():
        path=Path(name);lib.parent(path.parent);lib.root_tree(path);pinned(path,digest)

def locks(lib,stack):
    for path in (RUNTIME/'upgrade.lock',Path('/run/n810-gui/launch.lock'),RUNTIME/'session.lock'):
        lib.parent(path.parent);stack.enter_context(acquire(path))


CONTRACTS['/usr/local/sbin/n810-pocket-version']='c14035f054b42e68a9836af968f6f5399a740b0c0281d5684aa19a1a7e99de89'
def administrator():
    if len(sys.argv)!=1 or os.geteuid()!=0 or os.getegid()!=0:raise PermissionError('Protected administrator invocation only; no arguments')
    os.umask(0o022)


def library():
    source=BACKUP/'install-primitives.py';info=source.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_gid!=0 or info.st_mode&0o022:raise PermissionError('Untrusted install primitives')
    lib=primitives(pinned(source,PINS['primitives']));lib.parent(source.parent);lib.root_tree(source);contracts(lib)
    return lib


def known(path,hashes):
    if not path.exists() and not path.is_symlink():return None
    for digest in hashes:
        try:return pinned(path,digest)
        except ValueError:pass
    raise ValueError('Unexpected selector/catalog bytes: '+str(path))


def replace_files(lib,destinations,new,before,receipt,hashes):
    touched=[]
    try:
        for name,(path,mode) in destinations.items():
            if known(path,hashes[name])!=before[name]:raise ValueError('Selector/catalog changed during installation')
            touched.append(name)
            if new[name] is None:path.unlink(missing_ok=True)
            else:lib.atomic_write(path,new[name],mode)
            if known(path,hashes[name])!=new[name]:raise ValueError('Selector/catalog write did not verify')
        contracts(lib);lib.atomic_write(receipt,json.dumps(dict(completed=True)).encode())
    except BaseException:
        errors=[]
        for name in reversed(touched):
            path,mode=destinations[name]
            try:
                known(path,hashes[name])
                if before[name] is None:path.unlink(missing_ok=True)
                else:lib.atomic_write(path,before[name],mode)
                if known(path,hashes[name])!=before[name]:raise ValueError('Recovery bytes did not verify')
            except BaseException as error:errors.append(name+': '+str(error))
        try:
            receipt.unlink(missing_ok=True)
            lib.atomic_write(receipt,json.dumps(dict(completed=False,recovery_errors=errors)).encode())
        except BaseException:
            try:receipt.unlink(missing_ok=True)
            except OSError:pass
        if errors:print('Selector/catalog recovery errors: '+str(errors),file=sys.stderr)
        raise
CATALOG=Path("/usr/local/lib/n810-pocket/versions.json")
SELECTOR=Path("/usr/local/lib/n810-pocket/version_selector.py")
SELECTOR_SHA='cb6d69e258652312702745f7e3b09c83e64873506f7e9e300d6fb833d13db270'
POLICY=Path("/etc/sudoers.d/n810-pocket-version")
POLICY_SHA='fa1d62f8551c9cdf9210124c741c1e2ee3d123316112f67453e72d699c01d198'
FILE_PAYLOAD=False
PACKAGE_SHA='3e765d926f027e2e29a0852c16e206a8b8069ccbb664b9c44d67f66cb7577920'
ENTRY={'title': 'Window drag scheduling trial', 'summary': 'Draws held drag outline before unrelated model work; keeps process touch acquisition. Contact loss and resize speed need physical acceptance.', 'manifest_sha256': '7fc8f860e71fd2a4d17c1a3a4fd6da892110e5c0214df1e519a4abf7a7a1bd80', 'engine_sha256': '79d18678aeb3af263246b14b1e5cbc9d2e8fff5b13ffc8da573b1d4ea2aca525', 'retained': 'touch-process-79d1867/candidate-assets'}
VERSION_ID='touch-process-79d1867'
INPUT=Path('/tmp/touch-process-79d1867-register')
DESTINATION=Path('/var/backups/n810-pocket-console/touch-process-79d1867')


DATA_ROOT=Path('/usr/local/share/n810-map-packs/fixed-v2-close-v2')
DATA_ARCHIVE_SHA='631dfb2cd1c26e621bbb8c3e0de532aa99a7b629cef8bf9bea4796fa1da34e41'
DATA_MANIFEST_SHA='d22dd566fcc12886db0dff07aa822e8c999bef2146819fdcb9830677db1d3ff4'

def verify_pack(lib,path,full=True):
    lib.root_tree(path)
    raw=pinned(path/'device-poc/pocket-manifest.json',DATA_MANIFEST_SHA)
    manifest=json.loads(raw)
    if manifest.get('version')!=1 or manifest.get('pack_set')!=DATA_ROOT.name:raise ValueError('Wrong map pack set')
    # Installed root-only fixed data is trusted between explicit full audits.
    # Ownership and exact manifest remain checked on every reuse.
    if not full:return
    expected=set(manifest['files'])|{'device-poc/pocket-manifest.json'}
    actual={str(p.relative_to(path)) for p in path.rglob('*') if p.is_file()}
    if actual!=expected:raise ValueError('Map data closure differs')
    for name,digest in manifest['files'].items():
        relative=Path(name)
        if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe data path')
        pinned(path/relative,digest)

def install_pack(lib):
    lib.parent(DATA_ROOT.parent)
    if DATA_ROOT.exists():
        verify_pack(lib,DATA_ROOT,full=False);return
    archive=pinned(INPUT/'map-packs.tar.gz',DATA_ARCHIVE_SHA)
    stage=DATA_ROOT.with_name('.'+DATA_ROOT.name+'.new')
    stage.mkdir(mode=0o755,exist_ok=False)
    lib.extract(archive,stage);verify_pack(lib,stage)
    stage.rename(DATA_ROOT)


def select_verified_candidate(lib,entries,versions):
    """Only this invocation's disk-verified candidate, under its existing locks."""
    source=DESTINATION/'candidate-assets'
    if versions.get(VERSION_ID)!=source:raise ValueError('Verified candidate location changed')
    current=next((key for key,path in versions.items() if path==ASSETS),None)
    if current is None:raise ValueError('Active assets missing')
    destination=DESTINATION.parent/entries[current]['retained']
    if destination.exists() or destination.is_symlink():raise ValueError('Retained destination occupied')
    moved_old=moved_new=False
    try:
        ASSETS.rename(destination);moved_old=True
        source.rename(ASSETS);moved_new=True
        pinned(ASSETS/'device-poc/pocket-manifest.json',ENTRY['manifest_sha256']);contracts(lib)
    except BaseException:
        if moved_new:ASSETS.rename(source)
        if moved_old and not ASSETS.exists():destination.rename(ASSETS)
        raise


def main():
    administrator();lib=library();lib.root_tree(SELECTOR);lib.root_tree(POLICY)
    source=pinned(SELECTOR,SELECTOR_SHA);pinned(POLICY,POLICY_SHA)
    selector=types.ModuleType('reviewed_installed_selector');exec(compile(source,'<reviewed-installed-selector>','exec'),selector.__dict__)
    archive=None if FILE_PAYLOAD else pinned(INPUT/'nokia.tar.gz',PACKAGE_SHA)
    with ExitStack() as stack:
        locks(lib,stack);lib.assert_no_console_client();contracts(lib)
        install_pack(lib)
        entries=selector.load_catalog(lib)
        if VERSION_ID in entries:raise ValueError('Installed ID already exists; silent replacement refused')
        # Inventory checks trusted paths and manifest identities for every entry.
        # Unselected payload bodies are checked by audit_retained.py, not install.
        selector.inventory(lib,entries)
        # Preserve every prior catalog byte and every prior release tree.
        fd=os.open(CATALOG,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,'rb') as stream:before=stream.read(65537)
        if len(before)>65536:raise ValueError('Oversized catalog')
        lib.parent(DESTINATION.parent);DESTINATION.mkdir(mode=0o700,exist_ok=False)
        candidate=DESTINATION/'candidate-assets'
        if FILE_PAYLOAD:
            payload=INPUT/'files';lib.root_tree(payload)
            shutil.copytree(payload,candidate)
        else:
            candidate.mkdir(mode=0o755);lib.extract(archive,candidate)
        selector.verify_tree(lib,candidate,ENTRY)
        updated=dict(entries);updated[VERSION_ID]=ENTRY
        selector.validate_catalog(dict(version=1,entries=updated));versions=selector.inventory(lib,updated)
        data=(json.dumps(dict(version=1,entries=updated),indent=2)+chr(10)).encode()
        if len(data)>65536:raise ValueError('Updated catalog exceeds64KiB')
        lib.atomic_write(DESTINATION/'catalog.previous.json',before,0o600)
        hashes={'catalog':[hashlib.sha256(before).hexdigest(),hashlib.sha256(data).hexdigest()]}
        replace_files(lib,{'catalog':(CATALOG,0o600)},{'catalog':data},{'catalog':before},DESTINATION/'result.json',hashes)
        # Failure leaves a registered candidate and restores the prior active tree.
        select_verified_candidate(lib,updated,versions)
    print('Registered '+VERSION_ID+'; selected the just-verified candidate under the same locks.')

if __name__=='__main__':main()
