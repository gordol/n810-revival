"""Secondary memory selection with APRS A and digital-channel fields preserved."""
import struct
from uvpro_tune import payload


def bits(raw,offset,width):return int.from_bytes(raw,'big')>>(len(raw)*8-offset-width)&((1<<width)-1)


def put(raw,offset,width,value):
    shift=len(raw)*8-offset-width;mask=((1<<width)-1)<<shift
    return ((int.from_bytes(raw,'big')&~mask)|(value<<shift)).to_bytes(len(raw),'big')


def field(layout,name):
    offset=0
    for key,width,kind in layout:
        if key==name:return offset,width
        offset+=width
    raise ValueError('Missing field '+name)


def settings(original,index,layout):
    if len(original)!=22 or not 0<=index<256:raise ValueError('Unsupported settings layout')
    desired=original
    for name,value in (('channel_b_lower',index&15),('channel_b_upper',index>>4),('double_channel',2)):
        desired=put(desired,*field(layout,name),value)
    return desired


def protected(raw,layout):
    a=bits(raw,*field(layout,'channel_a_upper'))*16+bits(raw,*field(layout,'channel_a_lower'))
    digital=bits(raw,*field(layout,'auto_share_loc_ch_upper'))*32+bits(raw,*field(layout,'auto_share_loc_ch'))-1
    return a,digital


def channel(template,index,repeater):
    if len(template) not in (25,27):raise ValueError('Unsupported FM channel layout')
    rx,tx,rt,tt,_,_=struct.unpack('>IIHHHH',payload(repeater))
    raw=template
    for offset,width,value in ((0,8,index),(8,2,0),(10,30,tx),(40,2,0),(42,30,rx),
                               (72,16,tt),(88,16,rt),(104,1,0),(106,1,0),(107,1,int('FM wide' in repeater['modes'])),
                               (108,1,0),(111,1,0),(112,1,0),(113,1,0),(115,1,0)):
        raw=put(raw,offset,width,value)
    label=str(repeater.get('call') or repeater.get('name') or repeater.get('site') or ('%.3f'%repeater['rx_mhz']))
    label=''.join(c for c in label if 32<=ord(c)<=126).strip()[:10] or 'Repeater'
    return raw[:15]+label.encode('ascii').ljust(10,b'\0')+raw[25:]


def matches(raw,repeater):
    if len(raw) not in (25,27):return False
    desired=channel(raw,raw[0],repeater)
    return all(bits(raw,o,w)==bits(desired,o,w) for o,w in ((8,64),(72,32),(107,1)))
