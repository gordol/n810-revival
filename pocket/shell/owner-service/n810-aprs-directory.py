#!/usr/bin/env python3
"""Optional offline heard directory. Collector reads frozen raw history only."""
import argparse
import curses
import hashlib
import importlib.util
import json
import os
import re
import textwrap
import datetime
from pathlib import Path
import signal
import socket
import sqlite3
import time


_ui_spec=importlib.util.spec_from_file_location('ui_state',os.path.join(os.path.dirname(__file__),'n810-ui-state.py'))
ui_state=importlib.util.module_from_spec(_ui_spec);_ui_spec.loader.exec_module(ui_state)
_terminal_spec=importlib.util.spec_from_file_location('directory_terminal',Path(__file__).with_name('n810-terminal-text.py'))
terminal=importlib.util.module_from_spec(_terminal_spec);_terminal_spec.loader.exec_module(terminal)
_visibility_spec=importlib.util.spec_from_file_location('stations_visible',Path(__file__).with_name('n810-ui-visible.py'))
visibility=importlib.util.module_from_spec(_visibility_spec);_visibility_spec.loader.exec_module(visibility)

def database(path):
    path=Path(path).expanduser();path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=.2)
    os.chmod(path,0o600)
    db.executescript('''
    CREATE TABLE IF NOT EXISTS stations(call TEXT PRIMARY KEY, first TEXT, last TEXT, packets INTEGER DEFAULT 0);
    CREATE TABLE IF NOT EXISTS via(call TEXT, relay TEXT, first TEXT, last TEXT, packets INTEGER DEFAULT 0, PRIMARY KEY(call,relay));
    CREATE TABLE IF NOT EXISTS people(call TEXT PRIMARY KEY, buddy INTEGER DEFAULT 0, name TEXT DEFAULT '', notes TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS evidence(call TEXT,kind TEXT,stamp TEXT,detail TEXT,PRIMARY KEY(call,kind));
    CREATE TABLE IF NOT EXISTS legacy_records(id TEXT PRIMARY KEY,call TEXT,stamp TEXT);
    CREATE TABLE IF NOT EXISTS legacy_evidence(call TEXT,kind TEXT,stamp TEXT,detail TEXT,PRIMARY KEY(call,kind));
    CREATE TABLE IF NOT EXISTS seen(id TEXT PRIMARY KEY, stamp TEXT);
    ''');db.commit();return db


def snapshot(path):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(2);client.connect(path)
        with client.makefile('rb') as f:
            header=json.loads(f.readline(4096))
            if header.get('type')!='snapshot' or header.get('version')!=1:raise ValueError('Unsupported raw snapshot')
            return [json.loads(f.readline(150000)) for _ in range(min(200,int(header['records']))) ]


def load_monitor():
    spec=importlib.util.spec_from_file_location('monitor',Path(__file__).with_name('n810-packet-monitor.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


_decode_spec=importlib.util.spec_from_file_location('aprs_decode',Path(__file__).with_name('n810-aprs-decode.py'))
aprs_decode=importlib.util.module_from_spec(_decode_spec);_decode_spec.loader.exec_module(aprs_decode)

def evidence(payload,destination=''):
    return aprs_decode.decode(payload,destination)['evidence']


def record_evidence(db,source,payload,stamp,destination=''):
    for kind,detail in evidence(payload,destination):
        db.execute("""INSERT INTO evidence VALUES(?,?,?,?) ON CONFLICT(call,kind) DO UPDATE SET
                   stamp=excluded.stamp,detail=excluded.detail WHERE excluded.stamp>stamp""",(source,kind,stamp,detail))


def age(stamp):
    if stamp.startswith('legacy '):return 'older text'
    try:
        seconds=max(0,int((datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(stamp)).total_seconds()))
        return '%ds ago'%seconds if seconds<60 else '%dm ago'%(seconds//60) if seconds<3600 else '%dh ago'%(seconds//3600)
    except ValueError:return stamp


def ingest(db,records,monitor,own_call):
    count=0
    with db:
        for row in records:
            if row.get('direction')!='radio_to_host':continue
            frame=bytes.fromhex(row['frame']);text=monitor.describe(frame)
            if not text or '>' not in text:continue
            source,tail=text.split('>',1);route=tail.split(' ',1)[0].split(',')
            # Do not turn own-radio echoes into remote reception statistics.
            if source.split('-')[0]==own_call.split('-')[0]:continue
            stamp=row['time'];identity=hashlib.sha256((stamp+'|'+row['frame']).encode()).hexdigest()
            if not db.execute('INSERT OR IGNORE INTO seen VALUES(?,?)',(identity,stamp)).rowcount:
                if ' pid=f0 ' in text and (' ctl=03 ' in text or ' ctl=13 ' in text):
                    record_evidence(db,source,text.split(' pid=f0 ',1)[1],stamp,route[0])
                continue
            db.execute('''INSERT INTO stations VALUES(?,?,?,1) ON CONFLICT(call) DO UPDATE SET
                first=CASE WHEN first LIKE 'legacy %' THEN excluded.first ELSE min(first,excluded.first) END,last=CASE WHEN last LIKE 'legacy %' THEN excluded.last ELSE max(last,excluded.last) END,packets=packets+1''',(source,stamp,stamp))
            for relay in set(hop[:-1] for hop in route[1:] if hop.endswith('*')):
                db.execute('''INSERT INTO via VALUES(?,?,?,?,1) ON CONFLICT(call,relay) DO UPDATE SET
                    first=min(first,excluded.first),last=max(last,excluded.last),packets=packets+1''',(source,relay,stamp,stamp))
            if ' pid=f0 ' in text and (' ctl=03 ' in text or ' ctl=13 ' in text):
                payload=text.split(' pid=f0 ',1)[1]
                record_evidence(db,source,payload,stamp,route[0])
                # Inner APRS sender evidence is distinct from the outer RF route.
                for _ in range(3):
                    if not payload.startswith('}') or ':' not in payload:break
                    header,payload=payload[1:].split(':',1)
                    if '>' not in header:break
                    inner=header.split('>',1)[0]
                    record_evidence(db,inner,payload,stamp,header.split('>',1)[1].split(',')[0])
            count+=1
        # Capture IDs are tiny durable replay guards, not a retained packet archive.
        db.execute('DELETE FROM seen WHERE id NOT IN (SELECT id FROM seen ORDER BY stamp DESC LIMIT 2000)')
    return count


def import_history(db,path,own_call):
    """Import text without inventing dates or recovering missing H flags."""
    text=Path(path).expanduser().read_text()
    try:
        data=json.loads(text)
        rows=data['packets'] if isinstance(data,dict) and 'packets' in data else data
        if not isinstance(rows,list):raise ValueError('Expected packet list')
    except json.JSONDecodeError:
        rows=[json.loads(line) for line in text.splitlines() if line.strip()]
    added=0
    with db:
        for row in rows:
            line=row if isinstance(row,str) else row.get('raw','')
            match=re.match(r'^(\d\d:\d\d:\d\d) ([A-Z0-9-]+)>(\S+) ctl=(?:03|13) pid=f0 (.*)$',line)
            if not match:continue
            clock,source,route,payload=match.groups()
            if source.split('-')[0]==own_call.split('-')[0]:continue
            identity=hashlib.sha256(line.encode()).hexdigest()
            is_new=db.execute('INSERT OR IGNORE INTO legacy_records VALUES(?,?,?)',(identity,source,clock)).rowcount
            # Prefer dated raw evidence. Imported text has a clock but unknown date.
            stamp='legacy '+clock
            db.execute('INSERT OR IGNORE INTO stations VALUES(?,?,?,0)',(source,stamp,stamp))
            for kind,detail in evidence(payload,route.split(',')[0]):
                db.execute('INSERT OR REPLACE INTO legacy_evidence VALUES(?,?,?,?)',(source,kind,stamp,detail))
            added+=int(bool(is_new))
    return added


def station_evidence(db,call):
    legacy={k:(k,t,d) for k,t,d in db.execute('SELECT kind,stamp,detail FROM legacy_evidence WHERE call=?',(call,))}
    for k,t,d in db.execute('SELECT kind,stamp,detail FROM evidence WHERE call=?',(call,)):legacy[k]=(k,t,d)
    imported=db.execute('SELECT count(*) FROM legacy_records WHERE call=?',(call,)).fetchone()[0]
    if imported:legacy['legacy']=('legacy','legacy unknown date','%d older text records'%imported)
    observed=db.execute('SELECT count(DISTINCT call) FROM via WHERE relay=?',(call,)).fetchone()[0]
    if observed:legacy['relay_activity']=('relay_activity','',str(observed))
    forwarded=list(db.execute('SELECT call,packets FROM via WHERE relay=? ORDER BY packets DESC LIMIT 20',(call,)))
    legacy['forwarded']=('forwarded','',json.dumps(forwarded))
    return sorted(legacy.values())


def collect(args):
    from packet_events import PacketEvents
    db=database(args.db);monitor=load_monitor()
    def stop(*_):raise KeyboardInterrupt
    previous={sig:signal.signal(sig,stop) for sig in (signal.SIGTERM,signal.SIGINT)}
    def capture():
        try:
            added=ingest(db,snapshot(args.socket),monitor,args.call)
            print(time.strftime('%H:%M:%S'),'added',added,'observations',flush=True)
        except (OSError,ValueError,KeyError,sqlite3.Error) as exc:
            print('Snapshot unavailable; waiting for next receive event:',str(exc),flush=True)
    events=PacketEvents(args.feed_socket,capture,lambda text:print(text,flush=True))
    print('Independent heard collector: initial raw snapshot, then receive events; no Bluetooth or TX access.',flush=True)
    try:events.run()
    except KeyboardInterrupt:pass
    finally:
        events.close();db.close()
        for sig,handler in previous.items():signal.signal(sig,handler)


def station_details(call,name,buddy,last,count,ev,hops,notes,width,technical=False):
    """Build a cached plain-text detail page; no I/O on the paint path."""
    by_kind={kind:(stamp,detail) for kind,stamp,detail in ev}
    if not technical:
        lines=[call+('  *' if buddy else '')]
        if name:lines.append(name)
        if 'role' in by_kind:lines += [by_kind['role'][1]]
        lines+=['Heard '+age(last)+'   ·   %d captured'%count]
        if 'legacy' in by_kind:lines += [by_kind['legacy'][1]+' · dates unavailable']
        lines += ['']
        if 'phg' in by_kind:
            rf=json.loads(by_kind['phg'][1])
            lines+=['RADIO',
                    'Power      %d W'%rf['watts'],
                    'Antenna    %d dB · %s'%(rf['gain_db'],rf['direction']),
                    'Height     %s ft / %s m HAAT'%(format(rf['height_ft'],','),format(rf['height_m'],',')),
                    '           Advertised setup','']
        if 'position' in by_kind:
            stamp,detail=by_kind['position'];lat,lon=json.loads(detail)
            lines+=['Position   %.4f%s  %.4f%s'%(abs(lat),'N' if lat>=0 else 'S',abs(lon),'E' if lon>=0 else 'W'),
                    '           Last reported '+age(stamp),'']
        else:lines+=['Position   Unknown','']
        advertised=by_kind.get('messaging')
        capability='Unknown'
        if advertised:capability='Not advertised' if advertised[1].startswith('Messaging not') else 'Advertised'
        if 'mice' in by_kind:
            motion=json.loads(by_kind['mice'][1]);lines+=['Motion     %d kn / %03d deg'%(motion['speed_knots'],motion['course']),'Status     '+motion['status']]
            if motion.get('ambiguity'):lines+=['Position   Approximate / ambiguity %d'%motion['ambiguity']]
            lines+=['']
        lines+=['Messaging  '+capability]
        for kind,label in [('message','Message observed'),('ack','ACK observed')]:
            if kind in by_kind:lines+=['           '+label+' '+age(by_kind[kind][0])]
        if 'relay_activity' in by_kind:lines+=['Relaying   Observed for '+by_kind['relay_activity'][1]+' stations']
        lines+=['','HEARD THROUGH',(' · '.join(r for r,n,t in hops) if hops else 'No confirmed used relays in its path.')]
        forwarded=json.loads(by_kind.get('forwarded',('','[]'))[1])
        lines+=['','RELAYED FOR']
        lines += ['%-12s %d captured'%(c,n) for c,n in forwarded] or ['No relaying observed in retained captures.']
        services=[(k,t,d) for k,t,d in ev if k.startswith('service:') or k=='voice']
        if services:
            lines+=['','ADVERTISEMENTS']
            for kind,stamp,detail in services:
                lines+=textwrap.wrap(detail,max(20,width))+['']
        if notes:lines+=['','NOTES']+textwrap.wrap(notes,max(20,width))
        return lines
    lines=[call+('  * Buddy' if buddy else ''), name] if name else [call+('  * Buddy' if buddy else '')]
    lines+=['Last heard '+age(last)+'  /  %d captured packets'%count,'','']
    lines+=['MESSAGING']
    advertised=by_kind.get('messaging')
    if advertised:
        text=advertised[1]
        if text.startswith('Messaging not'):text='Not advertised; support unknown'
        elif text=='Messaging advertised':text='Advertised by station'
        lines += [text+'  /  '+age(advertised[0])]
    else:lines+=['Capability unknown']
    for kind,label in [('message','Message sent'),('ack','ACK sent')]:
        if kind in by_kind:lines += [label+' observed '+age(by_kind[kind][0])]
    if 'phg' in by_kind:
        stamp,detail=by_kind['phg'];rf=json.loads(detail)
        lines+=['','','RADIO / ADVERTISED',
                'Power       %d W'%rf['watts'],
                'Antenna     %d dB gain  /  %s'%(rf['gain_db'],rf['direction']),
                'Height      %s ft  /  %s m above average terrain'%(format(rf['height_ft'],','),format(rf['height_m'],',')),
                '            HAAT = height above average terrain, not tower height.']
        if technical:lines+=['Source      '+rf['code']+'  /  '+stamp]
    if 'position' in by_kind:
        stamp,detail=by_kind['position'];lat,lon=json.loads(detail)
        lines+=['','','POSITION / LAST KNOWN',
                '%.4f%s   %.4f%s'%(abs(lat),'N' if lat>=0 else 'S',abs(lon),'E' if lon>=0 else 'W'),
                'Reported '+age(stamp)+'  /  v to view on map']
    services=[(k,t,d) for k,t,d in ev if k.startswith('service:') or k=='voice']
    if services:
        lines+=['','','ADVERTISEMENTS / UNVERIFIED']
        for kind,stamp,detail in services:
            lines += [kind.replace('service:','').upper()+'  /  '+age(stamp)]
            lines += textwrap.wrap(detail,max(20,width)) + ['']
    lines+=['','','RECEIVED VIA']
    lines += ['%-12s %d packets  /  %s'%(r,n,age(t)) for r,n,t in hops] or ["No used relay recorded in this station's path."]
    if notes:lines+=['','','PERSONAL NOTES']+textwrap.wrap(notes,max(20,width))
    if technical:
        lines+=['','','EVIDENCE / CAPTURE TIMES (UTC)']
        for kind,stamp,detail in ev:lines+=[kind+'  '+stamp]+textwrap.wrap(detail,max(20,width))
    return lines


def display(win,args):
    db=database(args.db);curses.curs_set(0);win.keypad(True);win.timeout(200)
    selected=0;relay=None;updated=0;rows=[];status='';only_buddies=False;detail_key=None;details=[];detail_scroll=0;ev=[];technical=False;relays_only=False
    saved=ui_state.load('directory')
    relay=saved.get('relay');only_buddies=bool(saved.get('only_buddies',False));relays_only=bool(saved.get('relays_only',False))
    technical=bool(saved.get('technical',False));detail_scroll=max(0,int(saved.get('scroll',0)))
    restore_call=saved.get('call');request_id=saved.get('request_id');request_check=0
    def save_directory():
        ui_state.save('directory',dict(call=rows[selected][0] if rows else None,relay=relay,
            only_buddies=only_buddies,relays_only=relays_only,technical=technical,
            scroll=detail_scroll,request_id=request_id))
    def put(y,x,text,attr=0):
        h,w=win.getmaxyx()
        if 0<=y<h and x<w-1:
            try:win.addnstr(y,x,terminal.printable(text),w-x-1,attr)
            except curses.error:pass
    try:
        while True:
            if not visibility.visible():
                win.getch();continue
            if time.monotonic()>=request_check:
                request_check=time.monotonic()+.5
                try:
                    request=json.loads(Path('/dev/shm/n810-directory-request.json').read_text())
                    if request['id']!=request_id:
                        request_id=request['id'];restore_call=request['call']
                        relay=None;only_buddies=False;relays_only=False;updated=0
                except (OSError,ValueError,KeyError):pass
            if time.monotonic()-updated>3:
                sticky=restore_call or (rows[selected][0] if rows and selected<len(rows) else None)
                try:
                    if relay:
                        rows=db.execute('SELECT v.call,v.last,v.packets,coalesce(p.buddy,0),coalesce(p.name,\'\') FROM via v LEFT JOIN people p ON p.call=CASE WHEN instr(v.call,\'-\')>0 THEN substr(v.call,1,instr(v.call,\'-\')-1) ELSE v.call END WHERE relay=? ORDER BY v.last DESC',(relay,)).fetchall()
                    else:
                        rows=db.execute('SELECT s.call,s.last,s.packets,coalesce(p.buddy,0),coalesce(p.name,\'\') FROM stations s LEFT JOIN people p ON p.call=CASE WHEN instr(s.call,\'-\')>0 THEN substr(s.call,1,instr(s.call,\'-\')-1) ELSE s.call END ORDER BY (substr(s.last,1,6)=char(108,101,103,97,99,121)),s.last DESC').fetchall()
                    if relays_only:
                        relay_calls={r[0] for r in db.execute('SELECT DISTINCT relay FROM via UNION SELECT call FROM evidence WHERE kind=? UNION SELECT call FROM legacy_evidence WHERE kind=?',('role','role'))}
                        rows=[row for row in rows if row[0] in relay_calls]
                        present={row[0] for row in rows}
                        rows += [(call,last,0,0,'') for call,last in db.execute('SELECT relay,max(last) FROM via GROUP BY relay') if call not in present]
                    if only_buddies:rows=[r for r in rows if r[3]]
                    if sticky:
                        matches=[i for i,row in enumerate(rows) if row[0]==sticky]
                        if matches:selected=matches[0];restore_call=None
                    status=''
                except sqlite3.Error:status='Collector saving; retrying'
                updated=time.monotonic()
            selected=max(0,min(selected,len(rows)-1));win.erase();h,w=win.getmaxyx();split=max(27,min(40,w//3))
            put(0,2,'STATIONS',curses.A_BOLD)
            put(1,2,('Observed via '+relay if relay else 'Relays / advertised or observed' if relays_only else 'All heard stations')+(' / buddies' if only_buddies else ''))
            put(3,2,'STATION         SEEN',curses.A_BOLD)
            for y in range(3,h-3):put(y,split-2,'│')
            visible=max(1,h-7);start=max(0,selected-visible+1)
            for y,(i,row) in enumerate(list(enumerate(rows))[start:start+visible],4):
                call,last,count,buddy,name=row
                text=('%s %-11s %s'%('*' if buddy else ' ',call,age(last)))[:split-4]
                put(y,2,text,curses.A_REVERSE if i==selected else 0)
            if rows:
                call,last,count,buddy,name=rows[selected];base=call.split('-')[0]
                if detail_key != (call,updated):
                    detail_key=(call,updated)
                    ev=station_evidence(db,call)
                    hops=list(db.execute('SELECT relay,packets,last FROM via WHERE call=? ORDER BY packets DESC',(call,)))
                    notes=db.execute('SELECT notes FROM people WHERE call=?',(base,)).fetchone()
                    details=station_details(call,name,buddy,last,count,ev,hops,notes[0] if notes else '',w-split-3,technical)
                    if getattr(display,'last_call',None) not in (None,call):detail_scroll=0
                    display.last_call=call
                for y,line in enumerate(details[detail_scroll:],3):
                    if y>=h-4:break
                    put(y,split,line,curses.A_BOLD if line in ('HEARD THROUGH','RELAYED FOR','RADIO','ADVERTISEMENTS','MESSAGING','RADIO / ADVERTISED','POSITION / LAST KNOWN','RECEIVED VIA','PERSONAL NOTES','ADVERTISEMENTS / UNVERIFIED','EVIDENCE / CAPTURE TIMES (UTC)') or y==3 else 0)
            else:
                put(5,split,'No captured paths via '+relay if relay else 'No stations in this view.')
                if relay:put(7,split,'Older text paths are excluded: used-hop flags unknown.')
            put(h-3,2,status or ('Details %d-%d / %d  |  [ ] scroll'%(detail_scroll+1,min(len(details),detail_scroll+h-7),len(details)) if len(details)>h-7 else ''))
            put(h-2,1,'↑↓ select   v map   b buddy   R relays   r via   a all   d details   g nets   q close')

            win.refresh();key=win.getch()
            if key==ord('g'):
                spec=importlib.util.spec_from_file_location('ui_window',Path(__file__).with_name('n810-ui-window.py'))
                helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
                save_directory();helper.open_window('Nets');continue
            if key in (ord('q'),27):break
            if key in (curses.KEY_DOWN,ord('j')):selected=min(len(rows)-1,selected+1)
            elif key in (curses.KEY_UP,ord('k')):selected=max(0,selected-1)
            elif key==ord('d'):technical=not technical;detail_key=None
            elif key in (ord('['),ord(']')):detail_scroll=max(0,min(max(0,len(details)-5),detail_scroll+(4 if key==ord(']') else -4)))
            elif key==ord('m') and rows:
                request={'to':rows[selected][0],'created':time.time()}
                target=Path('/dev/shm/n810-message-request.json');temp=target.with_suffix('.tmp')
                temp.write_text(json.dumps(request));os.chmod(temp,0o600);temp.replace(target)
                spec=importlib.util.spec_from_file_location('ui_window',Path(__file__).with_name('n810-ui-window.py'))
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                save_directory();module.open_window('Messages')
            elif key==ord('v') and rows:
                request={'call':rows[selected][0],'id':time.time_ns()}
                for kind,stamp,detail in ev:
                    if kind=='position':request['position']=json.loads(detail);request['position_time']=stamp
                target=Path('/dev/shm/n810-map-request.json');temp=target.with_suffix('.tmp')
                temp.write_text(json.dumps(request));os.chmod(temp,0o600);temp.replace(target)
                spec=importlib.util.spec_from_file_location('ui_window',Path(__file__).with_name('n810-ui-window.py'))
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                save_directory();module.open_window('APRS')
            elif key==ord('b') and rows:
                base=rows[selected][0].split('-')[0]
                with db:db.execute('INSERT INTO people(call,buddy) VALUES(?,1) ON CONFLICT(call) DO UPDATE SET buddy=1-buddy',(base,))
                updated=0
            elif key==ord('B'):only_buddies=not only_buddies;updated=0
            elif key==ord('a'):relay=None;relays_only=False;updated=0
            elif key==ord('R'):relay=None;relays_only=not relays_only;updated=0
            elif key==ord('r') and rows:relay=rows[selected][0];relays_only=False;selected=0;updated=0
    finally:
        save_directory()
        db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db',default='~/.local/state/n810-aprs/directory.sqlite3')
    p.add_argument('--socket',default='/dev/shm/n810-aprs-replay.sock')
    p.add_argument('--feed-socket',default='/dev/shm/n810-aprs.sock')
    p.add_argument('--call',default='N0ANT');p.add_argument('--collect',action='store_true')
    p.add_argument('--json',action='store_true',help='Print station statistics as JSON lines, then exit')
    p.add_argument('--import-history',action='append',default=[],help='Conservatively import saved decoded JSON/JSONL, then exit')
    p.add_argument('--via',help='Filter JSON statistics by confirmed used relay')
    args=p.parse_args()
    if args.import_history:
        db=database(args.db)
        for path in args.import_history:print(path,import_history(db,path,args.call),'new legacy observations')
        db.close()
    elif args.collect:collect(args)
    elif args.json:
        db=sqlite3.connect('file:'+str(Path(args.db).expanduser())+'?mode=ro',uri=True,timeout=1)
        db.row_factory=sqlite3.Row
        query='SELECT call,first,last,packets FROM stations ORDER BY last DESC'
        params=()
        if args.via:
            query='SELECT call,first,last,packets FROM via WHERE relay=? ORDER BY last DESC';params=(args.via.upper(),)
        for row in db.execute(query,params):print(json.dumps(dict(row)))
        db.close()
    else:curses.wrapper(display,args)

if __name__=='__main__':main()
