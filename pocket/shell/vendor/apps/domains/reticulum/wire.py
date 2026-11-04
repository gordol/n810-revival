"""Bounded MessagePack frames shared by local owners and service transports."""
import io
import math
import struct
try:
    import msgpack as codec
    NATIVE_CODEC=codec.Packer.__module__.endswith('._cmsgpack')
except ImportError:
    NATIVE_CODEC=False
if not NATIVE_CODEC:
    if __package__:
        from . import _umsgpack as codec
    else:
        import _umsgpack as codec

LIMIT=32768
MAGIC=b'PS\x02'
HEADER=7
_SCALARS=(str,bytes,int,bool,type(None))

def validate(value,depth=0):
    if depth>24:raise ValueError('Service nesting limit exceeded')
    if type(value) in _SCALARS:return
    if isinstance(value,dict):
        if any(not isinstance(k,str) for k in value):raise ValueError('Service keys must be strings')
        for item in value.values():validate(item,depth+1)
    elif isinstance(value,(list,tuple)):
        for item in value:validate(item,depth+1)
    elif isinstance(value,float):
        if not math.isfinite(value):raise ValueError('Invalid service number')
    elif not isinstance(value,_SCALARS):raise ValueError('Unsupported service value')

def encode(value):
    validate(value)
    raw=codec.packb(value,use_bin_type=True) if NATIVE_CODEC else codec.packb(value)
    if not 1<=len(raw)<=LIMIT-HEADER:raise ValueError('Service frame exceeds limit')
    return MAGIC+struct.pack('!I',len(raw))+raw

def frame_size(raw):
    if len(raw)<HEADER:return None
    if raw[:3]!=MAGIC:raise ValueError('Binary service protocol required; update both endpoints')
    length=struct.unpack('!I',raw[3:HEADER])[0]
    if not 1<=length<=LIMIT-HEADER:raise ValueError('Service frame exceeds limit')
    return HEADER+length

def _unique_map(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate service key')
        result[key]=value
    return result

def decode(raw):
    size=frame_size(raw)
    if size is None or size!=len(raw):raise ValueError('Invalid service framing')
    try:
        if NATIVE_CODEC:
            value=codec.unpackb(raw[HEADER:],raw=False,strict_map_key=False,
                max_str_len=LIMIT,max_bin_len=LIMIT,max_array_len=LIMIT,max_map_len=LIMIT,max_ext_len=LIMIT,object_pairs_hook=_unique_map)
        else:
            stream=io.BytesIO(raw[HEADER:]);value=codec.unpack(stream)
            if stream.read(1):raise ValueError('Trailing service data')
        validate(value)
    except (codec.UnpackException,RecursionError,TypeError) as error:raise ValueError('Invalid binary service frame') from error
    if not isinstance(value,dict) or type(value.get('version')) is not int or value['version']!=1:raise ValueError('Invalid service version')
    # An owner snapshot may describe a failed radio operation while its
    # management endpoint and recovery actions remain available.
    if value.get('error') and value.get('owner_online') is not True:raise ValueError(str(value['error']))
    return value

def read(stream):
    header=stream.read(HEADER)
    size=frame_size(header)
    if size is None:raise ConnectionError('Service disconnected during frame header')
    return decode(header+stream.read(size-HEADER))


def exchange(path, request):
    import _socket as socket
    raw = encode(request)
    client=socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        if request.get('action') in ('service_call','service_share'):
            if __package__:from .service_transport import request_timeout
            else:from service_transport import request_timeout
            client.settimeout(request_timeout(request)+10)
        else: client.settimeout(None if request.get('action') == 'connect' else 2)
        client.connect(str(path))
        client.sendall(raw)
        return read_socket(client)
    finally:client.close()


def read_socket(client):
    """Read one bounded frame directly from a native socket, including short reads."""
    def take(size):
        chunks=bytearray()
        while len(chunks)<size:
            chunk=client.recv(size-len(chunks))
            if not chunk:raise ConnectionError('Service disconnected during frame')
            chunks.extend(chunk)
        return bytes(chunks)
    header=take(HEADER)
    size=frame_size(header)
    return decode(header+take(size-HEADER))
