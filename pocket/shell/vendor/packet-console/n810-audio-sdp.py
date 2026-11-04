#!/usr/bin/env python3
"""Bounded SDP-only lookup of the vendor audio UUID; no audio/control connection."""
import argparse
import json
import socket
import struct
import uuid

AUDIO_UUID='39144315-32fa-40db-85ed-fbfeba2d86e6'


def query(transaction=1,continuation=b''):
    if len(continuation)>16:raise ValueError('SDP continuation exceeds protocol bound')
    params=b'\x35\x11\x1c'+uuid.UUID(AUDIO_UUID).bytes+b'\xff\xff\x35\x05\x0a\x00\x00\xff\xff'+bytes([len(continuation)])+continuation
    return struct.pack('>BHH',6,transaction,len(params))+params


def element(data,offset=0,depth=0):
    if depth>12 or offset>=len(data):raise ValueError('Invalid SDP element nesting')
    head=data[offset];kind=head>>3;size=head&7;offset+=1
    if size<=4:length=1<<size
    else:
        count={5:1,6:2,7:4}[size]
        if offset+count>len(data):raise ValueError('Truncated SDP length')
        length=int.from_bytes(data[offset:offset+count],'big');offset+=count
    end=offset+length
    if end>len(data) or length>32768:raise ValueError('Truncated/oversized SDP value')
    value=data[offset:end]
    if kind in (6,7):
        children=[]
        while offset<end:
            child,offset=element(data,offset,depth+1);children.append(child)
        value=children
    return (kind,value),end


def channels(attributes):
    tree,end=element(attributes)
    if end!=len(attributes) or tree[0]!=6:raise ValueError('Invalid SDP attribute list')
    out=[]
    for record in tree[1]:
        if record[0]!=6:continue
        fields=record[1]
        pairs={int.from_bytes(fields[i][1],'big'):fields[i+1] for i in range(0,len(fields)-1,2) if fields[i][0]==1}
        classes=pairs.get(1)
        if not classes or classes[0]!=6 or not any(item[0]==3 and item[1]==uuid.UUID(AUDIO_UUID).bytes for item in classes[1]):continue
        for i in range(0,len(fields)-1,2):
            key,value=fields[i:i+2]
            if key[0]!=1 or int.from_bytes(key[1],'big')!=4 or value[0]!=6:continue
            for protocol in value[1]:
                if protocol[0]!=6 or len(protocol[1])<2:continue
                proto,channel=protocol[1][:2]
                if proto[0]==3 and int.from_bytes(proto[1],'big')==3 and channel[0]==1:
                    number=int.from_bytes(channel[1],'big')
                    if 1<=number<=30:out.append(number)
    return sorted(set(out))


def discover(address):
    data=bytearray();continuation=b''
    with socket.socket(socket.AF_BLUETOOTH,socket.SOCK_SEQPACKET,socket.BTPROTO_L2CAP) as link:
        link.settimeout(5);link.connect((address,1))
        for transaction in range(1,9):
            link.sendall(query(transaction,continuation)) # SDP request only, never audio/control.
            reply=link.recv(65535)
            if len(reply)<8:raise ValueError('Short SDP response')
            kind,identity,size=struct.unpack('>BHH',reply[:5])
            if kind!=7 or identity!=transaction or size!=len(reply)-5:raise ValueError('SDP response rejected/mismatched')
            count=int.from_bytes(reply[5:7],'big');end=7+count
            if end>=len(reply):raise ValueError('Truncated SDP attributes')
            data.extend(reply[7:end]);n=reply[end];continuation=reply[end+1:]
            if n!=len(continuation) or n>16 or len(data)>32768:raise ValueError('Invalid SDP continuation/size')
            if not n:return {'service_uuid':AUDIO_UUID,'rfcomm_channels':channels(bytes(data)),'source':'fresh_sdp_query'}
    raise ValueError('SDP continuation limit exceeded')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--address',required=True)
    try:print(json.dumps(discover(p.parse_args().address)))
    except (OSError,ValueError) as exc:print(json.dumps({'error':str(exc),'audio_connection_opened':False}));raise SystemExit(1)
