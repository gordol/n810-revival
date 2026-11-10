"""Exact self-address preferences shared by clients of one local Directory."""
import json
import os
from pathlib import Path
import tempfile


def _identity_path(db):
    return Path(db).expanduser().resolve().with_name('station-identity.json')


def self_calls(preferences, db=None):
    if db is not None:
        try:
            saved=json.loads(_identity_path(db).read_text())
            from_file=tuple(saved['self_calls'])
            if all(isinstance(call,str) for call in from_file):return from_file
        except (OSError,ValueError,KeyError,TypeError):pass
    if 'station-self' not in preferences:return ()
    group=preferences['station-self']
    return tuple(group[key] for key in sorted(group) if key.startswith('self-call-'))


def save_self_calls(db,calls):
    """Write only local identity settings, atomically and privately."""
    path=_identity_path(db)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.station-identity-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:
            json.dump({'self_calls':list(calls)},stream)
            stream.write('\n')
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def with_self_calls(preferences,calls):
    group={f'self-call-{index:02d}':call for index,call in enumerate(calls)}
    return {**preferences,'station-self':group}
