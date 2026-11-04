"""Explicit MeshCore owner selection; no radio activity at shell launch."""
import os
from pathlib import Path
import stat
import re


def saved_selection(directory):
    path=Path(directory)/'meshcore-owner.toml'
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>4096:raise ValueError('MeshCore configuration must be a private user-owned TOML file')
        raw=stream.read(4097)
    if len(raw)>4096:raise ValueError('MeshCore configuration exceeds limit')
    # Cache validated configuration using the framework's bounded binary wire
    # format. Still check the original file's ownership/mode and exact contents
    # on every read. Editing the TOML invalidates this cache automatically.
    from vendor.apps.domains.reticulum import wire
    cache=path.with_suffix('.cache')
    try:
        fd=os.open(cache,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>12288:raise ValueError('Invalid configuration cache')
            value=wire.decode(stream.read(12289))
        if value.get('source')==raw:return validate_selection(value['selection'])
    except (OSError,ValueError,KeyError,TypeError):pass
    import tomllib
    data=tomllib.loads(raw.decode())
    selection=validate_selection(data)
    temporary=str(cache)+'.'+str(os.getpid())+'.tmp'
    try:
        fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(wire.encode(dict(version=1,source=raw,selection=data)))
            os.replace(temporary,cache)
        finally:
            if os.path.lexists(temporary):os.unlink(temporary)
    except OSError:pass  # A read-only configuration directory remains usable.
    return selection


def validate_selection(data):
    if not isinstance(data,dict):raise ValueError('Invalid MeshCore owner configuration')
    if set(data)=={'socket'}:
        if not isinstance(data['socket'],str) or not Path(data['socket']).is_absolute():raise ValueError('Choose an absolute owner socket')
        return dict(mode='external',**data)
    required={'state','interpreter','station','port','trusted_peripheral'}
    if not required<=set(data) or set(data)-required-{'baudrate'}:raise ValueError('Invalid MeshCore owner configuration')
    hub=isinstance(data['port'],str) and bool(re.fullmatch(r'htit://(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}/(?:[1-9]|[12][0-9]|30)/(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}/[01]',data['port']))
    for key in ('state','interpreter') if hub else ('state','interpreter','port'):
        if not isinstance(data[key],str) or not Path(data[key]).is_absolute() or not data[key].isprintable():raise ValueError('MeshCore '+key+' must be an absolute path')
    if (not hub and not data['port'].startswith('/dev/')) or type(data['trusted_peripheral']) is not bool:raise ValueError('Choose an explicit serial peripheral and trust policy')
    if not isinstance(data['station'],str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}',data['station']):raise ValueError('Invalid station identity')
    speed=data.get('baudrate',115200)
    if type(speed) is not int or not 300<=speed<=4000000:raise ValueError('Invalid serial speed')
    return dict(mode='local',**data)
