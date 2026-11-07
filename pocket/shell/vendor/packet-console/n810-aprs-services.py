#!/usr/bin/env python3
"""Read-only APRS station, service-hint and message browser for the RAM feed."""
import argparse
import collections
import curses
import re
import socket
import time
import textwrap

from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
_style_spec=spec_from_file_location('radio_style',Path(__file__).with_name('n810-radio-style.py'))
style=module_from_spec(_style_spec);_style_spec.loader.exec_module(style)

_model_spec=spec_from_file_location('services_model',Path(__file__).with_name('n810-services-model.py'))
model=module_from_spec(_model_spec);_model_spec.loader.exec_module(model)

PACKET=model.PACKET
FREQUENCY=model.FREQUENCY


hints=model.hints


message=model.message


State=model.State


def put(win, y, text, attr=0):
    h,w = win.getmaxyx()
    if 0 <= y < h:
        try: win.addnstr(y,0,str(text),max(0,w-1),attr)
        except curses.error: pass


POSITION=model.POSITION


readable=model.readable


details=model.details


summary=model.summary



def tabs(win, selected):
    _, width = win.getmaxyx()
    labels = ('s Services', 't Stations', 'm Messages') if width >= 46 else ('s Svc', 't Stations', 'm Msg')
    x = 0
    for index, label in enumerate(labels):
        active = index == selected
        edge, face = style.tab_styles(active)
        size = len(label) + 2
        for y, text, attr in ((1, '┌'+'─'*size+'┐', edge),
                              (2, '│ '+label+' │', face),
                              (3, '└'+'─'*size+'┘', edge)):
            try: win.addnstr(y,x,text,max(0,min(len(text),width-x-1)),attr)
            except curses.error: pass
        x += size + 3


def at(win,y,x,text,width,attr=0):
    h,w=win.getmaxyx()
    if 0<=y<h and 0<=x<w:
        try: win.addnstr(y,x,str(text),max(0,min(width,w-x-1)),attr)
        except curses.error: pass


def panel(win,y,x,height,width,title):
    if height<3 or width<4: return
    at(win,y,x,'┌'+'─'*(width-2)+'┐',width)
    at(win,y,x+2,' '+title+' ',width-4,curses.A_BOLD)
    for row in range(y+1,y+height-1):
        at(win,row,x,'│',1);at(win,row,x+width-1,'│',1)
    at(win,y+height-1,x,'└'+'─'*(width-2)+'┘',width)


fields=model.fields


def draw(win, state, tab, selected, expanded=False, raw_only=False, detail_scroll=0):
    h,w=win.getmaxyx();win.erase()
    at(win,0,1,'APRS SERVICES',w-2,curses.A_BOLD)
    at(win,0,max(17,w-25),state.call+'  ·  Receive only',24)
    tabs(win,tab)
    # Transport counters belong to the feed window; keep this status concise.
    status=state.status
    if 'Listening' in status or status.startswith('UV-PRO connected'): status='Radio connected · waiting for packets'
    at(win,4,1,status,w-2)
    if h<18 or w<48:
        at(win,7,1,'Use at least 48 columns × 18 rows.',w-2);return
    rows=state.rows(tab);selected=min(selected,max(0,len(rows)-1))
    top=6;raw_y=h-7;body_h=raw_y-top-1
    expanded=expanded or body_h<9
    split_view=w>=90 and not expanded and not raw_only
    left_w=max(32,min(44,w//3))
    if not expanded and not raw_only:
        list_h=body_h if split_view else max(5,body_h//2)
        list_w=left_w if split_view else w-2
        panel(win,top,1,list_h,list_w,('Advertisements','Heard stations','Observed messages')[tab])
        count=max(1,(list_h-2)//3);first=max(0,selected-count+1)
        for i,row in enumerate(rows[first:first+count],first):
            y=top+1+(i-first)*3;active=i==selected
            attr=style.selection() if active else curses.A_NORMAL
            who=row['call'] if tab==2 else row['entity']
            title=who[:max(1,list_w-15)].ljust(max(1,list_w-15))+' '+row['time']
            text=('To '+row['to']+' · ' if tab==2 else '')+summary(row)
            at(win,y,3,title.ljust(list_w-4),list_w-4,attr)
            if y+1<top+list_h-1:at(win,y+1,3,text.ljust(list_w-4),list_w-4,attr)
        if not rows:at(win,top+2,3,'Nothing received yet.',list_w-4)
    else:list_h=0
    dx=left_w+3 if split_view else 1
    dy=top if split_view or expanded or raw_only else top+list_h+1
    dw=w-dx-1;dh=raw_y-dy-1
    panel(win,dy,dx,dh,dw,'Raw packet' if raw_only else 'Selected packet')
    if rows:
        row=rows[selected];content=[]
        label_w=13 if dw>=40 else 10
        if raw_only:
            content=[('',row['raw'][i:i+dw-5]) for i in range(0,len(row['raw']),dw-5)]
        else:
            for label,value in fields(row):
                parts=textwrap.wrap(value,max(8,dw-label_w-6),replace_whitespace=False) or ['']
                content.append((label,parts[0]));content.extend(('',part) for part in parts[1:])
                content.append(('',''))
        available=max(1,dh-2);offset=min(detail_scroll,max(0,len(content)-available))
        for y,(label,value) in enumerate(content[offset:offset+available],dy+1):
            at(win,y,dx+2,label,label_w,style.label())
            at(win,y,dx+2+(label_w+1 if not raw_only else 0),value,dw-label_w-5 if not raw_only else dw-5,style.accent() if label in ('Station','Frequency','To') else curses.A_NORMAL)
        if len(content)>available:at(win,dy+dh-1,dx+2,' u/d scroll · v expand ',dw-4)
        panel(win,raw_y,1,5,w-2,'Original packet · r for full raw view')
        raw=row['raw'];width=w-6
        for i in range(3):at(win,raw_y+1+i,3,raw[i*width:(i+1)*width],width)
    else:
        at(win,dy+2,dx+3,'Select a received packet to inspect.',dw-6)
    at(win,h-1,1,'s/t/m tabs   j/k select   v expand   r raw   g nets   q quit',w-2)


def run(win, args):
    style.init_screen(win)
    try: curses.curs_set(0)
    except curses.error: pass
    win.timeout(250)
    state=State(args.call); tab=0; selected=0; connection=None
    expanded=False; raw_only=False; detail_scroll=0
    pending=b''; retry_at=0; dirty=True; size=None
    try:
        while True:
            if connection is None and time.monotonic() >= retry_at:
                candidate=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); candidate.settimeout(.2)
                try: candidate.connect(args.socket)
                except OSError:
                    candidate.close(); retry_at=time.monotonic()+2
                    state.status='Feed unavailable; retrying (viewer only)'
                else:
                    connection=candidate; connection.setblocking(False); pending=b''
                    state.status='Connected to feed; loading replay'
                dirty=True
            if connection:
                try: data=connection.recv(8192)
                except BlockingIOError: data=None
                except OSError: data=b''
                if data == b'':
                    connection.close(); connection=None; pending=b''; retry_at=time.monotonic()+2
                    state.status='Feed disconnected; waiting to reconnect'; dirty=True
                elif data:
                    pending+=data
                    while b'\n' in pending:
                        line,pending=pending.split(b'\n',1)
                        state.add(line.decode('utf-8','replace'))
                    if len(pending)>65536: pending=b''
                    dirty=True
            if dirty or size != win.getmaxyx():
                selected=min(selected,max(0,len(state.rows(tab))-1))
                draw(win,state,tab,selected,expanded,raw_only,detail_scroll);win.refresh();dirty=False;size=win.getmaxyx()
            key=win.getch()
            if key==ord('g'):
                spec=spec_from_file_location('ui_window',Path(__file__).with_name('n810-ui-window.py'))
                helper=module_from_spec(spec);spec.loader.exec_module(helper)
                try:helper.open_window('Nets')
                except (OSError,RuntimeError) as exc:state.status=str(exc)
                continue
            if key in (ord('q'),27): break
            if key in (ord('1'),ord('2'),ord('3'),ord('s'),ord('t'),ord('m')):
                tab = {ord('1'):0,ord('2'):1,ord('3'):2,ord('s'):0,ord('t'):1,ord('m'):2}[key]
                selected=0;detail_scroll=0;dirty=True
            elif key in (curses.KEY_LEFT,ord('h'),curses.KEY_RIGHT,ord('l'),9):
                tab=(tab + (-1 if key in (curses.KEY_LEFT,ord('h')) else 1)) % 3
                selected=0;detail_scroll=0;dirty=True
            elif key == ord('v'):
                expanded=not expanded; detail_scroll=0; dirty=True
            elif key == ord('r'):
                raw_only=not raw_only; detail_scroll=0; dirty=True
            elif key in (ord('u'),ord('d'),ord('['),ord(']')):
                detail_scroll=max(0,detail_scroll+(-3 if key in (ord('u'),ord('[')) else 3)); dirty=True
            elif key in (curses.KEY_DOWN,ord('j')):
                selected=min(selected+1,max(0,len(state.rows(tab))-1));detail_scroll=0;dirty=True
            elif key in (curses.KEY_UP,ord('k')):
                selected=max(0,selected-1);detail_scroll=0;dirty=True
    finally:
        if connection: connection.close()


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--socket',default='/dev/shm/n810-aprs.sock')
    parser.add_argument('--call',default='N0DEM')
    curses.wrapper(run,parser.parse_args())
