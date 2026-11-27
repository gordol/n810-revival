"""Distant Cascades and Puget Sound from a private Mapzen Terrarium tile cache."""
from array import array
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen
import zlib

# Registered to every eighth sample of the original 3DEP Rainier export.
SIZE=257
MID=SIZE//2
LAT,LON=46.795,-121.76
DLAT,DLON=8*.53/257,8*.68/257
PIXELS=128*256


def offset(index):
    """World offset in original grid steps; spend more samples near Rainier."""
    distance=abs(index)
    steps=.5*min(distance,64)+1.5*max(0,distance-64)
    return math.copysign(steps,index)


def pixel(lon,lat):
    return (int((lon+180)/360*PIXELS),
            int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)*PIXELS/2))


def convert(stage):
    from PIL import Image
    data=array('h')
    tiles={}
    for j in range(SIZE):
        for i in range(SIZE):
            x,y=pixel(LON+offset(i-MID)*DLON,LAT+offset(j-MID)*DLAT)
            key=(x//256,y//256)
            if key not in tiles:
                with Image.open(stage/f'{key[0]}-{key[1]}.png') as im:
                    if im.size!=(256,256):raise ValueError('Invalid horizon tile')
                    tiles[key]=im.convert('RGB')
            r,g,_=tiles[key].getpixel((x%256,y%256))
            data.append(256*r+g-32768)
    if sys.byteorder!='little':data.byteswap()
    (stage/'grid').write_bytes(zlib.compress(data.tobytes()))


def samples():
    from data_paths import rainier_cache
    target=rainier_cache()/'horizon-terrarium-v2.i16.zlib'
    def read(path):
        raw=zlib.decompress(path.read_bytes())
        if len(raw)!=SIZE*SIZE*2:raise ValueError('Incomplete horizon grid')
        data=array('h')
        data.frombytes(raw)
        if sys.byteorder!='little':data.byteswap()
        return data
    try:return read(target),True
    except (FileNotFoundError,zlib.error,ValueError):pass
    try:
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
            stage=Path(tmp)
            west,north=pixel(LON-MID*DLON,LAT+MID*DLAT)
            east,south=pixel(LON+MID*DLON,LAT-MID*DLAT)
            for x in range(west//256,east//256+1):
                for y in range(north//256,south//256+1):
                    url=f'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/7/{x}/{y}.png'
                    with urlopen(url,timeout=6) as response:raw=response.read(300001)
                    if len(raw)>300000:raise ValueError('Oversize horizon tile')
                    (stage/f'{x}-{y}.png').write_bytes(raw)
            if os.environ.get('POCKET_TERMUX')=='1':
                script=stage/'summit_horizon.py'
                script.write_bytes(Path(__file__).read_bytes())
                subprocess.run(['proot-distro','login','pocket-maps','--bind',tmp,'--','/usr/bin/python3',
                                str(script),tmp],check=True,timeout=30)
            else:convert(stage)
            data=read(stage/'grid')
            (stage/'grid').replace(target)
            return data,True
    except (OSError,ValueError,ImportError,zlib.error,subprocess.SubprocessError):
        old=target.with_name('horizon-terrarium-v1.i16.zlib')
        if old.is_file():return read(old),False
        raise


def append_mesh(out,field,origin_y,data,graded=True):
    """Keep the inner walking mesh intact, stitching each fine edge span."""
    dx,dz=8*field.dx,8*field.dz
    coordinate=offset if graded else float
    seam=32 if graded else 16
    stride=4 if graded else 8
    def vertex(i,j):
        east,north=coordinate(i-MID),coordinate(j-MID)
        x,z=east*dx,north*dz
        edge=max(abs(east),abs(north))
        if edge==16:
            height=field.values[round(128+north*8)*257+round(128+east*8)]
        else:height=data[j*SIZE+i]
        drop=min(1.,(edge-16)/10)*(x*x+z*z)/(2*6371000)
        if height<=0:color=(.16,.37,.52)
        else:
            base=(.29,.40,.33) if height<1300 else (.43,.46,.45) if height<2300 else (.88,.89,.90)
            col,row=round(i),round(j)
            left,right=max(0,col-1),min(SIZE-1,col+1)
            below,above=max(0,row-1),min(SIZE-1,row+1)
            sx=(data[row*SIZE+right]-data[row*SIZE+left])/((coordinate(right-MID)-coordinate(left-MID))*dx)
            sz=(data[above*SIZE+col]-data[below*SIZE+col])/((coordinate(above-MID)-coordinate(below-MID))*dz)
            # Northwest illumination reveals north/south as well as east/west relief.
            light=(.62+.55*sx-.55*sz)/math.sqrt(1+sx*sx+sz*sz)
            shade=.45+.76*max(0.,light)
            color=tuple(c*shade for c in base)
        return (x,max(0,height)-drop-origin_y,z,*color,0.)
    lo,hi=MID-seam,MID+seam
    previous=[]
    for j in range(SIZE):
        row=[vertex(i,j) if max(abs(i-MID),abs(j-MID))>=seam else None for i in range(SIZE)]
        if previous:
            for i in range(SIZE-1):
                if lo<=i<hi and lo<j<=hi:continue
                corners=[previous[i],previous[i+1],row[i+1],row[i]]
                edge=None
                if lo<=i<hi and j in (lo,hi+1):edge=2 if j==lo else 0
                if lo<j<=hi and i in (lo-1,hi):edge=1 if i==lo-1 else 3
                if edge is None:
                    for v in (corners[0],corners[3],corners[1],corners[1],corners[3],corners[2]):out.extend(v)
                    continue
                offsets=((0,-1),(1,-1),(1,0),(0,0))
                ax,az=offsets[edge]
                bx,bz=offsets[(edge+1)%4]
                anchor=corners[(edge+2)%4]
                last=corners[edge]
                for step in range(1,stride+1):
                    t=step/stride
                    point=vertex(i+ax+(bx-ax)*t,j+az+(bz-az)*t)
                    for v in (anchor,point,last):out.extend(v)
                    last=point
                for v in (anchor,corners[edge],corners[(edge+3)%4]):out.extend(v)
        previous=row


if __name__=='__main__':convert(Path(sys.argv[1]))
