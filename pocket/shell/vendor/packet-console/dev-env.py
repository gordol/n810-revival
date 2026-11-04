#!/usr/bin/env python3
"""Run legacy radio TUIs locally against private captured data and RX-only sockets."""
import argparse
import collections
import datetime
import importlib.util
import json
import math
import os
from pathlib import Path
import selectors
import signal
import socket
import stat
import sqlite3
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
DEFAULT=Path('/tmp')/('n810-dev-'+str(os.getuid()))
LIMIT=256*1024

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

def read_capture(path):
    if path.stat().st_size>8_000_000:raise ValueError('capture exceeds 8 MB')
    data=json.loads(path.read_text());return data.get('data',data)

def prepare(root,live,catalog):
    root.mkdir(mode=0o700,parents=True,exist_ok=True)
    if root.stat().st_uid!=os.getuid() or root.stat().st_mode&0o077:raise ValueError('sandbox must be private and owned by this user')
    state=root/'home/.local/state/n810-aprs';state.mkdir(mode=0o700,parents=True,exist_ok=True)
    data=read_capture(live);cat=read_capture(catalog)
    frames=module('dev_frames','n810-frame-history.py');monitor=module('dev_monitor','n810-packet-monitor.py')
    history=frames.History()
    for row in data.get('packets',[])[-200:]:history.add(row)
    history.save(state/'raw-frames.json')
    directory=module('dev_directory','n810-aprs-directory.py');db=directory.database(state/'directory.sqlite3')
    if not db.execute('SELECT count(*) FROM stations').fetchone()[0]:
        for r in cat.get('stations',[])[:500]:
            db.execute('INSERT OR IGNORE INTO stations VALUES(?,?,?,?)',tuple(r.get(k) for k in ('call','first','last','packets')))
            if r.get('name') or r.get('buddy') or r.get('notes'):
                db.execute('INSERT OR IGNORE INTO people VALUES(?,?,?,?)',(r['call'],int(bool(r.get('buddy'))),r.get('name') or '',r.get('notes') or ''))
        for r in cat.get('evidence',[])[:2000]:db.execute('INSERT OR IGNORE INTO evidence VALUES(?,?,?,?)',tuple(r.get(k) for k in ('call','kind','stamp','detail')))
        for r in cat.get('via',[])[:1000]:db.execute('INSERT OR IGNORE INTO via VALUES(?,?,?,?,?)',tuple(r.get(k) for k in ('call','relay','first','last','packets')))
        db.commit()
    stations=db.execute('SELECT count(*) FROM stations').fetchone()[0];db.close()
    meta=dict(version=1,mode='REPLAY',hardware='unavailable',transmit=False,original_capture_times=True,fixture_captured=data.get('captured'),catalog_captured=cat.get('captured'),records=len(history.records),stations=stations,decoded_socket=str(root/'aprs.sock'),snapshot_socket=str(root/'replay.sock'),home=str(root/'home'))
    (root/'environment.json').write_text(json.dumps(meta,indent=2)+'\n');os.chmod(root/'environment.json',0o600)
    (root/'catalog.json').write_text(json.dumps(cat));os.chmod(root/'catalog.json',0o600)
    return history,history.decoded(monitor.describe),meta

def active(path):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        try:s.connect(str(path));return True
        except (ConnectionRefusedError,FileNotFoundError):return False

def serve(args):
    root=args.root
    for p in (root/'aprs.sock',root/'replay.sock'):
        if active(p):raise ValueError('A development feed already owns '+str(p))
    history,decoded,meta=prepare(root,args.live,args.catalog)
    sel=selectors.DefaultSelector();listeners=[];clients={};stopped=False
    status=('REPLAY | original capture timestamps | hardware unavailable | TX disabled | '+str(len(history.records))+' retained records\n').encode()
    def stop(*_):
        nonlocal stopped
        stopped=True
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
    def drop(c):sel.unregister(c);clients.pop(c,None);c.close()
    def queue(c,b):
        clients[c].extend(b)
        if len(clients[c])>LIMIT:drop(c)
        else:sel.modify(c,selectors.EVENT_READ|selectors.EVENT_WRITE,sel.get_key(c).data)
    try:
        for name in ('aprs.sock','replay.sock'):
            path=root/name
            if path.exists():
                if not stat.S_ISSOCK(path.lstat().st_mode):raise ValueError("Refusing to remove non-socket "+str(path))
                path.unlink()
            s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);s.bind(str(path));os.chmod(path,0o600);s.listen(8);s.setblocking(False);sel.register(s,selectors.EVENT_READ,name);listeners.append((s,path))
        header,_,records=history.export().partition(b'\n');header=json.loads(header);header.update(replay=True,fixture_captured=meta['fixture_captured']);snapshot=json.dumps(header).encode()+b'\n'+records
        replay=iter(decoded);next_packet=time.monotonic()+args.interval if args.interval else float('inf');heartbeat=time.monotonic()+10
        print(json.dumps(meta),flush=True)
        while not stopped:
            now=time.monotonic();timeout=max(0,min(1,next_packet-now,heartbeat-now))
            for key,events in sel.select(timeout):
                if key.fileobj in [x[0] for x in listeners]:
                    c,_=key.fileobj.accept();c.setblocking(False);clients[c]=bytearray();sel.register(c,selectors.EVENT_READ)
                    queue(c,snapshot if key.data=='replay.sock' else b''.join(decoded)+status)
                    # Frozen snapshot closes after its buffered export; decoded subscriptions stay open.
                    if c in clients:sel.modify(c,selectors.EVENT_READ|selectors.EVENT_WRITE,key.data)
                    continue
                c=key.fileobj
                if c not in clients:continue
                try:
                    if events&selectors.EVENT_READ:
                        # No commands, KISS transmitter or hardware writes exist on this service.
                        if not c.recv(4096):drop(c);continue
                        drop(c);continue
                    if events&selectors.EVENT_WRITE:
                        n=c.send(clients[c]);del clients[c][:n]
                        if not clients[c]:
                            if key.data=='replay.sock':drop(c)
                            else:sel.modify(c,selectors.EVENT_READ,'aprs.sock')
                except (OSError,ConnectionError):
                    if c in clients:drop(c)
            now=time.monotonic()
            publish=[]
            if now>=next_packet:
                line=next(replay,None)
                if line is None:next_packet=float('inf');publish.append(b'REPLAY | end of recorded sequence | no live radio\n')
                else:publish.append(line);next_packet=now+args.interval
            if now>=heartbeat:publish.append(status);heartbeat=now+10
            for c in list(clients):
                if sel.get_key(c).data=='aprs.sock':
                    for b in publish:
                        if c in clients:queue(c,b)
    finally:
        for c in list(clients):drop(c)
        for s,path in listeners:sel.unregister(s);s.close();path.unlink(missing_ok=True)
        sel.close()

def launch(args):
    root=args.root
    if not (root/'environment.json').exists():raise ValueError('Start dev-env.py serve first')
    home=root/'home';env=dict(os.environ,HOME=str(home));env['N810_DEV_MODE']='REPLAY'
    commands={
        'aprs':['n810-aprs-view.py','--map-engine','next','--tui-theme','color','--maps',str(HERE/'maps'),'--socket',str(root/'aprs.sock')],
        'directory':['n810-aprs-directory.py','--db',str(home/'.local/state/n810-aprs/directory.sqlite3')],
        'services':['n810-aprs-services.py','--socket',str(root/'aprs.sock'),'--call','N0CALL'],
        'nets':['n810-nets.py','--socket',str(root/'aprs.sock'),'--lead','0'],
    }
    command=commands[args.app];return subprocess.call([sys.executable,str(HERE/command[0]),*command[1:]],env=env,cwd=HERE)

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    s=sub.add_parser('serve',help='RX-only captured feed and sandboxed state; no Bluetooth or network access')
    s.add_argument('--root',type=Path,default=DEFAULT);s.add_argument('--live',type=Path,default=HERE/'phone-terminal/.private/native-live.json');s.add_argument('--catalog',type=Path,default=HERE/'phone-terminal/.private/native-catalog.json');s.add_argument('--interval',type=float,default=0,help='Optional seconds between re-emitted original records, once; 0 leaves a static snapshot')
    r=sub.add_parser('run',help='Open an unchanged legacy TUI with sandbox HOME and explicit local sockets');r.add_argument('app',choices=('aprs','directory','services','nets'));r.add_argument('--root',type=Path,default=DEFAULT)
    args=p.parse_args();args.root=args.root.expanduser().resolve()
    if len(str(args.root/'replay.sock').encode())>=100:p.error('Use a short /tmp sandbox path for Unix sockets')
    if not math.isfinite(getattr(args,'interval',0)) or getattr(args,'interval',0)<0:p.error('interval must be finite and nonnegative')
    try:return serve(args) if args.action=='serve' else launch(args)
    except (OSError,ValueError,KeyError) as error:print('Development environment: '+str(error),file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
