#!/usr/bin/env python3
"""Offline walking APRS test. Starts disarmed; explicit on-device ARM permits RF."""
import argparse
import collections
import curses
import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import select
import signal
import socket
import time

BASE=Path(__file__).resolve().parent

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,BASE/file)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj

bridge=module('walk_bridge','n810-kiss-bridge.py')
monitor=module('walk_monitor','n810-packet-monitor.py')
live=module('walk_live','n810-radio-live.py')
terminal=module('walk_terminal','n810-terminal-text.py')
history=module('walk_history','n810-walk-history.py')

visibility=module('walk_visible','n810-ui-visible.py')
map_style=module('walk_map_style','n810-map-style.py')
walk_map=module('walk_indexed_map','n810-walk-map.py')
ink=map_style.ink

rgb_map=module('walk_rgb_map','n810-map-rgb.py')
Plan=module('walk_plan','n810-walk-plan.py').Plan
Journal=module('walk_journal','n810-walk-journal.py').Journal

def init_map_colors(win):
    map_style.init_screen(win);walk_map.init_colors()

def map_attr(kind,terrain=True):
    return walk_map.attr(kind,terrain) if kind.startswith(('band','street','route','contour','stream')) else map_style.cell_attr(kind,terrain)



def fresh_position(state,now):
    p=state.get('position',{})
    try:
        age=now-float(p['time']);received=now-float(state['fields']['position'])
        lat,lon=float(p['lat']),float(p['lon']);accuracy=float(p.get('accuracy',99999))
        if not state.get('connected') or not 0<=now-float(state['heartbeat'])<=12:return None
        if not (-90<=lat<=90 and -180<=lon<=180) or not 0<=age<=30 or not 0<=received<=15:return None
        if not math.isfinite(accuracy) or not 0<accuracy<=100:return None
        return dict(p)
    except (KeyError,ValueError,TypeError):return None


def coordinate(value,latitude):
    # Round total minutes before splitting, including carry at degree boundaries.
    hundredths=round(abs(value)*60*100);degrees,minutes=divmod(hundredths,6000)
    if latitude:return '%02d%05.2f%s'%(degrees,minutes/100,'N' if value>=0 else 'S')
    return '%03d%05.2f%s'%(degrees,minutes/100,'E' if value>=0 else 'W')


def beacon_payload(position,tag,number):
    return ('!'+coordinate(position['lat'],True)+'/'+coordinate(position['lon'],False)+'[Walk '+tag+' %03d'%number).encode('ascii')


def ax_address(call,last=False,command=False):
    parts=call.upper().split('-');name=parts[0];ssid=int(parts[1]) if len(parts)==2 else 0
    if len(parts)>2 or not 1<=len(name)<=6 or not name.isascii() or not name.isalnum() or not 0<=ssid<=15:raise ValueError('Invalid callsign')
    return bytes(ord(c)<<1 for c in name.ljust(6))+bytes([0x60|(ssid<<1)|int(last)|(0x80 if command else 0)])


def beacon_frame(call,position,tag,number):
    calls=['APN810',call,'WIDE1-1','WIDE2-1']
    return b'\0'+b''.join(ax_address(c,i==len(calls)-1,i==0) for i,c in enumerate(calls))+b'\x03\xf0'+beacon_payload(position,tag,number)


def unpack(frame):
    if not frame or frame[0]!=0:return None
    addresses=[];i=1
    while i+7<=len(frame) and len(addresses)<10:
        raw=frame[i:i+7];addresses.append((monitor.address(raw),bool(raw[6]&128)));i+=7
        if raw[6]&1:break
    else:return None
    if len(addresses)<2 or frame[i:i+2]!=b'\x03\xf0':return None
    return addresses,frame[i+2:]


class Walk:
    def __init__(self,args):
        self.call=args.callsign.upper();ax_address(self.call)
        self.plan=Plan(args.budget);self.log=Journal(Path(args.logs).expanduser())
        self.tag=datetime.datetime.now().strftime('%H%M%S')
        self.rx=None;self.tx=None;self.release_at=None;self.frames=bridge.Frames();self.retry=0;self.lease=0;self.state_due=0
        self.state={};self.position=None;self.track=collections.deque(maxlen=7200);self.received=0
        self.recent=collections.deque(maxlen=100);self.last_fix=None;self.prompt=None;self.notice='Recording walk'
        self.atlas=None;self.base_key=None;self.map_base=({},[]);self.center=None;self.span=2;self.map_full=True;self.terrain=True;self.roads=True
        try:self.atlas=walk_map.Atlas(str(BASE/'maps'))
        except (OSError,ValueError):pass
        self.log.add('session',callsign=self.call,tag=self.tag,budget=args.budget,automatic_seconds=60,path=['WIDE1-1','WIDE2-1'])
        self.log.flush()
        self.archives=history.load(self.log.path.parent,self.call,self.log.path)
        self.archive_index=0;self.view_history=bool(self.archives);self.fit_requested=self.view_history
        self.map_layer=None;self.layer_key=None;self.paint_key=None;self.layout=None
        if self.view_history:self.notice='Saved walk loaded'
    def view_track(self):
        return self.archives[self.archive_index]['track'] if self.view_history else self.track
    def view_probes(self):
        return self.archives[self.archive_index]['probes'] if self.view_history else self.plan.probes
    def close_tx(self):
        if self.tx:self.tx.close();self.tx=None
        self.release_at=None
    def disarm(self,reason):
        was=self.plan.armed;self.plan.disarm(reason);self.close_tx();self.notice=reason
        if was:self.log.add('disarmed',reason=reason)
    def disconnect(self):
        if self.rx:self.rx.close();self.rx=None
        self.frames=bridge.Frames();self.disarm('Radio disconnected; explicitly re-arm after recovery')
    def healthy(self):
        status=self.state.get('status',{})
        safe_channel=(status.get('curr_channel_id_upper')==0 and not status.get('is_scan',True) and 0<=time.time()-self.state.get('fields',{}).get('status',0)<=20)
        return self.rx is not None and self.position is not None and safe_channel
    def tick(self):
        now=time.monotonic();wall=time.time()
        if now>=self.lease:
            live.atomic(live.GPS_CONTROL,{'until':wall+45});self.lease=now+10
        if now>=self.state_due:self.state=live.read();self.state_due=now+1
        self.position=fresh_position(self.state,wall)
        if self.position and self.position['time']!=self.last_fix:
            self.last_fix=self.position['time'];self.track.append(self.position);self.log.add('position',position=self.position)
            if self.center is None:self.center=(self.position['lat'],self.position['lon'])
        if self.rx is None and now>=self.retry:
            self.retry=now+3
            rx=socket.socket(socket.AF_UNIX);rx.settimeout(.2)
            try:rx.connect('/dev/shm/n810-kiss-rx.sock');rx.setblocking(False);self.rx=rx;self.log.add('radio_connected')
            except OSError:rx.close()
        if self.rx:
            try:
                for _ in range(16):
                    try:data=self.rx.recv(8192)
                    except BlockingIOError:break
                    if not data:self.disconnect();break
                    for frame in self.frames.feed(data):self.receive(frame)
            except (OSError,ValueError):self.disconnect()
        if self.tx and self.release_at is not None and now>=self.release_at:self.close_tx()
        if self.tx:
            try:
                # Drain replies; only monitor socket provides the recorded RX stream.
                for _ in range(16):
                    try:data=self.tx.recv(8192)
                    except BlockingIOError:break
                    if not data:raise ConnectionError('TX owner disconnected')
            except OSError:self.disarm('Transmit socket lost; explicitly re-arm')
        armed=self.plan.armed
        due=self.plan.tick(now,self.healthy())
        if armed and not self.plan.armed:self.close_tx();self.notice=self.plan.reason;self.log.add('disarmed',reason=self.notice)
        if due:self.send()
        if now>=self.log.due:self.log.flush()
    def receive(self,frame):
        self.received+=1;text=monitor.describe(frame) or 'KISS control frame'
        self.recent.append(time.strftime('%H:%M:%S')+' '+text)
        self.log.add('rx',frame=frame.hex(),position=self.position,decoded=text)
        info=unpack(frame)
        if info:
            addresses,payload=info
            if addresses[1][0]==self.call and addresses[0][0]=='APN810' and any(used for call,used in addresses[2:]):
                route=','.join(call+('*' if used else '') for call,used in addresses[2:])
                row=self.plan.returned(payload,route)
                if row:self.log.add('repeated_copy',number=row['number'],path=route,position=self.position);self.notice='Repeated copy observed for probe %03d'%row['number']
    def arm(self):
        if not self.healthy():self.notice='Cannot arm: APRS memory 0, connected radio and fresh GPS required';return
        tx=socket.socket(socket.AF_UNIX);tx.settimeout(.3)
        try:
            tx.connect('/dev/shm/n810-kiss.sock')
            if select.select([tx],[],[],.15)[0] and tx.recv(1,socket.MSG_PEEK)==b'':raise ConnectionError('Another tool owns transmit; disarm it first')
            self.plan.arm(time.monotonic(),True);tx.setblocking(False);self.tx=tx
            self.notice=self.plan.reason;self.log.add('armed',position=self.position);self.log.flush()
        except (OSError,ValueError) as exc:tx.close();self.notice=str(exc)
    def send(self):
        # Refresh just before every submission. No scheduled frame survives a lost fix/link.
        self.state=live.read();self.position=fresh_position(self.state,time.time())
        if not self.plan.armed or not self.healthy() or not self.tx:
            self.disarm('Send blocked: arm and fresh GPS/radio required');return
        if self.plan.pending:self.notice='One probe is still outstanding; wait up to 30 seconds';return
        frame=beacon_frame(self.call,self.position,self.tag,self.plan.count+1)
        try:
            self.tx.settimeout(.3);self.tx.sendall(bridge.encode(frame));self.tx.setblocking(False)
        except OSError as exc:self.log.add('submission_uncertain',frame=frame.hex(),error=str(exc));self.disarm('Write failed; no retry, submission uncertain');return
        row=self.plan.submitted(time.monotonic(),self.position,beacon_payload(self.position,self.tag,self.plan.count+1))
        self.log.add('submission',frame=frame.hex(),probe=dict(row));self.notice='Probe %03d submitted (not proof of RF)'%row['number']
        if not self.plan.armed:self.release_at=time.monotonic()+3
    def key(self,key):
        if self.prompt is not None:
            if key in (27,):self.prompt=None;return
            if key in (10,13):
                text=self.prompt;self.prompt=None
                if text=='ARM':self.arm()
                else:self.notice='Not armed; confirmation must be ARM'
            elif key in (curses.KEY_BACKSPACE,127,8):self.prompt=self.prompt[:-1]
            elif 32<=key<=126 and len(self.prompt)<12:self.prompt+=chr(key)
            return
        if key==ord('q'):return 'quit'
        if key in (ord('p'),ord(' ')):self.disarm('Paused by operator')
        elif key==ord('a'):
            if self.view_history:
                self.view_history=False;self.center=(self.position['lat'],self.position['lon']) if self.position else None;self.span=2
            if self.plan.armed:self.notice='Already armed; p pauses'
            else:self.prompt=''
        elif key==ord('s'):self.send()
        elif key==ord('w'):self.log.flush();self.notice='Walk saved'
        elif key==ord('h'):
            self.disarm('History/live view changed')
            self.view_history=not self.view_history if self.archives else False
            self.fit_requested=True
        elif key in (ord('j'),ord('k')) and self.view_history:
            self.archive_index=(self.archive_index+(1 if key==ord('j') else -1))%len(self.archives);self.fit_requested=True
        elif key==ord('m'):self.map_full=not self.map_full
        elif key==ord('t'):self.terrain=not self.terrain
        elif key==ord('r'):self.roads=not self.roads
        elif key==ord('f'):self.fit_requested=True
        elif key==ord('c'):
            p=self.view_track()[-1] if self.view_history and self.view_track() else self.position
            if p:self.center=(p['lat'],p['lon'])
        elif key in (curses.KEY_UP,curses.KEY_DOWN,curses.KEY_LEFT,curses.KEY_RIGHT) and self.center:
            lat,lon=self.center;distance=self.span*.2
            if key in (curses.KEY_LEFT,curses.KEY_RIGHT):lon+=distance/(111.32*math.cos(math.radians(lat)))*(1 if key==curses.KEY_RIGHT else -1)
            else:lat+=distance/111.32*(1 if key==curses.KEY_UP else -1)
            self.center=(round(max(-80,min(80,lat)),6),round((lon+180)%360-180,6))
        elif key in (ord('+'),ord('=')):self.span=max(.5,self.span/2)
        elif key==ord('-'):self.span=min(48000,self.span*2)
    def signature(self,size):
        p=self.position or {}
        return (self.received,self.notice,self.prompt,self.plan.armed,self.plan.count,
                int(self.plan.due-time.monotonic()) if self.plan.armed else None,
                bool(self.rx),p.get('accuracy'),p.get('lat'),p.get('lon'),
                self.view_history,self.archive_index,self.map_full,self.terrain,self.roads,
                self.center,self.span,len(self.track) if not self.view_history else 0,
                self.fit_requested,size)

    def draw(self,win,preview=False):
        h,w=win.getmaxyx();split=1 if self.map_full else max(18,w//2)
        top=4;mh=max(1,h-top-2);mw=max(1,w-split-2);self.map_size=(mw,mh)
        layout=(h,w,split)
        changed=layout!=self.layout
        if changed:
            win.clear() if rgb_map.enabled() else win.erase();self.layout=layout;self.paint_key=None
        def put(y,x,text,attr=0,width=None):
            if 0<=y<h and 0<=x<w-1:
                try:win.addnstr(y,x,terminal.printable(text),max(0,min(w-x-1,width if width is not None else w)),attr)
                except curses.error:pass
        def line(y,text,attr=0):
            if 0<=y<h:
                win.move(y,0);win.clrtoeol();put(y,0,text,attr)
        rgb_update=None
        use_rgb=rgb_map.enabled()
        track=self.view_track();probes=self.view_probes()
        if self.fit_requested and track:
            low=min(p['lat'] for p in track);high=max(p['lat'] for p in track)
            west=min(p['lon'] for p in track);east=max(p['lon'] for p in track)
            self.center=((low+high)/2,(west+east)/2)
            self.span=min(48000,max(.5,(east-west)*111.32*math.cos(math.radians(self.center[0]))*1.2,(high-low)*111.32*mw/max(1,mh)/2*1.2))
            self.fit_requested=False
        mode=('SAVED '+self.archives[self.archive_index]['start'][:16].replace('T',' ')) if self.view_history else 'LIVE'
        gps=('GPS +/- %s m'%self.position.get('accuracy')) if self.position else 'GPS waiting'
        safety='TX ARMED' if self.plan.armed else 'TX DISARMED'
        line(0,'WALK '+self.call+' | '+mode+' | '+safety+' | '+('Radio up' if self.rx else 'Radio reconnecting')+' | '+gps+' | RX '+str(self.received),ink(3 if self.plan.armed else 4)|curses.A_BOLD)
        reports=sum(bool(p.get('internet_reports')) for p in probes)
        span='%.2f'%self.span if self.span<10 else '%.0f'%self.span
        line(1,'%s km%s | t terrain %s | r roads %s | %d fixes / %d probes / %d Internet'%(span,' target' if preview else '', 'ON' if self.terrain else 'OFF','ON' if self.roads else 'OFF',len(track),len(probes),reports))
        line(2,'Arrows pan  +/- zoom  f fit  c center  h history/live  j/k walk  m panels')
        if self.prompt is not None:
            line(3,'Type ARM + Enter to allow RF beacons (Esc cancels): '+self.prompt,curses.A_REVERSE)
        else:
            timing=('next %ds'%max(0,int(self.plan.due-time.monotonic()))) if self.plan.armed else 'auto >=60s'
            line(3,'a arm  p/Space pause  s probe  w save  q quit | %s | %d/%d sent | no retries'%(timing,self.plan.count,self.plan.budget))
        line(h-2,('@ live E end · trail  o sent  + return  i Internet' if use_rgb else '@ live E end  · track  O submitted R RF return I Internet')+' | Map (c) OpenStreetMap contributors')
        if preview:
            message='Drawing target view; previous map remains visible'
        elif self.prompt is not None:
            message='Beacon: '+(beacon_payload(self.position,self.tag,self.plan.count+1).decode() if self.position else '<fresh GPS required>')+' | WIDE1-1,WIDE2-1'
        else:message=self.notice
        line(h-1,message)
        if preview:
            win.refresh();return
        if not self.map_full:
            for y in range(top,h-2):
                win.move(y,0);win.clrtoeol()
            put(top,0,'PROBES',curses.A_BOLD,width=split-2)
            rows=probes[-max(1,mh//2):]
            for i,row in enumerate(rows):put(top+1+i,0,'%03d %s %s'%(row['number'],time.strftime('%H:%M:%S',time.localtime(row['time'])),row['status']),width=split-2)
            start=top+2+len(rows);put(start,0,'RECENT PACKETS')
            for i,text in enumerate(list(self.recent)[-max(1,h-start-3):]):put(start+1+i,0,text,width=split-2)
        if self.center:
            key=(self.center,self.span,mw,mh,self.roads)
            if self.atlas and self.base_key!=key:
                self.map_base=([],[]) if use_rgb else self.atlas.background(self.center,self.span,mw,mh,self.roads);self.base_key=key
            layer_key=(key,self.terrain)
            if self.layer_key!=layer_key:
                if not use_rgb:self.map_layer=map_layer(self.map_base[0],mw,mh,self.terrain)
                self.layer_key=layer_key
            track_key=(len(track),tuple((track[-1].get(k) for k in ('lat','lon','time'))) if track else None)
            probe_key=tuple((p['number'],p.get('return_path'),bool(p.get('internet_reports'))) for p in probes)
            paint_key=(layer_key,self.view_history,self.archive_index,track_key,probe_key,
                       None if self.view_history or not self.position else (self.position['lat'],self.position['lon']))
            if self.paint_key!=paint_key or not self.map_full:
                if not use_rgb:self.map_layer.overwrite(win,0,0,top,split,top+mh-1,split+mw-1)
                rgb_marks={}
                def point(p,char,attr):
                    if self.atlas:
                        x,y=self.atlas.project(p['lon'],p['lat'],self.center,self.span,mw,mh);x,y=round(x),round(y)
                    else:
                        x=round((mw-1)/2+(p['lon']-self.center[1])*75*(mw-1)/self.span)
                        y=round((mh-1)/2-(p['lat']-self.center[0])*111*(mw-1)/self.span/2)
                    if 0<=x<mw and 0<=y<mh:
                        rgb_marks[x,y]=({'O':'o','R':'+','I':'i'}.get(char,char),(121,230,158) if char=='R' else (153,224,244) if char=='I' else (246,243,222))
                        try:
                            if not use_rgb:win.addnstr(top+y,split+x,char,1,attr|curses.A_BOLD)
                        except curses.error:pass
                if use_rgb:
                    rgb_marks.update(rgb_map.trail(track,lambda p:self.atlas.project(p['lon'],p['lat'],self.center,self.span,mw,mh),mw,mh,walk_map.clip))
                else:
                    for p in track:point(p,'·',ink(72))
                for row in sorted(probes,key=lambda row:bool(row.get('return_path') or row.get('internet_reports'))):
                    marker='R' if row.get('return_path') else 'I' if row.get('internet_reports') else 'O'
                    point(row['position'],marker,ink(73) if marker in ('R','I') else ink(7))
                if self.view_history and track:point(track[-1],'E',ink(7))
                elif self.position:point(self.position,'@',ink(7)|curses.A_REVERSE)
                if use_rgb:
                    if not hasattr(self,'rgb_surface'):self.rgb_surface=rgb_map.Surface()
                    frame,self.rgb_description=rgb_map.background(self.atlas,self.center,self.span,mw,mh,self.roads,self.terrain)
                    rgb_update=(frame,rgb_marks,split,top,mw,mh)
                self.paint_key=paint_key
        else:put(top,split,'Waiting for a fresh radio GPS fix')
        description=getattr(self.atlas,'description',None)
        if self.prompt is None and callable(description):line(h-1,self.notice+' | '+(getattr(self,'rgb_description',None) if rgb_map.enabled() and getattr(self,'rgb_description',None) else description()))
        win.refresh()
        if rgb_update:self.rgb_surface.draw(*rgb_update,force=True)
    def close(self):
        self.disarm('Session ended')
        if self.rx:self.rx.close()
        live.atomic(live.GPS_CONTROL,{'until':0})
        self.log.add('session_end',probes=self.plan.count,received=self.received);self.log.close()


NAVIGATION={ord('+'),ord('='),ord('-'),curses.KEY_UP,curses.KEY_DOWN,curses.KEY_LEFT,curses.KEY_RIGHT}


def navigation_batch(win,walk,first,clock=time.monotonic):
    """Apply a bounded navigation burst; return the first FIFO command barrier."""
    deadline=clock()+.1;key=first;count=0
    try:
        while True:
            walk.key(key);count+=1
            if count>=64:return None
            win.timeout(0);key=win.getch()
            if key==-1:
                remaining=deadline-clock()
                if remaining<=0:return None
                win.timeout(max(1,math.ceil(remaining*1000)));key=win.getch()
                if key==-1:return None
            if key not in NAVIGATION:return key
    finally:win.timeout(250)


def map_layer(cells,width,height,terrain):
    """Cache generated map glyphs as styled row runs in a small curses pad."""
    layer=curses.newpad(height,width);layer.bkgd(' ',ink(1));layer.erase()
    if hasattr(cells,'items'):
        attrs={kind:map_attr(kind,terrain) for kind in {kind for char,kind in cells.values()}}
        rows=collections.defaultdict(list)
        for (x,y),(char,kind) in cells.items():
            if 0<=x<width and 0<=y<height:rows[y].append((x,char,attrs[kind]))
        runs=[]
        for y,values in rows.items():
            for x,char,attribute in sorted(values):runs.append((y,x,x+1,char,attribute))
    else:
        attrs={kind:map_attr(kind,terrain) for kind in {r[4] for r in cells}}
        runs=[(y,left,right,char,attrs[kind]) for y,left,right,char,kind in cells]
    pending=None;text=''
    def flush():
        if pending is not None:
            y,start,end,attribute=pending
            try:layer.addstr(y,start,text,attribute)
            except curses.error:pass
    for y,left,right,char,attribute in runs:
        if pending is None or pending[0]!=y or pending[2]!=left or pending[3]!=attribute:
            flush();pending=(y,left,right,attribute);text=''
        else:pending=(y,pending[1],right,attribute)
        text+=char*(right-left)
    flush()
    return layer


def run(win,walk):
    try:curses.curs_set(0)
    except curses.error:pass
    init_map_colors(win)
    win.timeout(0);last=None
    while True:
        walk.tick()
        key=win.getch();navigated=False
        if key in NAVIGATION and walk.prompt is None:
            barrier=navigation_batch(win,walk,key);navigated=True
            if barrier is not None and walk.key(barrier)=='quit':break
        elif walk.key(key)=='quit':break
        visible=visibility.visible()
        signature=walk.signature(win.getmaxyx())
        if not visible:last=None
        elif signature!=last:
            if navigated:walk.draw(win,preview=True)
            walk.draw(win);last=walk.signature(win.getmaxyx())
        win.timeout(250)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--callsign',default='N0CALL');parser.add_argument('--budget',type=int,default=20)
    parser.add_argument('--logs',default='~/.local/state/n810-aprs/walks')
    args=parser.parse_args()
    if not 1<=args.budget<=60:parser.error('budget must be 1..60')
    # A second walk must not renew GPS leases or own a competing timer.
    import fcntl
    lock=open('/dev/shm/n810-aprs-walk.lock','a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:parser.exit(1,'Walk Test already running; use its tmux window.\n')
    def stop(*_):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGHUP,stop)
    visibility.setup()
    walk=Walk(args)
    try:curses.wrapper(run,walk)
    except KeyboardInterrupt:pass
    finally:walk.close()
    print('Walk saved:',walk.log.path)

if __name__=='__main__':main()
