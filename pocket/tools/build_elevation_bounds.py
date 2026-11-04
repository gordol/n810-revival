"""Build conservative maxima from prepared elevations, never from averages."""
from array import array
import hashlib,json,sys,zlib
from pathlib import Path


def build(directory):
    directory=Path(directory);path=directory/'index.json';meta=json.loads(path.read_text())
    size=16;nx=(meta['nx']+size-1)//size;ny=(meta['nz']+size-1)//size
    maxima=[-32767]*(nx*ny)
    try:import numpy as np
    except ImportError:np=None
    for key,item in meta['tiles'].items():
        tx,ty=map(int,key.split(','));raw=(directory/item['file']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('Tile checksum mismatch')
        values=array('h');values.frombytes(zlib.decompress(raw))
        if sys.byteorder!='little':values.byteswap()
        if np is not None:
            values_np=np.array(values,dtype=np.int32).reshape(item['height'],item['width'])
            values_np[values_np==meta['nodata']]=32767
            padded=np.full((((item['height']+size-1)//size)*size,((item['width']+size-1)//size)*size),-32767)
            padded[:item['height'],:item['width']]=values_np
            blocks=padded.reshape(padded.shape[0]//size,size,padded.shape[1]//size,size).max(axis=(1,3))
            for y,row in enumerate(blocks):
                start=(ty*256//size+y)*nx+tx*256//size
                maxima[start:start+len(row)]=list(map(int,row))
            continue
        for y in range(item['height']):
            for x in range(item['width']):
                i=((ty*256+y)//size)*nx+(tx*256+x)//size;v=values[y*item['width']+x]
                if v==meta['nodata']:maxima[i]=32767 # Unknown cannot establish clearance.
                elif maxima[i]!=32767:maxima[i]=max(maxima[i],v)
    meta['maximum_bounds']=dict(block_size=size,nx=nx,nz=ny,unknown=32767,values=maxima,
        basis='Maximum of every prepared DEM cell; unknown cells prevent pruning')
    path.write_text(json.dumps(meta,separators=(',',':'))+'\n')
    print(dict(blocks=len(maxima),bytes=path.stat().st_size))


if __name__=='__main__':build(sys.argv[1])
