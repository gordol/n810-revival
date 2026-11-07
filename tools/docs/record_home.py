#!/usr/bin/env python3
"""Capture Pocket in a fresh local state directory using filtered station history.

Requires Pillow and ffmpeg. Supply --stations and --exclude-call explicitly.
The source database is opened read-only. Output and review logs stay in a new
--work directory until their contents have been inspected. No service attaches.
"""
import argparse
from contextlib import closing
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

from record_tours import ROOT, environment, record
sys.path.insert(0,str(ROOT/'pocket/shell'))
from core import Host,Window
from panel import Panels
from session import capture
from runtime_codec import pack


def station_copy(source,destination,excluded):
    spec=importlib.util.spec_from_file_location('demo_directory',ROOT/'pocket/shell/vendor/packet-console/n810-directory-model.py')
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    target=model.database(destination)
    def permitted(call):
        return bool(re.fullmatch(r'[A-Z0-9]{1,6}(?:-\d{1,2})?',call)) and call.split('-')[0] not in excluded
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as db:
        db.execute('PRAGMA query_only=ON');db.execute('BEGIN')
        stations=[row for row in db.execute('SELECT call,first,last,packets FROM stations') if permitted(row[0])]
        calls={row[0] for row in stations}
        target.executemany('INSERT INTO stations VALUES(?,?,?,?)',stations)
        for call,kind,stamp,detail in db.execute('SELECT call,kind,stamp,detail FROM evidence'):
            if call not in calls or kind not in ('position','symbol','phg','role','messaging'):continue
            if any(value in detail.upper() for value in excluded):continue
            target.execute('INSERT INTO evidence VALUES(?,?,?,?)',(call,kind,stamp,detail))
        target.commit()
    target.close()
    return dict(stations=len(stations),latest_report=max((row[2] for row in stations),default=None))


def club_copy(source,destination,call):
    with closing(sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)) as db,closing(sqlite3.connect(destination)) as out,out:
        db.execute('PRAGMA query_only=ON')
        names=[row[1] for row in db.execute('PRAGMA table_info(stations)')]
        row=db.execute('SELECT * FROM stations WHERE callsign=?',(call,)).fetchone()
        if row is None or 'CLUB' not in str(row[names.index('name')]).upper():raise ValueError('Select a public club record for the ULS demonstration')
        for table in ('stations','license_details','fcc_meta'):
            out.execute(db.execute('SELECT sql FROM sqlite_master WHERE type=? AND name=?',('table',table)).fetchone()[0])
            rows=db.execute('SELECT * FROM '+table+' WHERE '+('key IN (?,?,?)' if table=='fcc_meta' else 'callsign=?'),('source_data_date','source_url','imported_at') if table=='fcc_meta' else (call,)).fetchall()
            for record_row in rows:out.execute('INSERT INTO '+table+' VALUES('+','.join('?' for _ in record_row)+')',record_row)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stations',type=Path,required=True)
    parser.add_argument('--exclude-call',action='append',required=True)
    parser.add_argument('--uls',type=Path)
    parser.add_argument('--club',default='W7DK')
    parser.add_argument('--work',type=Path,required=True)
    args=parser.parse_args()
    args.work.mkdir(parents=True,exist_ok=False)
    state=args.work/'session';state.mkdir(mode=0o700)
    excluded={value.upper().split('-')[0] for value in args.exclude_call}
    summary=station_copy(args.stations,state/'directory.sqlite3',excluded)
    if args.uls:club_copy(args.uls,state/'uls.sqlite',args.club)
    windows=[Window('Station Map',62,1,136,54),Window('ULS Lookup',2,2,58,28),Window('Stations',2,33,78,25)]
    host=Host(200,60,windows,animate=True);host.focus='Station Map';host.set_effect('flux')
    host.set_palette('ice');host.window_opacity=1.;host.shadow_enabled=False
    host.show_connectivity=False;host.show_clock=False;host.flux_density=2
    host.background_enabled=True
    panels=Panels('top',mode='bar')
    saved=capture(host,panels)
    saved['app_views']['Station Map']=dict(station_labels=True,show_repeaters=False,layers_visible=False)
    if args.uls:saved['app_views']['ULS Lookup']=dict(database=str(state/'uls.sqlite'))
    (state/'desktop.json').write_bytes(pack(saved))
    env=environment(args.work);env.update(HOME=str(args.work/'home'),XDG_DATA_HOME=str(args.work/'data'))
    Path(env['HOME']).mkdir();Path(env['XDG_DATA_HOME']).mkdir()
    os.environ['DOCS_REJECT_TEXT']='|'.join(excluded)
    cmd=[sys.executable,str(ROOT/'pocket/shell/launch.py'),'--state',str(state),'--no-local-services','--no-native','--no-save','--effect','flux','--station-maps',str(ROOT/'pocket/shell/vendor/packet-console/maps')]
    steps=[(0,'Received stations over public terrain | local laptop session',None),
           (1,'Look up a public radio club',b'\x1d,ULS Lookup\r'),
           (3,'Offline club record',args.club.encode()+b'\r'),
           (8,'Received stations and the offline radio-club lookup',b'\x1d,Station Map\r'),
           (12,'Maximize the map',b'\x1dZ'),
           (16,'Resize the terminal: 140 columns by 44 rows',('resize',140,44)),
           (23,'Resize the terminal: 200 columns by 62 rows',('resize',200,62)),
           (32,'Restore the window layout',b'Z'),
           (36,'Open the desktop overview',b'd'),
           (40,'Activate the selected window',b'\r'),
           (43,'Switch to the third desktop',b'\x1d3'),
           (48,'Window previews over Flux',b'd')]
    (args.work/'capture-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    record(cmd,env,'pocket-desktop','Pocket | received station history | local laptop capture',200,62,steps,52,args.work,b'q',11,output=args.work)

if __name__=='__main__':main()
