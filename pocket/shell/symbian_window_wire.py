"""Bounded Symbian window messages; pixel storage remains owned by Mesa."""
import struct

MAGIC=b'SWN1'
BEGIN,READY,FRAME,ACK,CLOSE,PAUSE,RESUME,ERROR=range(1,9)
HEADER=struct.Struct('<4sIQIIII')
IMAGE=struct.Struct('<12I') # destination rectangle followed by opaque Mesa descriptor
MAX_IMAGES=14
MAX_PACKET=HEADER.size+MAX_IMAGES*IMAGE.size


def packet(kind,serial=0,width=0,height=0,images=()):
    images=tuple(images)
    if kind not in range(BEGIN,ERROR+1) or not 0<=serial<2**64:raise ValueError('Invalid window message')
    if kind==FRAME:
        if not 1<=len(images)<=MAX_IMAGES or not 1<=width<=800 or not 1<=height<=480:raise ValueError('Invalid window frame')
        rectangles=[];area=0
        for image in images:
            if len(image)!=12:raise ValueError('Invalid image descriptor')
            x,y,w,h,version,iw,ih,fmt,session,generation,slot,reserved=image
            if min(x,y)<0 or min(w,h)<=0 or x+w>width or y+h>height or w>iw or h>ih:raise ValueError('Image outside frame')
            if iw>800 or ih>480 or fmt!=1 or not session or not generation or slot>=14:raise ValueError('Invalid retained image')
            if version==1:
                if (iw,ih)!=(128,128) or reserved:raise ValueError('Invalid legacy GPU image')
            elif version==2:
                if reserved!=iw*4 or ((iw,ih)!=(240,320) if slot<2 else (iw,ih)!=(128,128)):raise ValueError('Invalid native GPU image')
            else:raise ValueError('Unknown GPU image ABI')
            if any(x<a+c and a<x+w and y<b+d and b<y+h for a,b,c,d in rectangles):raise ValueError('Overlapping window images')
            rectangles.append((x,y,w,h));area+=w*h
        if area!=width*height:raise ValueError('Incomplete window frame')
        if len({image[10] for image in images})!=len(images):raise ValueError('Repeated image slot')
    elif images or width or height:raise ValueError('Unexpected frame payload')
    return HEADER.pack(MAGIC,kind,serial,width,height,len(images),0)+b''.join(IMAGE.pack(*image) for image in images)


def decode(data):
    if len(data)<HEADER.size or len(data)>MAX_PACKET:raise ValueError('Invalid window packet size')
    magic,kind,serial,width,height,count,reserved=HEADER.unpack_from(data)
    if magic!=MAGIC or reserved or count>MAX_IMAGES or len(data)!=HEADER.size+count*IMAGE.size:raise ValueError('Invalid window packet')
    images=tuple(IMAGE.unpack_from(data,HEADER.size+i*IMAGE.size) for i in range(count))
    if packet(kind,serial,width,height,images)!=data:raise ValueError('Invalid window message')
    return kind,serial,width,height,images
