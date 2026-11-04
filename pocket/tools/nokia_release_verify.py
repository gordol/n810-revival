import hashlib,json,tarfile
from pathlib import Path

HOST_GEOMETRY='native/build-host/Darwin-arm64-geometry/'
PLATFORM_FILES=frozenset(('vendor/native/_cellengine.abi3.so','vendor/native/_cellengine.provenance.json','native/build-host/Linux-armv6l-cpython-311/_cellengine.abi3.so','native/build-host/Linux-armv6l-cpython-311/provenance.json','vendor/native/libn810compute.so','vendor/native/libn810normals.so','vendor/native/libn810coverage.so','vendor/native/libn810finish.so','vendor/native/libn810pixels.so','build-info.json','vendor/native/libpocket_rns.so','vendor/native/libpocket_rns.provenance.json',HOST_GEOMETRY+'libgeometry.dylib',HOST_GEOMETRY+'provenance.json'))


def verify(archive_path):
    """Check a release without extracting or executing any of its contents."""
    with tarfile.open(archive_path) as archive:
        members={member.name:member for member in archive.getmembers()}
        if len(members)!=len(archive.getmembers()) or any(not member.isfile() for member in members.values()):raise ValueError('release contains duplicate or non-file members')
        manifest=json.load(archive.extractfile('device-poc/pocket-manifest.json'))
        if manifest['version']!=2:raise ValueError('unsupported release manifest')
        if set(members)!=set(manifest['files'])|{'device-poc/pocket-manifest.json'}:raise ValueError('release closure differs from manifest')
        for name,expected in manifest['files'].items():
            if name.startswith('/') or '..' in Path(name).parts:raise ValueError('unsafe release path')
            if hashlib.sha256(archive.extractfile(name).read()).hexdigest()!=expected:raise ValueError('release digest mismatch: '+name)
        shared={name:sha for name,sha in manifest['files'].items() if name not in PLATFORM_FILES}
        if shared!=manifest['shared_files']:raise ValueError('shared engine file mismatch')
        digest=hashlib.sha256(json.dumps(shared,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        if digest!=manifest['engine_sha256']:raise ValueError('engine digest mismatch')
        if set(manifest['platform_files'])!=set(manifest['files'])&PLATFORM_FILES:raise ValueError('platform adapter list mismatch')
        return manifest
