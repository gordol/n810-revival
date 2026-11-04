"""Timezone-aware net schedules and passive APRS announcements."""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from zoneinfo import ZoneInfo

UTC=dt.timezone.utc
ROOT=Path.home()/'.local/state/n810-aprs'
DATA=Path.home()/'.local/share/n810-radio/nets.json'
TIMESTAMP=r'(?:\d\d:\d\d:\d\d|\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:\d\d(?::\d\d(?:[.,]\d+)?)?))'
PACKET=re.compile(r'^('+TIMESTAMP+r') (\S+)>(\S+) ctl=(?:03|13) pid=f0 (.*)$')


def atomic(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.nets-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:
            json.dump(value,f,ensure_ascii=True,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def load(path):
    data=json.loads(Path(path).read_text())
    if data.get('version')!=1 or not isinstance(data.get('nets'),list):raise ValueError('Unsupported net schedule file')
    identities=set()
    for row in data['nets']:
        for key in ('id','name','call','time','timezone','weekdays','source_url','checked','frequency_mhz'):
            if key not in row:raise ValueError('Missing schedule field: '+key)
        if row['id'] in identities:raise ValueError('Duplicate schedule ID')
        identities.add(row['id']);ZoneInfo(row['timezone']);dt.date.fromisoformat(row['checked'])
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',row['time']):raise ValueError('Time must be HH:MM')
        if not isinstance(row['frequency_mhz'],(float,int)) or not math.isfinite(row['frequency_mhz']) or row['frequency_mhz']<=0:raise ValueError('Invalid frequency')
        if not row['weekdays'] or any(type(d)!=int or not 0<=d<=6 for d in row['weekdays']):raise ValueError('Invalid weekdays')
        if not row['source_url'].startswith('https://'):raise ValueError('Schedule needs a source URL')
    return data


def wall_times(day,time,zone):
    naive=dt.datetime.combine(day,dt.time.fromisoformat(time));result={}
    for fold in (0,1):
        local=naive.replace(tzinfo=zone,fold=fold);utc=local.astimezone(UTC)
        if utc.astimezone(zone).replace(tzinfo=None)==naive:result[utc]=local
    return [result[k] for k in sorted(result)]


def upcoming(data,now=None,days=7,call=None):
    now=(now or dt.datetime.now(UTC)).astimezone(UTC);end=now+dt.timedelta(days=days);result=[]
    for row in data['nets']:
        if call and row['call'].upper()!=call.upper():continue
        zone=ZoneInfo(row['timezone']);start=now.astimezone(zone).date()
        for offset in range(days+2):
            day=start+dt.timedelta(days=offset)
            if day.weekday() not in row['weekdays']:continue
            if row.get('valid_from') and day<dt.date.fromisoformat(row['valid_from']):continue
            if row.get('valid_until') and day>dt.date.fromisoformat(row['valid_until']):continue
            times=wall_times(day,row['time'],zone)
            # Repeated local times need a publisher/user decision, not two guessed alerts.
            if len(times)!=1:continue
            local=times[0];utc=local.astimezone(UTC)
            if now<=utc<end:
                result.append(dict(row,start=utc,local=local,occurrence=row['id']+'@'+utc.isoformat()))
    return sorted(result,key=lambda row:(row['start'],row['name']))


def due(rows,now,lead,sent):
    if not lead:return []
    now=now.astimezone(UTC)
    return [row for row in rows if 0<=(row['start']-now).total_seconds()<=lead*60 and row['occurrence'] not in sent]


def announcement(line):
    found=PACKET.match(line)
    if not found:return None
    stamp,call,route,payload=found.groups()
    bulletin=payload.startswith(':BLN') and len(payload)>=11 and payload[10]==':'
    is_net=bool(re.search(r'\b(?:net|nets|net\s*(?:mon|tue|wed|thu|fri|sat|sun))\b',payload,re.I))
    if not is_net and not bulletin:return None
    return dict(id=hashlib.sha256(line.encode()).hexdigest(),call=call,packet_time=stamp,
                kind='Bulletin' if bulletin else 'Net mention',text=payload[11:] if bulletin else payload,
                raw=line,time_basis='Unverified; packet may be replayed')


def ical(rows):
    def escape(text):return str(text).replace('\\','\\\\').replace('\n','\\n').replace(',','\\,').replace(';','\\;')
    def fold(text):
        lines=[];part='';size=0
        for char in text:
            count=len(char.encode('utf-8'))
            if size+count>73:lines.append(part);part=' '+char;size=1+count
            else:part+=char;size+=count
        return '\r\n'.join(lines+[part])
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//N810//Radio Nets//EN','CALSCALE:GREGORIAN']
    now=dt.datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')
    for row in rows:
        lines+=['BEGIN:VEVENT','UID:'+hashlib.sha256(row['occurrence'].encode()).hexdigest()+'@n810',
                'DTSTAMP:'+now,'DTSTART:'+row['start'].strftime('%Y%m%dT%H%M%SZ'),
                'SUMMARY:'+escape(row['name']),
                'DESCRIPTION:'+escape(row['call']+' / '+str(row.get('frequency_mhz','?'))+' MHz\n'+row['source_url']+'\nSource checked '+row['checked']),
                'END:VEVENT']
    return '\r\n'.join(fold(line) for line in lines+['END:VCALENDAR',''])
