"""Small build-time ambient palette; decode one requested viewport, no FP math."""
from array import array
from functools import lru_cache
from pathlib import Path
import struct
import sys
import zlib

MAGIC=b'CWAMB01\0'
_info=dict(source='not requested',error=None,decodes=0,fallbacks=0)


@lru_cache(maxsize=1)
def _table():
    data=Path(__file__).with_name('data').joinpath('loader-ambient.zlib').read_bytes()
    magic,width,height,count=struct.unpack_from('<8sHHH',data)
    if magic!=MAGIC or (width,height)!=(64,32) or not 1<=count<=256:raise ValueError('ambient table header')
    start=14;end=start+4*count
    palette=array('I');palette.frombytes(data[start:end])
    offsets=array('I');offsets.frombytes(data[end:end+4*(64*32+1)])
    if palette.itemsize!=4 or offsets.itemsize!=4:raise ValueError('ambient table integer width')
    if sys.byteorder!='little':palette.byteswap();offsets.byteswap()
    base=end+4*(64*32+1)
    if len(offsets)!=2049 or offsets[0]!=0 or offsets[-1]!=len(data)-base:raise ValueError('ambient table offsets')
    colors=tuple(('▄',(1<<48)|(value<<24)) for value in palette)
    return data,base,offsets,colors


@lru_cache(maxsize=2)
def lookup(width,height):
    if not 1<=width<=64 or not 1<=height<=32:return None
    try:
        data,base,offsets,colors=_table();index=(height-1)*64+width-1
        left,right=offsets[index:index+2]
        if not 0<=left<=right<=len(data)-base:raise ValueError('ambient entry offsets')
        decoder=zlib.decompressobj();raw=decoder.decompress(data[base+left:base+right],width*height+1)
        if len(raw)!=width*height or not decoder.eof or decoder.unused_data:raise ValueError('ambient entry length')
        result=tuple(colors[value] for value in raw)
    except (OSError,ValueError,IndexError,struct.error,zlib.error) as error:
        _info.update(source='reference fallback',error=str(error));_info['fallbacks']+=1
        return None
    _info.update(source='precomputed',error=None);_info['decodes']+=1
    return result


def status():return dict(_info)
