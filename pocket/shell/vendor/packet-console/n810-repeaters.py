#!/usr/bin/env python3
"""Private offline repeater directory; distance sorting is not a coverage model."""
from contextlib import closing
import argparse
import csv
import curses
import datetime
import importlib.util
import io
import json
import math
import os
import sqlite3
from pathlib import Path
import tempfile
import zipfile

LOCAL_DATA=Path('~/.local/share/n810-radio/repeaters.json').expanduser()
BUNDLED_DATA=Path(__file__).resolve().parents[3]/'data/repeaters/repeaters.json'
DATA=LOCAL_DATA if LOCAL_DATA.exists() else BUNDLED_DATA


def distance(lat,lon,other_lat,other_lon):
    a,b=math.radians(lat),math.radians(other_lat)
    dlat=b-a;dlon=math.radians(other_lon-lon)
    h=math.sin(dlat/2)**2+math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return 6371*2*math.asin(math.sqrt(min(1,max(0,h))))


def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f);f.write('\n')
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def import_wwara(path):
    with zipfile.ZipFile(path) as archive:
        names=[n for n in archive.namelist() if n.startswith('WWARA-rptrlist-') and n.endswith('.csv')]
        if len(names)!=1:raise ValueError('Expected one coordinated-repeater CSV')
        name=names[0];text=archive.read(name).decode('utf-8-sig')
        if text.startswith('DATA_SPEC_VERSION='):text=text.split('\n',1)[1]
        rows=[]
        for record in csv.DictReader(io.StringIO(text)):
            def number(key):
                try:return float(record[key].strip())
                except (ValueError,KeyError):return None
            rx,tx=number('OUTPUT_FREQ'),number('INPUT_FREQ')
            if not rx or not tx:continue
            modes=[label for key,label in [('FM_WIDE','FM wide'),('FM_NARROW','FM narrow'),('DMR','DMR'),('DSTAR_DV','D-Star'),('FUSION','Fusion'),('P25_PHASE_1','P25'),('NXDN_DIGITAL','NXDN')] if record.get(key)=='Y']
            rows.append(dict(id=record['FC_RECORD_ID'].strip(),call=record['CALL'].strip(),
                site=record['CITY'].strip(),area=record['LOCALE'].strip(),rx_mhz=rx,tx_mhz=tx,
                tx_ctcss=number('CTCSS_IN'),rx_ctcss=number('CTCSS_OUT'),dcs=record.get('DCS_CDCSS','').strip(),
                lat=number('LATITUDE'),lon=number('LONGITUDE'),modes=modes,
                expiry=record.get('EXPIRATION_DATE','').strip(),url=record.get('URL','').strip(),
                sponsor=record.get('SPONSOR','').strip(),comment=record.get('COMMENT','').strip()))
        return dict(version=1,source='WWARA',source_url='https://www.wwara.org/coordinations/coordination-data-files/',
                    edition=name.removeprefix('WWARA-rptrlist-').removesuffix('.csv'),
                    downloaded=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    notice=archive.read('copyright.txt').decode('utf-8-sig'),
                    coordinate_note='Some coordinates are intentionally approximate by up to 50 miles.',repeaters=rows)


def candidates(data,lat,lon,radius=150,asof=None):
    asof=asof or datetime.date.today().isoformat();rows=[]
    for record in data['repeaters']:
        if not any(m.startswith('FM ') for m in record['modes']):continue
        if not (136<=record['rx_mhz']<=174 or 400<=record['rx_mhz']<=520):continue
        if record['expiry'] and record['expiry']<asof:continue
        if record['lat'] is None or record['lon'] is None:continue
        row=dict(record,km=distance(lat,lon,record['lat'],record['lon']))
        if row['km']<=radius:rows.append(row)
    return sorted(rows,key=lambda r:(r['km'],r['rx_mhz'],r['id']))


def add_to_library(row,edition=''):
    if row['dcs']:raise ValueError('DCS entry needs review; not added by this CTCSS editor')
    spec=importlib.util.spec_from_file_location('banks',Path(__file__).with_name('n810-radio-banks.py'))
    banks=importlib.util.module_from_spec(spec);spec.loader.exec_module(banks)
    data=banks.load(banks.STORE)
    bank=next((b for b in data['banks'] if b['name']=='Repeater picks'),None)
    if bank is None:
        import uuid
        bank=dict(id=uuid.uuid4().hex,name='Repeater picks',channels=[]);data['banks'].append(bank)
    if any(c.get('wwara_id')==row['id'] for c in bank['channels']):return 'Already in Repeater picks'
    channel=banks.channel((row['call']+' '+row['site'])[:48],row['rx_mhz'])
    channel.update(tx_mhz=row['tx_mhz'],tx_ctcss=row['tx_ctcss'],rx_ctcss=None,
                   bandwidth='Wide' if 'FM wide' in row['modes'] else 'Narrow',
                   wwara_id=row['id'],source_url=row['url'],source='WWARA',source_edition=edition,review='unverified')
    bank['channels'].append(channel);banks.save(banks.STORE,data)
    return 'Added to local Repeater picks'


FILTERS=('Voice','Packet','Winlink','Mailboxes','All')


def directory_rows(data,services,lat,lon,radius=150,category='Voice',asof=None):
    rows=[]
    for entry in candidates(data,lat,lon,radius,asof):
        rows.append(dict(entry,kind='Voice',transport=', '.join(entry['modes']),
                         source='WWARA',source_date=data['edition'],source_url=data['source_url'],
                         capture='Coordination listing',baud=None,connect_call=None))
    for item in services.get('services',[]):
        kind={'Winlink gateway':'Winlink','Mailbox':'Mailboxes'}.get(item['service'],'Packet')
        frequency=item['frequency_mhz']
        if not (136<=frequency<=174 or 400<=frequency<=520):continue
        position=item.get('position');km=None
        if position is not None:
            km=distance(lat,lon,position[0],position[1])
            if km>radius:continue
        identity='|'.join([item['call'],str(frequency),item['service'],item['transport']])
        rows.append(dict(id=identity,call=item['call'],site=item['area'],area=item['area'],
                         rx_mhz=frequency,tx_mhz=frequency,tx_ctcss=None,rx_ctcss=None,dcs='',
                         km=km,kind=kind,transport=item['transport'],baud=item.get('baud'),
                         connect_call=item['call'],alias=item.get('alias',''),source='District 3 listing',
                         source_date=item['source_checked'],source_url=item['source_url'],
                         capture=item['verification'],table_revision=services.get('source_rms_table_revision'),expiry='',url='',sponsor='',modes=[]))
    if category!='All':rows=[row for row in rows if row['kind']==category]
    return sorted(rows,key=lambda row:(row['km'] is None,row['km'] or 0,row['call'],row['rx_mhz']))


def observations(path):
    try:
        with closing(sqlite3.connect('file:'+str(Path(path).expanduser())+'?mode=ro',uri=True,timeout=.1)) as db:
            return {call:(last,count) for call,last,count in db.execute('SELECT call,last,packets FROM stations')}
    except sqlite3.Error:return {}


def add_service(row,store=None):
    spec=importlib.util.spec_from_file_location('banks',Path(__file__).with_name('n810-radio-banks.py'))
    banks=importlib.util.module_from_spec(spec);spec.loader.exec_module(banks)
    path=store or banks.STORE;data=banks.load(path);name='Data service picks'
    bank=next((b for b in data['banks'] if b['name']==name),None)
    if bank is None:
        import uuid
        bank=dict(id=uuid.uuid4().hex,name=name,channels=[]);data['banks'].append(bank)
    if any(c.get('service_id')==row['id'] for c in bank['channels']):return 'Already in '+name
    channel=banks.channel(row['call'],row['rx_mhz'])
    channel.update(service_id=row['id'],connect_call=row['connect_call'],transport=row['transport'],
                   baud=row['baud'],source_url=row['source_url'],source_checked=row['source_date'],
                   review='unverified',review_required=['baud','bandwidth','access','tones'])
    bank['channels'].append(channel);banks.save(path,data);return 'Added local draft to '+name


def details(row,heard):
    lines=[row['call']+' / '+row['site'],'',row['kind']+' / '+row['transport'],'',
           'RX       %.4f MHz'%row['rx_mhz']]
    if row['kind']=='Voice':
        lines += ['TX       %.4f MHz'%row['tx_mhz'], 'Offset   %+.3f MHz'%(row['tx_mhz']-row['rx_mhz']),
                  'TX tone  '+(str(row['tx_ctcss'])+' Hz' if row['tx_ctcss'] else 'Not listed'),
                  'RX tone  '+(str(row['rx_ctcss'])+' Hz' if row['rx_ctcss'] else 'Not listed'),
                  'DCS      '+(row['dcs'] or 'Not listed')]
    else:
        lines += ['Connect  '+row['connect_call'], 'Baud     '+(str(row['baud']) if row['baud'] else 'Unknown'),
                  'Access   Not verified']
        if row.get('alias'):lines += ['Alias    '+row['alias']]
    lines += ['', 'APRS CALL OBSERVATIONS']
    if row['call'] in heard:
        stamp,count=heard[row['call']];lines += [stamp,'%d captured packets'%count]
    else:lines += ['No matching callsign captured']
    lines += ['', 'SOURCE',row['source'],('Edition ' if row['kind']=='Voice' else 'Checked ')+row['source_date']]
    if row['kind']=='Voice':lines += ['Coordination expires '+(row['expiry'] or 'Unknown')]
    else:
        if row.get('table_revision'):lines += ['RMS table revised '+row['table_revision']]
        lines += ['Published listing / not RF tested']
    return lines


def draw(win,rows,selected,data,args,notice,category,heard):
    h,w=win.getmaxyx();win.erase();split=max(34,w//2)
    def put(y,x,text,attr=0,width=None):
        if 0<=y<h and x<w-1:
            try:win.addnstr(y,x,str(text),min(width or w,w-x-1),attr)
            except curses.error:pass
    put(0,1,'RADIO SERVICES',curses.A_BOLD)
    x=1
    for number,label in enumerate(FILTERS,1):
        title='%d %s  '%(number,label)
        put(2,x,title,curses.A_REVERSE if label==category else 0);x+=len(title)
    put(3,1,'%d entries / fixed reference %.3f, %.3f / %d km'%(len(rows),args.lat,args.lon,args.radius))
    put(5,1,'RX MHz   CALL       ~KM  AREA',curses.A_BOLD)
    visible=max(1,h-10);start=max(0,selected-visible+1)
    for y,(i,row) in enumerate(list(enumerate(rows))[start:start+visible],7):
        km='%3d'%round(row['km']) if row['km'] is not None else ' --'
        put(y,1,'%.3f  %-9s %s  %s'%(row['rx_mhz'],row['call'],km,row['site']),curses.A_REVERSE if i==selected else 0,split-3)
    if rows:
        for y,line in enumerate(details(rows[selected],heard),5):
            put(y,split,line,curses.A_BOLD if y==5 or line in ('SOURCE','APRS CALL OBSERVATIONS') else 0)
    else:put(7,1,'No matching entries')
    if notice:put(h-3,1,notice)
    put(h-1,1,'Left/right filter  Up/down select  a presets  g nets  r refresh  ? source  q quit')
    win.refresh()


def run(win,data,args):
    curses.curs_set(0);win.keypad(True);win.timeout(200)
    category=args.category;selected=0;notice='';dirty=True;size=None;help_open=False
    def refresh():
        try:services=json.loads(args.services.read_text())
        except (OSError,ValueError):services={}
        return directory_rows(data,services,args.lat,args.lon,args.radius,category),observations(args.heard_db)
    rows,heard=refresh()
    while True:
        if dirty or size!=win.getmaxyx():
            draw(win,rows,selected,data,args,notice,category,heard)
            if help_open:
                win.erase()
                selected_row=rows[selected] if rows else None
                lines=['RADIO SERVICES / SOURCE','',selected_row['source_url'] if selected_row else data['source_url'],'',
                       'Distances are approximate; -- means position unknown.',
                       'Entries without coordinates remain visible in their regional pack.',
                       'APRS counts match exact callsigns, not services or frequency.',
                       'An observation may have arrived through relays or an Internet gateway.',
                       'No coverage model, GPS feed, or live gateway query is active.',
                       'a copies a channel into saved radio presets; it does not program the radio.',
                       'Data-service baud, access and channel settings require review.',
                       '',data['coordinate_note'],'']+data['notice'].splitlines()+['','? close help']
                h,w=win.getmaxyx()
                for y,line in enumerate(lines[:h-1]):
                    try:win.addnstr(y,1,line,w-2)
                    except curses.error:pass
                win.refresh()
            dirty=False;size=win.getmaxyx()
        key=win.getch()
        if key==-1:continue
        dirty=True
        if key==ord('?'):help_open=not help_open;continue
        if key==ord('g'):
            spec=importlib.util.spec_from_file_location('ui_window',Path(__file__).with_name('n810-ui-window.py'))
            helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
            try:helper.open_window('Nets')
            except (OSError,RuntimeError) as exc:notice=str(exc)
            continue
        if key in (ord('q'),27):break
        if help_open:continue
        if key in (curses.KEY_LEFT,curses.KEY_RIGHT) or ord('1')<=key<=ord('5'):
            category=FILTERS[key-ord('1')] if ord('1')<=key<=ord('5') else FILTERS[(FILTERS.index(category)+(1 if key==curses.KEY_RIGHT else -1))%len(FILTERS)]
            selected=0;notice='';rows,heard=refresh()
        elif key in (curses.KEY_DOWN,ord('j')):selected=min(max(0,len(rows)-1),selected+1)
        elif key in (curses.KEY_UP,ord('k')):selected=max(0,selected-1)
        elif key==ord('r'):
            rows,heard=refresh();selected=min(selected,max(0,len(rows)-1));notice='Refreshed local data'
        elif key==ord('a') and rows:
            try:notice=add_to_library(rows[selected],data['edition']) if rows[selected]['kind']=='Voice' else add_service(rows[selected])
            except (OSError,ValueError) as exc:notice=str(exc)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,default=DATA)
    p.add_argument('--import-wwara',type=Path);p.add_argument('--json',action='store_true')
    p.add_argument('--lat',type=float,default=5.5355);p.add_argument('--lon',type=float,default=5.5655)
    p.add_argument('--radius',type=float,default=150)
    p.add_argument('--services',type=Path,default=Path('~/.local/share/n810-radio/data-services.json').expanduser())
    p.add_argument('--heard-db',default='~/.local/state/n810-aprs/directory.sqlite3')
    p.add_argument('--category',choices=FILTERS,default='Voice');args=p.parse_args()
    if args.import_wwara:
        data=import_wwara(args.import_wwara);write(args.data,data);print('Imported',len(data['repeaters']),'records');return
    try:data=json.loads(args.data.read_text())
    except (OSError,ValueError) as exc:p.error('Load a private WWARA pack first: '+str(exc))
    if args.json:
        try:services=json.loads(args.services.read_text())
        except (OSError,ValueError):services={}
        for row in directory_rows(data,services,args.lat,args.lon,args.radius,args.category):print(json.dumps(row))
    else:curses.wrapper(run,data,args)

if __name__=='__main__':main()
