"""Verify the optional host geometry asset before registering common stages.

No compilation, worker or dependency installation at startup. Missing assets or
NumPy leave the ordinary portable engine in charge.
"""
import hashlib
import json
from pathlib import Path
import platform
import stat

SOURCES=tuple('native/accelerators/'+group+'/kernels.c' for group in ('coverage','normals','raster-finish'))+tuple('native/accelerators/host-geometry/'+name for name in ('cold_kernels.c','host_geometry.py'))


def verify(root,directory,system=None,machine=None):
    root=Path(root);directory=Path(directory)
    receipt=json.loads((directory/'provenance.json').read_text())
    system=platform.system() if system is None else system
    machine=platform.machine() if machine is None else machine
    if receipt.get('schema_version')!=1 or receipt.get('abi')!=1 or receipt.get('system')!=system or receipt.get('machine')!=machine:
        raise ValueError('host geometry platform/ABI provenance mismatch')
    if set(receipt.get('sources',{}))!=set(SOURCES):raise ValueError('host geometry source closure mismatch')
    library=directory/'libgeometry.dylib'
    if not stat.S_ISREG(library.lstat().st_mode):raise ValueError('host geometry asset is not a regular file')
    if hashlib.sha256(library.read_bytes()).hexdigest()!=receipt.get('library_sha256'):raise ValueError('host geometry binary provenance mismatch')
    for name,wanted in receipt['sources'].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=wanted:raise ValueError('host geometry source provenance mismatch: '+name)
    return library,root/'native/accelerators/host-geometry/host_geometry.py'


def select(root=None,directory=None):
    root=Path(root) if root is not None else Path(__file__).resolve().parent
    directory=Path(directory) if directory is not None else root/'native/build-host'/('-'.join((platform.system(),platform.machine(),'geometry')))
    library,adapter=verify(root,directory)
    import geometry_compute
    return geometry_compute.configure_host_stages(library,adapter)
