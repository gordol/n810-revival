"""Immutable packaged release identity; no discovery or subprocesses."""
import os
from types import MappingProxyType

FIELDS=('release_id','framework_commit','domain_commit','platform','backend','artifact_sha256','touch_acquisition_default','product_version')
LABELS=('Release','Framework commit','Domain commit','Packaged platform target','Packaged backend hint','Payload manifest hash','Touch acquisition default','Product version')
UNKNOWN='UNKNOWN'
_PACKAGED_RELEASE=UNKNOWN


def load(path=None):
    import json
    path=path if path is not None else os.path.join(os.path.dirname(__file__),'build-info.json')
    data={}
    try:
        with open(path,'rb') as source:raw=source.read(16385)
        if len(raw)<=16384:
            candidate=json.loads(raw)
            if isinstance(candidate,dict) and type(candidate.get('schema_version')) is int and candidate['schema_version']==1:data=candidate
    except (OSError,ValueError,UnicodeError):pass
    def field(name):
        value=data.get(name)
        if name=='touch_acquisition_default':return 'process' if value=='process' else 'python'
        return value if isinstance(value,str) and 0<len(value)<=160 and all(32<=ord(c)<127 for c in value) else UNKNOWN
    return MappingProxyType({name:field(name) for name in FIELDS})


def current():
    if 'IDENTITY' not in globals():globals()['IDENTITY']=load()
    return globals()['IDENTITY']


def __getattr__(name):
    if name=='IDENTITY':return current()
    raise AttributeError(name)


def release_id():
    return _PACKAGED_RELEASE if _PACKAGED_RELEASE!=UNKNOWN else current()['release_id']


def details(identity=None):
    if identity is None:identity=current()
    return tuple(zip(LABELS,(identity[name] for name in FIELDS)))


def panel_entries(width,clock,connectivity=(),desktops=(),identity=None):
    """Optional identity yields to clock, link status and desktop controls."""
    if identity is None:identity=current()
    label='build '+identity['release_id'][:20]+'  '
    occupied=sum(len(text) for _,text in tuple(clock)+tuple(connectivity)+tuple(desktops))
    if width<120 or width-occupied<len(label)+24:return []
    return [('Settings',label)]
