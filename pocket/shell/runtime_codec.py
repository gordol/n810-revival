"""Pocket runtime values use the framework's MessagePack codec, with bounded frames."""
from pathlib import Path
import importlib.util
import struct
try:
    import msgpack as _codec
    _native=_codec.Packer.__module__.endswith('._cmsgpack')
except ImportError:_native=False
if not _native:
    _spec=importlib.util.spec_from_file_location('_pocket_runtime_msgpack',Path(__file__).parent/'vendor/apps/domains/reticulum/_umsgpack.py')
    _codec=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_codec)

MAGIC=b'PC\x01'
HEADER=7

def copy_data(value):
    """Detach process-local plain data, retaining tuple and numeric types.

    These bytes never leave this call; persistent and wire values use MessagePack.
    """
    import marshal
    return marshal.loads(marshal.dumps(value,2))

def pack(value):
    return _codec.packb(value,use_bin_type=True) if _native else _codec.packb(value)

def unpack(raw,limit=4*1024*1024):
    if not 1<=len(raw)<=limit:raise ValueError('Runtime value exceeds byte limit')
    try:
        if _native:
            return _codec.unpackb(raw,raw=False,strict_map_key=False,max_str_len=limit,max_bin_len=limit,
                max_array_len=limit,max_map_len=limit,max_ext_len=0)
        import io
        stream=io.BytesIO(raw);value=_codec.unpack(stream)
        if stream.read(1):raise ValueError('Trailing runtime data')
        return value
    except (TypeError,RecursionError,_codec.UnpackException) as error:raise ValueError('Invalid binary runtime value') from error

def frame(value,limit=8192):
    raw=pack(value)
    if not 1<=len(raw)<=limit:raise ValueError('Runtime frame exceeds byte limit')
    return MAGIC+struct.pack('!I',len(raw))+raw

def frame_size(raw,limit=8192):
    if len(raw)<HEADER:return None
    if raw[:3]!=MAGIC:raise ValueError('Binary runtime protocol required')
    size=struct.unpack('!I',raw[3:HEADER])[0]
    if not 1<=size<=limit:raise ValueError('Runtime frame exceeds byte limit')
    return HEADER+size

def read_frame(stream,limit=8192):
    header=stream.read(HEADER);size=frame_size(header,limit)
    if size is None:raise ValueError('Incomplete runtime header')
    return unpack(stream.read(size-HEADER),limit)

def atomic_write(path,value):
    """Write private binary state atomically; caller owns schema and migration."""
    import os,tempfile
    path=Path(path);raw=pack(value);temporary=None
    try:
        fd,temporary=tempfile.mkstemp(prefix='.pocket-state-',dir=path.parent)
        with os.fdopen(fd,'wb') as stream:stream.write(raw);stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary is not None:
            try:os.unlink(temporary)
            except FileNotFoundError:pass
