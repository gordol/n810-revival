"""Nets settings, bounded observations and agenda projection without UI or transport."""
import collections
import datetime as dt
import importlib.util
from pathlib import Path

_spec=importlib.util.spec_from_file_location('nets_calendar_model',Path(__file__).with_name('n810-net-calendar.py'))
cal=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(cal)


def restore(settings,default_lead=0):
    lead=settings.get('lead',default_lead) if settings.get('version')==2 else 0
    enabled=set(settings.get('enabled',[])) if settings.get('version')==2 else set()
    confirmed=settings.get('confirmed',[])
    if type(lead) is not int or not 0<=lead<=1440:lead=default_lead
    sent=collections.OrderedDict((key,None) for key in settings.get('sent',[]) if isinstance(key,str))
    observations=collections.OrderedDict((row['id'],row) for row in settings.get('heard',[]) if isinstance(row,dict) and 'id' in row)
    return lead,enabled,confirmed,sent,observations


def state_payload(lead,enabled,confirmed,sent,observations):
    return dict(version=2,lead=lead,enabled=sorted(enabled),confirmed=confirmed,sent=list(sent)[-500:],heard=list(observations.values())[-200:])


def observe(observations,row):
    observations[row['id']]=row
    if len(observations)>200:observations.popitem(last=False)


def agenda(data,confirmed,observations,enabled,now,*,heard=False,today=False):
    scheduled=cal.upcoming(dict(nets=data['nets']+confirmed),now)
    for item in scheduled:item['reminders']=item['id'] in enabled
    unverified=[item for item in reversed(observations.values()) if 'radio-'+item['id'] not in {net['id'] for net in confirmed}]
    rows=list(reversed(observations.values())) if heard else scheduled+unverified
    if today and not heard:
        zone=cal.ZoneInfo('America/Los_Angeles');date=now.astimezone(zone).date()
        rows=[row for row in rows if 'start' not in row or row['start'].astimezone(zone).date()==date]
    return scheduled,rows


def confirmed_schedule(row,values,now=None):
    days={name.lower():i for i,name in enumerate(('Mon','Tue','Wed','Thu','Fri','Sat','Sun'))}
    if not cal.re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',values['time']):raise ValueError('Use HH:MM time')
    weekdays=sorted(set(days[v.strip().lower()] for v in values['days'].split(',')))
    cal.ZoneInfo(values['timezone']);frequency=float(values['frequency'])
    if not values['name'] or not cal.math.isfinite(frequency) or frequency<=0:raise ValueError('Name and valid frequency required')
    return dict(id='radio-'+row['id'],name=values['name'],call=row['call'],time=values['time'],
                timezone=values['timezone'],weekdays=weekdays,frequency_mhz=frequency,mode='FM',
                source='Radio · user confirmed',source_url='APRS '+row['call'],raw=row['raw'],
                checked=(now or dt.datetime.now(cal.UTC)).date().isoformat(),notes=row['text'])
