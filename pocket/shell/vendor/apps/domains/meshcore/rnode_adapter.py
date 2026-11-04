#!/usr/bin/env python3
"""RNode KISS compatibility PTY for HTIT service 3; not a firmware flasher.

Radio configuration is applied only on an explicit KISS radio-on command.
Commands are never replayed after an ambiguous transport failure.
"""
import argparse
from collections import deque
import os
import select
import struct
import time
if __package__:from .hub_transport import Link, Endpoint, check_reply
else:from hub_transport import Link, Endpoint, check_reply


def kiss(command, data):
    body=bytes([command])+data
    return b'\xc0'+body.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')+b'\xc0'


class KissDecoder:
    def __init__(self):self.data=bytearray();self.active=False;self.escape=False;self.bad=False
    def feed(self,raw):
        result=[]
        for byte in raw:
            if byte==0xc0:
                if self.active and self.data and not self.bad and not self.escape:result.append((self.data[0],bytes(self.data[1:])))
                self.data.clear();self.active=True;self.bad=False;self.escape=False
            elif self.active and not self.bad:
                if self.escape:
                    if byte not in (0xdc,0xdd):self.bad=True;continue
                    byte=0xc0 if byte==0xdc else 0xdb;self.escape=False
                elif byte==0xdb:self.escape=True;continue
                self.data.append(byte)
                if len(self.data)>509:self.bad=True
        return result


class Adapter:
    def __init__(self,link,endpoint):
        self.link,self.endpoint=link,endpoint
        self.values={};self.pending={};self.queue=deque();self.online=False;self.configuring=False
        self.last_renew=time.monotonic();self.decoder=KissDecoder();self.tx=False
        self.claimed=False;self.configuration=None
    def emit(self,command,data):self.endpoint.queue(kiss(command,data))
    def error(self,code=1):self.emit(0x90,bytes([code]))
    def request(self,op,data=b'',purpose=None):
        ident=self.link.send(3,op,data);self.pending[ident]=(op,purpose,time.monotonic());return ident
    def off(self):
        if any(purpose=='off' for _,purpose,_ in self.pending.values()):return
        active=self.claimed or self.configuring or bool(self.pending)
        # Replies from abandoned configuration/TX must never enable or replay
        # after the caller has requested shutdown.
        self.pending.clear();self.queue.clear();self.configuration=None
        self.online=False;self.configuring=False;self.tx=False;self.claimed=False
        if active:self.request(6,purpose='off')
        else:self.emit(6,b'\0')
    def command(self,command,data):
        if command==8 and data==b'\x73':self.emit(8,b'\x46')
        elif command==0x50:self.emit(command,bytes([1,52])) # compatibility level, not upstream firmware identity
        elif command==0x48:self.emit(command,b'\x90') # no display extension
        elif command==0x49:self.emit(command,b'\x00')
        elif command in (1,2,3,4,5):
            if self.online or self.configuring:self.error();return
            size=4 if command in (1,2) else 1
            if len(data)!=size:self.error();return
            self.values[command]=int.from_bytes(data,'big')
        elif command in (0x0b,0x0c):
            if data!=b'\0\0':self.error();return # nonzero airtime-limit policy not implemented
            self.emit(command,data)
        elif command==6:
            if data==b'\xff':self.emit(6,bytes([self.online]));return
            if data==b'\0':self.off();return
            if data!=b'\1' or set(self.values)!={1,2,3,4,5} or self.configuring or any(p=='off' for _,p,_ in self.pending.values()):self.error();return
            self.configuring=True
            v=self.values
            try:config=struct.pack('<IIBBB',v[1],v[2],v[4],v[5],v[3])
            except struct.error:self.configuring=False;self.error();return
            self.configuration=config
            if self.claimed:self.request(2,config,'configure')
            else:self.request(1,purpose='claim')
        elif command==0:
            if not self.online or not 1<=len(data)<=508:self.error(2)
            elif len(self.queue)>=4:self.error(4)
            else:self.queue.append(data)
        elif command==0x0a:self.off()
        elif command==7:self.emit(command,b'\0')
        else:self.error()
    def frame(self,frame):
        if frame.service!=3:return
        if frame.op==0x90:
            if len(frame.data)<4:return
            rssi=struct.unpack('<h',frame.data[:2])[0]
            self.emit(0x23,bytes([max(0,min(255,rssi+157))]));self.emit(0x24,frame.data[2:3]);self.emit(0,frame.data[3:]);return
        item=self.pending.pop(frame.id,None)
        if item is None:return
        op,purpose,_=item
        if frame.op!=op|0x80:raise ValueError('Unexpected LoRa acknowledgement')
        try:check_reply(frame)
        except (ValueError,RuntimeError):
            if purpose in ('claim','renew'):raise ConnectionError('LoRa ownership unavailable; stop without replay')
            self.configuring=False
            if purpose=='tx':self.tx=False;self.queue.clear();self.error(2)
            else:self.online=False;self.error()
            return
        if purpose=='claim':
            self.claimed=True;self.last_renew=time.monotonic()
            if self.configuration is not None:self.request(2,self.configuration,'configure')
        elif purpose=='configure':self.request(3,b'\1','on')
        elif purpose=='on':
            self.configuring=False;self.online=True
            for cmd in (1,2,3,4,5):self.emit(cmd,self.values[cmd].to_bytes(4 if cmd in (1,2) else 1,'big'))
            self.emit(6,b'\1');self.emit(0x0f,b'\1')
        elif purpose=='off':
            self.claimed=False;self.online=False;self.configuring=False;self.tx=False
            self.configuration=None;self.queue.clear();self.emit(6,b'\0')
        elif purpose=='tx':self.tx=False;self.emit(0x0f,b'\1')
    def tick(self):
        now=time.monotonic()
        if any(now-start>65 for _,_,start in self.pending.values()):raise TimeoutError('LoRa acknowledgement missing; no replay')
        if self.claimed and now-self.last_renew>10:self.request(1,purpose='renew');self.last_renew=now
        if self.online and not self.tx and self.queue:self.tx=True;self.request(4,self.queue.popleft(),'tx')
    def run(self):
        while True:
            readers=[self.link.serial.fileno(),self.endpoint.master]
            writable=[self.endpoint.master] if self.endpoint.output else []
            timeout=max(.01,10-(time.monotonic()-self.last_renew)) if self.claimed else 10
            r,w,_=select.select(readers,writable,[],timeout)
            if w:self.endpoint.flush()
            if self.link.serial.fileno() in r:self.link.read()
            if self.endpoint.master in r:
                raw=os.read(self.endpoint.master,4096)
                if not raw:raise OSError('RNode PTY closed')
                for command,data in self.decoder.feed(raw):self.command(command,data)
            while self.link.inbox:self.frame(self.link.inbox.popleft())
            self.tick()


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--port',required=True)
    args=parser.parse_args();link=Link(args.port);endpoint=None
    try:
        hello=link.hello()
        if len(hello)!=3 or not hello[2]&8:raise ValueError('Hub lacks onboard LoRa service')
        endpoint=Endpoint('RNODE_PORT');adapter=Adapter(link,endpoint);adapter.run()
    finally:
        try:link.send(3,6)
        except Exception:pass
        if endpoint:endpoint.close()
        link.close()

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
