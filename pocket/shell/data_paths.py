"""Shared discovery of packaged reference data; user state stays separate."""
import os
from pathlib import Path

def data_root():
    explicit=os.environ.get('POCKET_DATA_ROOT')
    if explicit:return Path(explicit).expanduser()
    checkout=Path(__file__).resolve().parents[1]/'data'
    if checkout.is_dir():return checkout
    return Path('/usr/share/pocket/data')

def rainier_cache():
    return Path(os.environ.get('XDG_DATA_HOME') or Path.home()/'.local/share')/'pocket/rainier-walk'

def rainier_root():
    root=data_root()
    for directory in (root,rainier_cache()/'regional',rainier_cache()):
        if all((directory/name).is_file() for name in ('tahoma-3dep.json','tahoma-3dep.i16.zlib')):
            return directory
    return root

def map_directory(fallback):
    """One generated map directory for native and terminal readers."""
    current=data_root()/'maps'
    return current if (current/'walk-layers.n8w').is_file() else Path(fallback)

# Stat changes refresh this in-process memo; persisted identities use content.
from functools import lru_cache
import hashlib

@lru_cache(maxsize=256)
def _digest(path,modified,size):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()

def content_identity(path):
    path=Path(path)
    if not path.is_file():return ()
    info=path.stat()
    return (path.parent.name+'/'+path.name,_digest(str(path),info.st_mtime_ns,info.st_size))
