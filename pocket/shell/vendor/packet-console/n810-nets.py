#!/usr/bin/env python3
"""Offline net agenda, local heads-up notices, and passive APRS announcements."""
import argparse
import collections
import curses
import datetime as dt
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import textwrap
import time


def module(name,filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value);return value

cal=module('net_calendar','n810-net-calendar.py')
model=module('nets_model','n810-nets-model.py')
style=module('radio_style','n810-radio-style.py')
windows=module('ui_window','n810-ui-window.py')
STATE=cal.ROOT/'nets-state.json'


def saved(path):
    try:
        value=json.loads(Path(path).read_text())
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError):return {}


def notify(row,minutes):
    pane=os.environ.get('TMUX_PANE')
    text='%s in %d min · %.3f MHz · %s' % (row['name'],minutes,row['frequency_mhz'],row['local'].strftime('%H:%M %Z'))
    if pane:
        session=subprocess.check_output(['tmux','-L','n810','display-message','-p','-t',pane,'#{session_name}'],text=True,timeout=15).strip()
        clients=subprocess.check_output(['tmux','-L','n810','list-clients','-t',session,'-F','#{client_tty}'],text=True,timeout=15).splitlines()
        for client in clients:
            subprocess.run(['tmux','-L','n810','display-message','-c',client,'-d','15000',text],check=True,timeout=15)
    return text


class Feed:
    def __init__(self,path):self.path=path;self.socket=None;self.retry=0;self.pending=b'';self.status='Waiting for feed'
    def poll(self):
        result=[]
        if self.socket is None and time.monotonic()>=self.retry:
            candidate=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);candidate.settimeout(.2)
            try:candidate.connect(self.path)
            except OSError:candidate.close();self.retry=time.monotonic()+3;self.status='Feed unavailable; schedules still work offline'
            else:self.socket=candidate;candidate.setblocking(False);self.pending=b'';self.status='Listening for net announcements'
        if self.socket:
            try:data=self.socket.recv(16384)
            except BlockingIOError:data=None
            except OSError:data=b''
            if data==b'':self.close();self.retry=time.monotonic()+3;self.status='Feed disconnected; retrying'
            elif data:
                self.pending+=data
                while b'\n' in self.pending:
                    line,self.pending=self.pending.split(b'\n',1)
                    row=cal.announcement(line.decode('utf-8','replace'))
                    if row:result.append(row)
                if len(self.pending)>65536:self.pending=b''
        return result
    def close(self):
        if self.socket:self.socket.close()
        self.socket=None;self.pending=b''


def put(win,y,x,text,width,attr=0):
    h,w=win.getmaxyx()
    if 0<=y<h and 0<=x<w:
        try:win.addnstr(y,x,str(text),max(0,min(width,w-x-1)),attr)
        except curses.error:pass


def draw(win,rows,selected,heard,lead,today,notice,status,detail_scroll=0):
    h,w=win.getmaxyx();win.erase()
    if h<18 or w<65:
        put(win,1,2,'Nets needs at least 65 columns × 18 rows.',w-4);win.refresh();return
    put(win,0,2,'NETS',w-4,style.accent())
    put(win,0,10,'Pacific time · offline agenda',w-12)
    put(win,2,2,'RADIO ANNOUNCEMENTS' if heard else 'TODAY' if today else 'NEXT SEVEN DAYS',w-4,curses.A_BOLD)
    hint='Reminder lead: '+('%d min'%lead if lead else 'off')+'  ·  selected nets only'
    put(win,2,max(30,w-len(hint)-3),hint,len(hint))
    put(win,3,2,'─'*(w-4),w-4,style.border())
    split=max(30,int(w*.46));visible=max(1,(h-10)//3)
    selected=min(selected,max(0,len(rows)-1));first=max(0,selected-visible+1)
    for y in range(4,h-4):put(win,y,split,'│',1,style.border())
    for index,row in enumerate(rows[first:first+visible],first):
        y=5+(index-first)*3;attr=style.selection() if index==selected else curses.A_BOLD
        if 'start' not in row:
            title=row['call']+' · radio announcement'
            frequency=cal.re.search(r'\d{2,3}\.\d+\s*MHz',row['text'],cal.re.I)
            subtitle=(frequency.group()+' · ' if frequency else '')+'Schedule unconfirmed'
        else:
            title=row['name']
            local=row['start'].astimezone(cal.ZoneInfo('America/Los_Angeles'))
            subtitle=local.strftime('%a %d %b %H:%M')+' · %.3f · '%row['frequency_mhz']+('Radio' if row.get('source') else 'Web')
            if row.get('reminders'):subtitle+=' · alert on'
        put(win,y,2,title.ljust(split-4),split-4,attr)
        put(win,y+1,2,subtitle.ljust(split-4),split-4,style.selection() if index==selected else 0)
    if not rows:put(win,6,2,'No matching announcements or schedules.',split-4)
    if rows:
        row=rows[selected];x=split+3;width=w-x-2;lines=[]
        def line(text='',attr=0):
            lines.extend((part,attr) for part in (textwrap.wrap(str(text),max(8,width)) or ['']))
        def section(title):line();line(title,curses.A_BOLD)
        def field(label,value):
            prefix=label.ljust(12)
            parts=textwrap.wrap(str(value),max(8,width-12)) or ['']
            lines.append((prefix+parts[0],0))
            lines.extend((' '*12+part,0) for part in parts[1:])
        if 'start' not in row:
            line(row['call'],style.accent());line('HEARD OVER RADIO · UNCONFIRMED')
            section('Schedule');line('Time, days and time zone need confirmation.')
            line('f  Confirm schedule · reminders stay off',style.accent())
            section('Received announcement');line(row['text'])
            section('Reception');field('Packet time',row['packet_time']);line(row['time_basis'])
            section('Original packet');line(row['raw'])
        else:
            pacific=row['start'].astimezone(cal.ZoneInfo('America/Los_Angeles'))
            line(row['name'],curses.A_BOLD)
            line(pacific.strftime('%A %d %B · %H:%M %Z'),style.accent())
            line('%.3f MHz · %s · %s'%(row['frequency_mhz'],row.get('mode','FM'),row['call']),style.accent())
            section('Reminder');line('ON · a to turn off' if row.get('reminders') else 'OFF · a to enable for this net')
            section('Schedule')
            field('Repeats',', '.join(('Mon','Tue','Wed','Thu','Fri','Sat','Sun')[d] for d in row['weekdays']))
            field('Published',row['time']+' '+row['timezone'])
            field('UTC',row['start'].strftime('%d %b %H:%M'))
            if row.get('notes'):section('About this net');line(row['notes'])
            section('Source');line(row.get('source','Web · published schedule'))
            field('Checked',row['checked']);line(row['source_url'])
            if row.get('raw'):section('Original packet');line(row['raw'])
        available=h-9;offset=min(detail_scroll,max(0,len(lines)-available))
        for y,(text,attr) in enumerate(lines[offset:offset+available],5):put(win,y,x,text,width,attr)
        if len(lines)>available:put(win,h-5,x,'←/→ scroll details',width)
    put(win,h-4,2,'─'*(w-4),w-4,style.border())
    put(win,h-3,2,notice or status,w-4)
    put(win,h-2,2,'j/k select   u agenda   h radio   f confirm   a reminder   ,/. lead',w-4)
    put(win,h-1,2,'s services   v map   m messages   c export   q close',w-4)
    win.refresh()


def confirm(win,row):
    values={}
    fields=[('name','Net name',row.get('call','')+' net'),('time','Local time HH:MM',''),
            ('days','Weekdays Mon,Tue,Wed,Thu,Fri,Sat,Sun',''),
            ('timezone','Time zone','America/Los_Angeles'),('frequency','Frequency MHz','')]
    for key,label,default in fields:
        text=default
        while True:
            win.erase();h,w=win.getmaxyx()
            put(win,1,2,'CONFIRM RADIO SCHEDULE · Escape cancels',w-4,curses.A_BOLD)
            for y,line in enumerate(textwrap.wrap(row['text'],max(10,w-4))[:5],3):put(win,y,2,line,w-4)
            put(win,10,2,label,w-4,curses.A_BOLD);put(win,12,2,text+'▏',w-4)
            put(win,15,2,'Enter accepts field · Backspace edits · reminders stay off',w-4);win.refresh()
            try:k=win.get_wch()
            except curses.error:continue
            if k=='\x1b':return None
            if k in ('\n','\r'):break
            if k in ('\x7f','\b',curses.KEY_BACKSPACE):text=text[:-1]
            elif isinstance(k,str) and k.isprintable() and len(text)<200:text+=k
        values[key]=text.strip()
    return model.confirmed_schedule(row,values)


def run(win,args):
    style.init_screen(win);win.keypad(True);win.timeout(250)
    try:curses.curs_set(0)
    except curses.error:pass
    lead,enabled,confirmed,sent,observations=model.restore(saved(STATE),args.lead)
    data=cal.load(args.data);feed=Feed(args.socket)
    selected=0;heard=False;today=False;notice='';dirty=True;size=None;updated=0;rows=[];detail_scroll=0
    def save():
        cal.atomic(STATE,model.state_payload(lead,enabled,confirmed,sent,observations))
    try:
        while True:
            for row in feed.poll():
                model.observe(observations,row)
                dirty=True
            if time.monotonic()-updated>=20:
                updated=time.monotonic();now=dt.datetime.now(cal.UTC)
                scheduled,rows=model.agenda(data,confirmed,observations,enabled,now,heard=heard,today=today)
                for row in cal.due([item for item in scheduled if item['id'] in enabled],now,lead,sent):
                    try:notice=notify(row,max(0,round((row['start']-now).total_seconds()/60)))
                    except (OSError,subprocess.SubprocessError) as exc:notice='Local alert: '+row['name']+' · '+str(exc)
                    sent[row['occurrence']]=None;save()
                dirty=True
            if heard:rows=list(reversed(observations.values()))
            selected=min(selected,max(0,len(rows)-1))
            if dirty or size!=win.getmaxyx():
                draw(win,rows,selected,heard,lead,today,notice,feed.status,detail_scroll);dirty=False;size=win.getmaxyx()
            key=win.getch()
            if key==-1:continue
            dirty=True
            if key in (ord('q'),27):break
            if key in (ord('j'),curses.KEY_DOWN):selected=min(selected+1,max(0,len(rows)-1));detail_scroll=0
            elif key in (ord('k'),curses.KEY_UP):selected=max(0,selected-1);detail_scroll=0
            elif key in (curses.KEY_LEFT,curses.KEY_RIGHT):detail_scroll=max(0,min(200,detail_scroll+(-3 if key==curses.KEY_LEFT else 3)))
            elif key in (ord('u'),ord('h')):heard=key==ord('h');selected=0;updated=0
            elif key==ord('t'):today=not today;selected=0;updated=0
            elif key==ord('f') and rows and 'start' not in rows[selected]:
                try:
                    item=confirm(win,rows[selected])
                    if item:
                        confirmed[:]=[net for net in confirmed if net['id']!=item['id']]+[item]
                        save();notice='Schedule confirmed; reminders off';updated=0
                except (ValueError,KeyError) as exc:notice='Not saved: '+str(exc)
            elif key==ord('a'):
                if rows and 'start' in rows[selected]:
                    identity=rows[selected]['id']
                    if identity in enabled:enabled.remove(identity);notice='Reminder off for this net'
                    else:
                        enabled.add(identity)
                        if not lead:lead=15
                        notice='Reminder enabled for this net'
                    save();updated=0
                else:notice='Confirm the radio schedule with f before enabling reminders'
            elif key in (ord(','),ord('.')):
                lead=max(0,min(1440,lead+(-5 if key==ord(',') else 5)))
                save();notice='Heads-up '+('%d minutes before'%lead if lead else 'off');updated=0
            elif key==ord('r'):
                try:data=cal.load(args.data);notice='Reloaded local schedules';updated=0
                except (OSError,ValueError) as exc:notice=str(exc)
            elif key in (ord('s'),ord('v'),ord('m')):
                try:save();windows.open_window({ord('s'):'Radio Services',ord('v'):'APRS',ord('m'):'Messages'}[key])
                except (OSError,RuntimeError,subprocess.SubprocessError) as exc:notice=str(exc)
            elif key==ord('c'):
                target=Path.home()/'nets.ics'
                fd,name=cal.tempfile.mkstemp(prefix='.nets-',dir=target.parent)
                try:
                    with os.fdopen(fd,'w',newline='') as f:f.write(cal.ical(cal.upcoming(dict(nets=data['nets']+confirmed),days=90)))
                    os.replace(name,target);notice='Exported next 90 days to '+str(target)
                finally:
                    if os.path.exists(name):os.unlink(name)
    finally:feed.close();save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,default=cal.DATA)
    parser.add_argument('--socket',default='/dev/shm/n810-aprs.sock')
    parser.add_argument('--lead',type=int,choices=range(1441),metavar='MINUTES',default=0,help='heads-up minutes, 0 disables (0–1440); saved setting takes precedence')
    parser.add_argument('--import-file',type=Path)
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    if args.import_file:cal.atomic(args.data,cal.load(args.import_file));print('Imported net schedules');return
    if args.json:
        for row in cal.upcoming(cal.load(args.data)):
            print(json.dumps({key:value.isoformat() if isinstance(value,dt.datetime) else value for key,value in row.items()}))
    else:
        STATE.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        with os.fdopen(os.open(STATE.with_suffix('.lock'),os.O_CREAT|os.O_RDWR,0o600),'r+') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise SystemExit('Nets is already running; open the Nets tmux window')
            curses.wrapper(run,args)

if __name__=='__main__':main()
