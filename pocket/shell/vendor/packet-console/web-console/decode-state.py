"""Normalize browser facts with the shared KISS/APRS decoder on the laptop."""
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
root=Path(__file__).resolve().parent.parent
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,root/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
monitor=module('web_monitor','n810-packet-monitor.py')
decode=module('web_aprs_decode','n810-aprs-decode.py')
messages=module('web_messages','n810-aprs-messages.py')
data=json.load(sys.stdin);packets=[]
radio=module('web_radio','web-console/radio-read-model.py')
if '--radio-compare' in sys.argv:
    print(json.dumps(radio.compare_channels(data.get('native'),data.get('draft')),separators=(',',':')));raise SystemExit
if 'radio_snapshot' in data or 'radio_live' in data:
    data['radio_model']=radio.normalize_radio(data,data.get('radio_live'))
for row in data.pop('records',[])[:200]:
    try:
        text=monitor.describe(bytes.fromhex(row['frame']))
        if not text or text.startswith(('Malformed','Short')):continue
        source,tail=text.split('>',1);route=tail.split(' ',1)[0].split(',')
        payload=text.split(' pid=f0 ',1)[1] if ' pid=f0 ' in text else ''
        facts=decode.decode(payload,route[0]) if payload else {'format':'AX.25','evidence':[]}
        stamp=datetime.datetime.fromisoformat(row['time']).strftime('%H:%M:%S')
        message=messages.parse_message(stamp+' '+text)
        packets.append(dict(id=hashlib.sha256((row['time']+row['frame']).encode()).hexdigest(),time=row['time'],direction=row['direction'],source=source,destination=route[0],path=route[1:],used_relays=[h[:-1] for h in route[1:] if h.endswith('*')],payload=payload,raw=text,frame=row['frame'],facts=facts,message=message))
    except (ValueError,KeyError,TypeError):continue
if packets:data['packets']=packets
elif 'history_source' in data:data['packets']=[]
if 'outbox' in data:
    cal=module('web_net_calendar','n810-net-calendar.py')
    try:
        schedule=cal.load(root/'data/nets-puget-sound.json')
        data['nets']=[dict(row,start=row['start'].isoformat(),local=row['local'].isoformat()) for row in cal.upcoming(schedule)[:150]]
    except (OSError,ValueError,KeyError):data['nets']=[]
print(json.dumps(data,separators=(',',':')))
