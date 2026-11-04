#!/usr/bin/env python3
"""Compact radio snapshot browser with separate saved presets and app shortcuts."""
import curses
import datetime
import importlib.util
import time
from pathlib import Path
from types import SimpleNamespace


def module(name):
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),Path(__file__).with_name(name+'.py'))
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


readback=module('n810-radio-readback')
live=module('n810-radio-live')


def stamp(data):
    try:return datetime.datetime.fromisoformat(data.get('finished',data['started'])).astimezone().strftime('%b %d %H:%M %Z')
    except (KeyError,ValueError):return 'Time unknown'


def channel(bank,index):
    return next((r.get('decoded',{}) for r in bank.get('channels',[]) if r['index']==index),{})


def draw(win,data,bi,ci,focus,detail,scroll,notice,telemetry=None):
    h,w=win.getmaxyx();win.erase()
    def put(y,x,text,attr=0,width=None):
        if 0<=y<h-1 and 0<=x<w-1:
            try:win.addnstr(y,x,str(text),min(width or w,w-x-1),attr)
            except curses.error:pass
    put(0,1,'RADIO PREVIEW',curses.A_BOLD)
    put(0,22,'1 On radio',curses.A_REVERSE)
    put(0,39,'2 Saved presets')
    if not data:
        put(3,1,'No completed radio download found.')
        put(5,1,'2 saved presets   r reload   q close')
    else:
        banks=sorted(data['banks'],key=lambda row:row['index'])
        telemetry=telemetry or {};fields=telemetry.get('fields',{})
        settings=telemetry.get('settings',data.get('settings',{}))
        status=telemetry.get('status',data.get('status',{}))
        beacon=telemetry.get('beacon',data.get('beacon',{}))
        active=next((b for b in banks if b['index']==status.get('curr_region')), {})
        age=max(0,int(time.time()-fields.get('status',time.time())))
        connected=telemetry.get('connected') and time.time()-telemetry.get('heartbeat',0)<15
        enabled=telemetry.get('enabled',live.read(live.CONTROL).get('enabled',False))
        mode='PAUSED' if not enabled else 'DISCONNECTED' if not connected else 'WAITING' if 'status' not in fields else 'STALE' if age>20 else 'LIVE'
        put(2,1,'RADIO '+mode+' / '+active.get('name','Unknown bank')+(' / updated %ds ago'%age if 'status' in fields else ''),curses.A_BOLD)
        if fields:
            current=(status.get('curr_channel_id_upper',0)<<4)|status.get('curr_ch_id_lower',0)
            activity='TX' if status.get('is_in_tx') else 'RX' if status.get('is_in_rx') else 'Idle'
            put(3,1,'%s / selected memory %02d / dual watch %s / l %s'%(activity,current,'on' if status.get('double_channel') else 'off','pause' if enabled else 'resume'))
        else:put(3,1,'Snapshot / live radio status unavailable / l resume',curses.A_DIM)
        positions=[1,max(22,w//3),max(44,2*w//3)]
        a=(settings.get('channel_a_upper',0)<<4)|settings.get('channel_a_lower',0)
        b=(settings.get('channel_b_upper',0)<<4)|settings.get('channel_b_lower',0)
        encoded=(settings.get('auto_share_loc_ch_upper',0)<<5)|settings.get('auto_share_loc_ch',0)
        for x,label,index in [(positions[0],'A',a),(positions[1],'B',b)]:
            p=channel(active,index)
            put(5,x,'%s  %02d %s'%(label,index,p.get('name_str','Unknown')),curses.A_BOLD,w//3-2)
            put(6,x,'%.3f MHz'%(p['rx_freq']/1e6) if p.get('rx_freq') else 'Frequency unknown',width=w//3-2)
            power='High' if p.get('tx_at_max_power') else 'Medium' if p.get('tx_at_med_power') else 'Low'
            put(7,x,power+' / '+('Wide' if p.get('bandwidth') else 'Narrow'),width=w//3-2)
            put(8,x,'Tone RX '+readback.tone(p.get('rx_sub_audio',0))+' / TX '+readback.tone(p.get('tx_sub_audio',0)),width=w//3-2)
        put(5,positions[2],'DIGITAL / '+('%02d'%(encoded-1) if encoded else 'current'),curses.A_BOLD)
        put(6,positions[2],'KISS '+('on' if settings.get('kiss_en') else 'off'))
        put(7,positions[2],'Auto beacon '+('on' if beacon.get('should_share_location') else 'off'))
        put(10,1,'Memory names/details: downloaded '+stamp(data),curses.A_DIM)
        if detail:
            put(12,1,detail.upper()+' / DOWNLOADED',curses.A_BOLD)
            rows=readback.sections(data,{'Settings':1,'APRS':2,'Raw replies':3}[detail])
            for y,(key,value) in enumerate(rows[scroll:scroll+max(1,h-18)],14):put(y,1,'%-30s %s'%(key,value))
        elif banks:
            left=max(18,w//5);right=max(left+24,w//2)
            put(12,1,('> ' if focus==0 else '  ')+'BANKS ON RADIO',curses.A_BOLD,left-2)
            put(12,left,('> ' if focus==1 else '  ')+'MEMORIES',curses.A_BOLD)
            put(12,right,'SELECTED MEMORY',curses.A_BOLD)
            for y,(i,bank) in enumerate(enumerate(banks),14):
                put(y,1,'%d %s'%(bank['index'],bank['name']),curses.A_REVERSE if i==bi else 0,left-2)
            rows=banks[bi]['channels'];visible=max(1,h-19);start=max(0,ci-visible+1)
            for y,(i,row) in enumerate(list(enumerate(rows))[start:start+visible],14):
                p=row.get('decoded',{});empty=not p.get('rx_freq')
                put(y,left,'%02d %s'%(row['index'],'(empty)' if empty else p.get('name_str') or '(unnamed)'),curses.A_REVERSE if i==ci else 0,right-left-2)
            if rows:
                row=rows[ci]
                put(13,right,'Browsing only / does not tune',curses.A_DIM)
                if not row.get('decoded',{}).get('rx_freq'):put(15,right,'Empty memory')
                else:
                    for y,(key,value) in enumerate(readback.channel_details(row),15):
                        if y<h-4:put(y,right,'%-16s %s'%(key,value))
        put(h-4,1,notice or ('Enter / q back to banks' if detail else 'Arrows browse  s settings  a APRS  x raw  l live/pause  r reload  q close'))
    put(h-2,1,'OTHER APPS   d Services directory   h Heard stations   m Messages',curses.A_DIM)
    win.refresh()


def run(win):
    curses.curs_set(0);win.keypad(True);win.timeout(250)
    path,data=readback.latest();bi=ci=focus=scroll=0;detail=None;notice='';dirty=True;size=None
    telemetry={};next_check=0
    while True:
        if time.monotonic()>=next_check:
            new=live.read();next_check=time.monotonic()+1
            if new!=telemetry:telemetry=new;dirty=True
        banks=sorted(data.get('banks',[]),key=lambda b:b['index']) if data else []
        bi=max(0,min(bi,len(banks)-1));rows=banks[bi]['channels'] if banks else []
        ci=max(0,min(ci,len(rows)-1))
        if dirty or size!=win.getmaxyx():draw(win,data,bi,ci,focus,detail,scroll,notice,telemetry);size=win.getmaxyx();dirty=False
        key=win.getch()
        if key==-1:continue
        dirty=True;notice=''
        if key in (ord('q'),27):
            if detail:detail=None;scroll=0
            else:return
        elif key in (ord('2'),ord('p')):
            control=module('n810-radio-control')
            control.run(win,SimpleNamespace(store=control.STORE))
            path,data=readback.latest()
        elif key==ord('l'):
            live.enable(not live.read(live.CONTROL).get('enabled',False))
            notice='Live monitoring preference sent';next_check=0
        elif key==ord('1'):detail=None;scroll=0
        elif key in (ord('d'),ord('h'),ord('m')):
            try:module('n810-ui-window').open_window({ord('d'):'Services Directory',ord('h'):'Heard Stations',ord('m'):'Messages'}[key])
            except (OSError,RuntimeError) as exc:notice=str(exc)
        elif key==ord('r'):path,data=readback.latest();notice='Reloaded downloaded snapshot'
        elif key in (ord('s'),ord('a'),ord('x')):detail={ord('s'):'Settings',ord('a'):'APRS',ord('x'):'Raw replies'}[key];scroll=0
        elif key in (10,13,curses.KEY_ENTER):
            if detail:detail=None
            else:focus=1-focus
        elif key in (curses.KEY_LEFT,curses.KEY_RIGHT):focus=int(key==curses.KEY_RIGHT)
        elif key in (curses.KEY_UP,curses.KEY_DOWN,ord('j'),ord('k')):
            delta=1 if key in (curses.KEY_DOWN,ord('j')) else -1
            if detail and data:scroll=max(0,min(max(0,len(readback.sections(data,{'Settings':1,'APRS':2,'Raw replies':3}[detail]))-1),scroll+delta))
            elif focus:ci=max(0,min(len(rows)-1,ci+delta))
            else:bi=max(0,min(len(banks)-1,bi+delta));ci=0


if __name__=='__main__':
    live.enable(True)
    try:curses.wrapper(run)
    finally:live.enable(False)
