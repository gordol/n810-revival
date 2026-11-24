"""Opt-in local co-op. The host owns the basket, round and rewards."""
import ipaddress
import itertools
import secrets
import socket
import struct
import time

from river_walk import BUSHES, BerryTrail

PORT=43817
# Binary fixed-size packets bound parsing and carry only game coordinates.
MOVE=struct.Struct('!4sHIIIhhB')
STATE=struct.Struct('!4sHIIIIBB')
PLAYER=struct.Struct('!Ihh')
VERSION=b'ORB1'
SNAP=b'ORS1'
LIMIT=8


class RiverParty:
    def __init__(self,hosting,code=None,address='255.255.255.255',port=PORT):
        self.hosting=hosting
        self.code=code if code is not None else secrets.randbelow(9000)+1000
        self.ident=secrets.randbelow(2**31)+1
        self.destination=(str(ipaddress.IPv4Address(address)),port)
        self.server=None
        self.round=1 if hosting else 0
        self.sequence=0
        self.move_seq=0
        self.last_send=-1.
        self.received=None
        self.players={}
        self.roster={}
        self.restart=False
        self.hearts=0
        self.trail=BerryTrail()
        self.sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        try:
            self.sock.setblocking(False)
            self.sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
            self.sock.bind(('',port if hosting else 0))
        except OSError:
            self.close()
            raise

    def close(self):
        self.sock.close()

    def _send(self,data,to):
        try:self.sock.sendto(data,to)
        except OSError:pass  # Repeat the complete snapshot on the next tick.

    def step(self,x,z,now=None):
        now=time.monotonic() if now is None else now
        pos=(round(10*max(-1000,min(1000,x))),round(10*max(-1000,min(1000,z))))
        for _ in range(32):
            try:data,addr=self.sock.recvfrom(256)
            except (BlockingIOError,OSError):break
            if self.hosting and len(data)==MOVE.size:
                tag,code,uid,epoch,serial,px,pz,replay=MOVE.unpack(data)
                if tag!=VERSION or code!=self.code or uid in (0,self.ident) or max(abs(px),abs(pz))>10000:continue
                old=self.players.get(uid)
                if old and (old[0]!=addr or serial<=old[5]):continue
                if not old and len(self.players)>=LIMIT-1:continue
                self.players[uid]=(addr,now,px,pz,epoch,serial)
                if replay and epoch==self.round and self.trail.fed:self.restart=True
            elif not self.hosting and len(data)>=STATE.size and (self.server is None or addr==self.server):
                tag,code,seq,epoch,hearts,host,mask,n=STATE.unpack_from(data)
                if tag!=SNAP or code!=self.code or seq<=self.sequence or not 1<=n<=LIMIT or len(data)!=STATE.size+n*PLAYER.size:continue
                roster={uid:(px,pz) for uid,px,pz in PLAYER.iter_unpack(data[STATE.size:])}
                if self.ident not in roster or host not in roster:continue
                self.server=addr;self.received=now;self.sequence=seq
                if epoch!=self.round:self.restart=False
                self.round=epoch;self.hearts=hearts
                self.trail.picked={p for i,p in enumerate(BUSHES) if mask&(1<<i)}
                self.trail.fed=bool(mask&8);self.roster=roster
        if not self.hosting and self.received is not None and now-self.received>5:
            self.server=self.received=None
            self.sequence=0;self.round=0;self.roster={};self.restart=False
        if now-self.last_send<.12:return
        self.last_send=now
        if not self.hosting:
            self.move_seq+=1
            self._send(MOVE.pack(VERSION,self.code,self.ident,self.round,self.move_seq,*pos,int(self.restart)),self.server or self.destination)
            return
        self.players={uid:p for uid,p in self.players.items() if now-p[1]<5}
        if self.restart and self.trail.fed:
            self.trail=BerryTrail();self.round+=1
        self.restart=False
        was_fed=self.trail.fed
        self.roster={self.ident:pos,**{uid:(p[2],p[3]) for uid,p in self.players.items()}}
        for px,pz in itertools.chain([pos],((p[2],p[3]) for p in self.players.values() if p[4]==self.round)):
            self.trail.visit(px/10,pz/10)
        if self.trail.fed and not was_fed:self.hearts+=1
        self.sequence+=1
        mask=sum(1<<i for i,p in enumerate(BUSHES) if p in self.trail.picked)|(8 if self.trail.fed else 0)
        state=STATE.pack(SNAP,self.code,self.sequence,self.round,self.hearts,self.ident,mask,len(self.roster))
        state+=b''.join(PLAYER.pack(uid,*p) for uid,p in self.roster.items())
        for addr,*_ in self.players.values():self._send(state,addr)


class PartyMenu:
    def __init__(self,view):
        self.view=view
        self.digits=None
        self.error=''

    def lines(self,width):
        party=self.view.party
        if party:
            count=len(party.roster)
            status='Waiting for the host...' if not party.hosting and party.server is None else f'{count} on the trail'
            return ('Family walk','',f'Room {party.code}   {status}','','[ Walk together ]','','[ Leave room ]')
        if self.digits is None:
            return ('Family walk','', '[ Host on this Wi-Fi ]','','[ Join with a code ]','','[ Back ]',self.error)
        return ('Enter the four-digit room code','',self.digits.ljust(4,'_'),'',
                '   1       2       3','','   4       5       6','','   7       8       9','',
                '  Back     0     Delete',self.error)

    def tap_xy(self,x,y):
        import os
        if self.view.party:
            if y in (5,6,7):self.view.leave_party();return False
            return y not in (3,4)
        if self.digits is None:
            if y in (5,6,7):return False
            if y in (3,4):self.digits='';return True
            if y not in (1,2):return True
            host=True;code=None
        else:
            row=(y-3)//2
            if row not in range(4) or not 0<=x<24:return True
            col=x//8
            if row==3 and col==0:self.digits=None;return True
            if row==3 and col==2:self.digits=self.digits[:-1];return True
            self.digits+=str(0 if row==3 else 3*row+col+1)
            if len(self.digits)<4:return True
            host=False;code=int(self.digits)
        try:
            party=RiverParty(host,code,os.environ.get('POCKET_RIVER_HOST','255.255.255.255'))
        except (ValueError,OSError) as error:
            self.error=str(error);self.digits=None
        else:
            self.view.enter_party(party)
        return True
