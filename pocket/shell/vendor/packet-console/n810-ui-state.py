"""Small UI state files. Written only on navigation away or clean exit."""
import json
import os
from pathlib import Path
import tempfile


def root():return Path.home()/'.local/state/n810-aprs/ui'


def load(name):
    try:
        value=json.loads((root()/(name+'.json')).read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def save(name,value):
    folder=root();folder.mkdir(parents=True,exist_ok=True)
    fd,path=tempfile.mkstemp(prefix=name+'-',dir=folder)
    try:
        with os.fdopen(fd,'w') as f:json.dump(value,f)
        os.replace(path,folder/(name+'.json'))
    finally:
        if os.path.exists(path):os.unlink(path)
