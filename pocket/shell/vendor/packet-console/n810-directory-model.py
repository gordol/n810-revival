"""Shared Directory schema, evidence precedence and readable detail model."""
import datetime
import json
import os
import re
from pathlib import Path
import sqlite3
import textwrap


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



def age(stamp):
    if stamp.startswith('legacy '):return 'older text'
    try:
        seconds=max(0,int((datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(stamp)).total_seconds()))
        return '%ds ago'%seconds if seconds<60 else '%dm ago'%(seconds//60) if seconds<3600 else '%dh ago'%(seconds//3600)
    except ValueError:return stamp



def station_evidence(db,call):
    legacy={k:(k,t,d) for k,t,d in db.execute('SELECT kind,stamp,detail FROM legacy_evidence WHERE call=?',(call,))}
    for k,t,d in db.execute('SELECT kind,stamp,detail FROM evidence WHERE call=?',(call,)):legacy[k]=(k,t,d)
    imported=db.execute('SELECT count(*) FROM legacy_records WHERE call=?',(call,)).fetchone()[0]
    if imported:legacy['legacy']=('legacy','legacy unknown date','%d older text records'%imported)
    observed=db.execute('SELECT count(DISTINCT call) FROM via WHERE relay=?',(call,)).fetchone()[0]
    if observed:legacy['relay_activity']=('relay_activity','',str(observed))
    forwarded=[tuple(row) for row in db.execute('SELECT call,packets FROM via WHERE relay=? ORDER BY packets DESC LIMIT 20',(call,))]
    legacy['forwarded']=('forwarded','',json.dumps(forwarded))
    return sorted(legacy.values())



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


def person_call(call):
    if not isinstance(call,str):raise ValueError('Callsign required')
    call=call.strip().upper()
    if not re.fullmatch(r'[A-Z0-9]{1,12}(?:-(?:[0-9]|1[0-5]))?',call):raise ValueError('Invalid callsign')
    return call.split('-')[0]


def get_person(db,call):
    base=person_call(call)
    row=db.execute('SELECT buddy,name,notes FROM people WHERE call=?',(base,)).fetchone()
    buddy,name,notes=tuple(row) if row else (0,'','')
    return dict(call=base,buddy=bool(buddy),name=name,notes=notes)


def _personal_fields(values):
    if not isinstance(values,dict) or not values or set(values)-{'buddy','name','notes'}:raise ValueError('Expected buddy, name or notes fields')
    for key,value in values.items():
        if key=='buddy':
            if type(value)!=bool:raise ValueError('Buddy must be boolean')
        elif not isinstance(value,str) or len(value)>(120 if key=='name' else 4096) or '\0' in value:
            raise ValueError('Invalid '+key)


def edit_person(db,call,changes,expected=None):
    """Commit explicit field sets; expected values optionally detect stale edits."""
    return _change_person(db,call,changes,expected,False)


def toggle_buddy(db,call):
    """One local user action, serialized with other writers; not retry-idempotent."""
    return _change_person(db,call,{},None,True)


def _change_person(db,call,changes,expected,toggle):
    try:
        base=person_call(call)
        if not toggle:_personal_fields(changes)
        if expected is not None:
            _personal_fields(expected)
            if set(expected)!=set(changes):raise ValueError('Expected values must match edited fields')
    except ValueError as exc:return dict(status='invalid',person=None,error=str(exc))
    if db.in_transaction:return dict(status='error',person=None,error='Edit requires an idle connection')
    try:
        db.execute('BEGIN IMMEDIATE')
        current=get_person(db,base)
        desired={'buddy':not current['buddy']} if toggle else dict(changes)
        if all(current[key]==value for key,value in desired.items()):
            db.rollback();return dict(status='unchanged',person=current)
        if expected is not None and any(current[key]!=value for key,value in expected.items()):
            db.rollback();return dict(status='conflict',person=current)
        updated=dict(current,**desired)
        db.execute('INSERT INTO people(call,buddy,name,notes) VALUES(?,?,?,?) ON CONFLICT(call) DO UPDATE SET buddy=excluded.buddy,name=excluded.name,notes=excluded.notes',
                   (base,int(updated['buddy']),updated['name'],updated['notes']))
        db.commit();return dict(status='applied',person=updated)
    except sqlite3.Error as exc:
        db.rollback()
        code=getattr(exc,'sqlite_errorcode',0) or 0
        return dict(status='busy' if code&255 in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED) else 'error',person=None,error='Directory busy; retry after refresh' if code&255 in (sqlite3.SQLITE_BUSY,sqlite3.SQLITE_LOCKED) else 'Directory edit failed')


def symbol_value(table,code):
    """Preserve an explicit APRS table/overlay and printable symbol code."""
    if not isinstance(table,str) or len(table)!=1 or not (table in ('/','\\') or table.isascii() and table.isalnum()):return None
    if not isinstance(code,str) or len(code)!=1 or not 33<=ord(code)<=126:return None
    return dict(table=table,code=code)


SYMBOL_CLASSIFICATION_SOURCE='https://www.aprs.org/symbols/symbolsX.txt'
# APRS master list, 25 Nov 2015: JUST-MOBILE "IS NOW" and gateway/link entries.
MOBILE_PRIMARY=frozenset("!'<=>()*0123456789CFOPRSUXY[\\^abefgjkpsuv")
MOBILE_ALTERNATE=frozenset('>KOSY[^ksuv\\')


def classify_symbol(table,code):
    """Advertised symbol membership, not measured motion or link reachability."""
    known=symbol_value(table,code) is not None and (table in ('/','\\') or table.isascii() and ('A'<=table<='Z' or '0'<=table<='9'))
    mobile=gateway=None
    if known:
        primary=table=='/'
        mobile=code in (MOBILE_PRIMARY if primary else MOBILE_ALTERNATE)
        gateway=code=='&' or not primary and code=='0'
    return dict(table=table,code=code,advertised_mobile_symbol=mobile,
                advertised_gateway_link_symbol=gateway,classification_source=SYMBOL_CLASSIFICATION_SOURCE)


def self_call_snapshot(self_calls=None,own_call='N0ANT'):
    """Return exact configured addresses, never the whole base-callsign family."""
    values=(own_call,) if self_calls is None else self_calls
    if not isinstance(values,tuple) or len(values)>32:raise ValueError('Expected at most 32 exact self identities as a tuple')
    result=[]
    for value in values:
        if not isinstance(value,str) or not re.fullmatch(r'[A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?',value):raise ValueError('Invalid exact self identity')
        if value not in result:result.append(value)
    return tuple(result)


def station_counts(db,*,self_calls=None,own_call='N0ANT'):
    """Directory-wide received aggregates; raw history and TX are separate."""
    identities=self_call_snapshot(self_calls,own_call)
    condition='call IN ('+','.join('?' for _ in identities)+')' if identities else '0'
    total,packets,ours,our_packets=db.execute('SELECT count(*),coalesce(sum(packets),0),coalesce(sum(CASE WHEN '+condition+' THEN 1 ELSE 0 END),0),coalesce(sum(CASE WHEN '+condition+' THEN packets ELSE 0 END),0) FROM stations',identities+identities).fetchone()
    return dict(scope='directory',stations=total,self_stations=ours,remote_stations=total-ours,received_records=packets,self_received_records=our_packets,remote_received_records=packets-our_packets)
