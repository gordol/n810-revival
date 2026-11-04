"""Discovery storage uses the same MessagePack codec as the service framework."""
from wire import codec as _codec, NATIVE_CODEC


def pack(value):
    return _codec.packb(value,use_bin_type=True) if NATIVE_CODEC else _codec.packb(value)


def unpack(data):
    try:
        return _codec.unpackb(data,raw=False,strict_map_key=False) if NATIVE_CODEC else _codec.unpackb(data)
    except (ValueError,TypeError,_codec.UnpackException) as error:
        raise ValueError('Invalid discovery MessagePack') from error


class _DiscoveryCodec:
    packb=staticmethod(pack)
    unpackb=staticmethod(unpack)
    UnpackException=ValueError


def codec():
    return _DiscoveryCodec


def legacy_value(raw):
    """Import an old serialized value at a migration/external-card boundary."""
    import json
    return json.loads(raw)


def atomic_write(path,value):
    """Durable private binary state, without changing a service's schema."""
    import os,tempfile
    from pathlib import Path
    path=Path(path);temporary=None
    try:
        fd,temporary=tempfile.mkstemp(prefix='.state-',dir=path.parent)
        with os.fdopen(fd,'wb') as stream:
            stream.write(pack(value));stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
        directory=os.open(path.parent,os.O_RDONLY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        if temporary is not None:
            try:os.unlink(temporary)
            except FileNotFoundError:pass
