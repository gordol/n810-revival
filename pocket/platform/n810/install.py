"""Register a pinned release, then prepare timestamp-validated source caches on the target."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import py_compile
import stat
import sys
import time

STAGE = None
REGISTRAR_SHA256 = None
SESSION_ENTRY_SHA256 = None
SESSION_UPGRADE_SHA256 = None
ENGINE_SHA256 = None
SPP_HELPER_SHA256 = None
SPP_HELPER_PREDECESSORS = ()
RECEIPT_DIRECTORY = None
ASSETS = Path('/usr/local/share/n810-pocket')


def upgrade_session():
    """Run the pinned stopped-console upgrade before checking new contracts."""
    payloads={}
    for name,expected in (('session_entry.py',SESSION_ENTRY_SHA256),('upgrade_session.py',SESSION_UPGRADE_SHA256)):
        fd=os.open(STAGE/name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode):raise ValueError('Session payload must be a regular file')
            raw=stream.read(262145)
        if len(raw)>262144 or hashlib.sha256(raw).hexdigest()!=expected:
            raise ValueError('Session payload does not match package: '+name)
        payloads[name]=raw
    destination=Path('/tmp/pocket-session-startup-upgrade')
    destination.mkdir(mode=0o700,exist_ok=True)
    info=destination.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
        raise ValueError('Untrusted session upgrade directory')
    target=destination/'session_entry.py'
    try:fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644)
    except FileExistsError:
        fd=os.open(target,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022 or stream.read(262145)!=payloads['session_entry.py']:
                raise ValueError('Untrusted existing session upgrade payload')
    else:
        with os.fdopen(fd,'wb') as stream:
            stream.write(payloads['session_entry.py']);stream.flush();os.fsync(stream.fileno())
    namespace=dict(__name__='__main__',__file__=str(STAGE/'upgrade_session.py'))
    exec(compile(payloads['upgrade_session.py'],namespace['__file__'],'exec'),namespace)



def upgrade_spp_helper():
    """Upgrade only the reviewed fixed helper; retain its original for rollback."""
    if SPP_HELPER_SHA256 is None:return
    source=STAGE/'rnode_spp_prepare.py'
    fd=os.open(source,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno());raw=stream.read(65537)
    if not stat.S_ISREG(info.st_mode) or len(raw)>65536 or hashlib.sha256(raw).hexdigest()!=SPP_HELPER_SHA256:
        raise ValueError('Bluetooth helper payload does not match package')
    target=Path('/usr/local/sbin/n810-rnode-spp-prepare')
    if not target.exists():return  # A fresh platform must configure its own fixed helper/policy.
    info=target.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=0 or info.st_mode&0o022:
        raise ValueError('Installed Bluetooth helper is not protected')
    previous=target.read_bytes();digest=hashlib.sha256(previous).hexdigest()
    if digest==SPP_HELPER_SHA256:return
    if digest not in SPP_HELPER_PREDECESSORS:
        raise ValueError('Installed Bluetooth helper differs from reviewed predecessors; retained')
    backup=RECEIPT_DIRECTORY/'rnode-spp-prepare.before.py'
    fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as stream:
        stream.write(previous);stream.flush();os.fsync(stream.fileno())
    temporary=target.with_name('.n810-rnode-spp-prepare-'+str(os.getpid()))
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o755)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.chown(temporary,0,0);os.chmod(temporary,0o755);os.replace(temporary,target)
        directory=os.open(target.parent,os.O_RDONLY|os.O_CLOEXEC)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if temporary.exists():temporary.unlink()
    receipt=dict(previous_sha256=digest,sha256=SPP_HELPER_SHA256,backup=str(backup))
    (RECEIPT_DIRECTORY/'SPP_HELPER.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('Updated fixed Bluetooth helper; previous helper retained.',flush=True)


def previous_bytecode(assets, receipt):
    """Reuse verified compiled modules whose source bytes have not changed."""
    result={};total=0
    try:
        manifest=json.loads((assets/'device-poc/pocket-manifest.json').read_text())['files']
        records=json.loads(receipt.read_text())['files']
        for name,row in records.items():
            relative=Path(name);source=Path(row['source'])
            if relative.is_absolute() or source.is_absolute() or '..' in relative.parts or '..' in source.parts:continue
            if manifest.get(str(source))!=row['source_sha256']:continue
            raw=(assets/relative).read_bytes();total+=len(raw)
            if total>16*1024*1024:break
            if hashlib.sha256(raw).hexdigest()==row['cache_sha256']:
                result[(str(source),row['source_sha256'])]=raw
    except (OSError,ValueError,KeyError,TypeError):pass
    return result

def main():
    if os.geteuid() != 0 or len(sys.argv) != 1:
        raise SystemExit('Run this fixed installer as administrator, without arguments')
    reusable={}
    try:
        old=json.loads((ASSETS/'build-info.json').read_text())['release_id']
        if isinstance(old,str) and len(old)==12 and all(c in '0123456789abcdef' for c in old):
            reusable=previous_bytecode(ASSETS,Path('/var/backups/n810-pocket-console')/('pocket-'+old)/'BYTECODE.json')
    except (OSError,ValueError,KeyError,TypeError):pass
    path = STAGE/'register_candidate.py'
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode): raise ValueError('Registrar must be a regular file')
        raw = stream.read(131073)
    if len(raw) > 131072 or hashlib.sha256(raw).hexdigest() != REGISTRAR_SHA256:
        raise ValueError('Registrar does not match the reviewed package')
    upgrade_session()
    namespace = dict(__name__='__main__', __file__=str(path))
    exec(compile(raw, str(path), 'exec'), namespace)
    manifest = json.loads((ASSETS/'device-poc/pocket-manifest.json').read_text())
    if manifest['engine_sha256'] != ENGINE_SHA256: raise ValueError('Selected source identity changed')
    records = {}
    progress = time.monotonic()
    for name, digest in manifest['files'].items():
        if not name.endswith('.py'): continue
        source = ASSETS/name
        if hashlib.sha256(source.read_bytes()).hexdigest() != digest: raise ValueError('Source changed: '+name)
        # Release sources and caches are root-owned. Verify content at install;
        # normal imports can check mtime/size without rereading every source.
        raw_cache=reusable.get((name,digest))
        info=source.stat()
        if raw_cache and raw_cache[:4]==importlib.util.MAGIC_NUMBER and raw_cache[4:8]==bytes(4) and int.from_bytes(raw_cache[12:16],'little')==info.st_size:
            # Source content was verified above; only the timestamp changed
            # when rsync staged the same module in another release tree.
            raw_cache=raw_cache[:8]+(int(info.st_mtime)&0xffffffff).to_bytes(4,'little')+raw_cache[12:]
            cache=Path(importlib.util.cache_from_source(str(source)))
            cache.parent.mkdir(parents=True,exist_ok=True);cache.write_bytes(raw_cache)
        else:
            cache = Path(py_compile.compile(str(source), dfile=name, doraise=True,
                             invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP))
        cache.chmod(0o644)
        records[str(cache.relative_to(ASSETS))] = dict(source=name, source_sha256=digest,
                            cache_sha256=hashlib.sha256(cache.read_bytes()).hexdigest())
        if time.monotonic()-progress > 5:
            print('Prepared source caches:',len(records),flush=True);progress=time.monotonic()
    receipt = dict(engine=ENGINE_SHA256, python=sys.version, invalidation='timestamp',files=records)
    fd = os.open(RECEIPT_DIRECTORY/'BYTECODE.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd,'w') as stream: stream.write(json.dumps(receipt,indent=2)+'\n')
    upgrade_spp_helper()
    print('Installed with',len(records),'timestamp-validated source caches. Previous release retained.',flush=True)


if __name__ == '__main__': main()
