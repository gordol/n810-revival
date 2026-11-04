#!/usr/bin/env python3
"""Local channel-bank library and D-pad editor. No radio connection."""
import importlib.util
import curses
from pathlib import Path
import time

_spec=importlib.util.spec_from_file_location('radio_library',Path(__file__).with_name('n810-radio-library.py'))
_library=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_library)
STORE=_library.STORE
FIELDS=_library.FIELDS
CATEGORIES=_library.CATEGORIES
channel=_library.channel
core_bank=_library.core_bank
ensure_core=_library.ensure_core
validate=_library.validate
load=_library.load
save=_library.save
import_csv=_library.import_csv
export_csv=_library.export_csv
edit=_library.edit


def text(value):
    if value is None:return 'Off'
    if isinstance(value,bool):return 'On' if value else 'Off'
    if isinstance(value,float):return '%.3f'%value
    return str(value)


def render(win,data,bi,ci,fi,focus,notice,editing,dirty):
    h,w=win.getmaxyx();win.erase();bx=max(18,w//5);cx=max(bx+25,w//2)
    def put(y,x,value,attr=0,limit=None):
        if 0<=y<h and x<w-1:
            try:win.addnstr(y,x,str(value),min(w-x-1,limit or w),attr)
            except curses.error:pass
    put(0,1,'RADIO / SAVED BANKS',curses.A_BOLD);put(1,1,'Local presets / not uploaded'+(' *' if dirty else ''))
    for x,title,index in [(1,'BANKS',0),(bx,'CHANNELS',1),(cx,'CHANNEL',2)]:put(3,x,('> ' if focus==index else '  ')+title,curses.A_BOLD)
    banks=data['banks'];visible=max(1,h-9)
    start=max(0,bi-visible+1)
    for y,(i,bank) in enumerate(list(enumerate(banks))[start:start+visible],5):
        put(y,1,bank['name'],curses.A_REVERSE if i==bi else 0,bx-2)
    rows=banks[bi]['channels'] if banks else []
    start=max(0,ci-visible+1)
    for y,(i,row) in enumerate(list(enumerate(rows))[start:start+visible],5):
        put(y,bx,('%d '%row['hardware_slot'] if 'hardware_slot' in row else '')+'%s  %.3f'%(row['name'],row['rx_mhz']),curses.A_REVERSE if i==ci else 0,cx-bx-2)
    if rows:
        row=rows[ci]
        for y,(i,(key,label)) in enumerate(enumerate(FIELDS),5):
            value=editing[1]+'_' if editing and editing[0]==key else text(row[key])
            put(y,cx,'%-15s %s'%(label,value),curses.A_REVERSE if focus==2 and i==fi else 0)
        if 'hardware_slot' in row:put(18,cx,'Reserved slot   '+str(row['hardware_slot']))
        put(16,cx,'Offset          %+.3f MHz'%(row['tx_mhz']-row['rx_mhz']))
    elif banks:put(5,bx,'a add channel')
    else:put(5,1,'n new bank')
    if editing and editing[0] in ('new_bank','rename_bank'):put(h-4,1,'Bank name: '+editing[1]+'_')
    if notice:put(h-3,1,notice)
    put(h-1,1,'Arrows navigate  Enter edit  n bank  a channel  N rename  c copy  d delete  r services  s save  p profiles')
    win.refresh()


def run(win,path):
    try:data=load(path)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        # Never silently overwrite an unreadable library.
        raise ValueError('Cannot open bank library: '+str(exc)) from exc
    bi=ci=fi=focus=0;notice='';editing=None;dirty=False;redraw=True;pending_delete=None;delete_time=0;quit_pending=False
    while True:
        banks=data['banks'];bi=max(0,min(bi,len(banks)-1));rows=banks[bi]['channels'] if banks else [];ci=max(0,min(ci,len(rows)-1))
        if redraw:render(win,data,bi,ci,fi,focus,notice,editing,dirty);redraw=False
        key=win.getch()
        if key==-1:continue
        redraw=True
        if key==curses.KEY_RESIZE:continue
        if editing:
            kind,value=editing
            if key==27:editing=None;notice='';continue
            if key in (10,13,curses.KEY_ENTER):
                try:
                    if kind=='new_bank':data=edit(data,'add_bank',name=value);bi=len(data['banks'])-1;ci=0
                    elif kind=='rename_bank':data=edit(data,'rename_bank',bank_id=banks[bi]['id'],name=value)
                    else:data=edit(data,'update_channel',bank_id=banks[bi]['id'],channel_id=rows[ci]['id'],changes={kind:value})
                    editing=None;dirty=True;notice=''
                except ValueError as exc:notice=str(exc)
            elif key in (8,127,curses.KEY_BACKSPACE):editing=(kind,value[:-1])
            elif 32<=key<127 and len(value)<48:editing=(kind,value+chr(key))
            continue
        if key in (ord('p'),ord('q'),27):
            if not dirty or quit_pending:return
            quit_pending=True;notice='Unsaved library: s save, p again discard';continue
        quit_pending=False
        target=('bank',banks[bi]['id']) if banks and focus==0 else ('channel',rows[ci]['id']) if rows else None
        if key==ord('d') and banks and banks[bi]['id']=='core':
            notice='Core slots 0 / 1 / 2 are reserved';continue
        if key==ord('d') and target:
            if pending_delete==target and time.monotonic()-delete_time<3:
                if target[0]=='bank':data=edit(data,'delete_bank',bank_id=banks[bi]['id'])
                else:data=edit(data,'delete_channel',bank_id=banks[bi]['id'],channel_id=rows[ci]['id'])
                dirty=True;pending_delete=None;notice='Deleted from local library'
            else:pending_delete=target;delete_time=time.monotonic();notice='Press d again to delete selected '+target[0]
            continue
        pending_delete=None
        if key==ord('r'):
            spec=importlib.util.spec_from_file_location('ui_window',Path(__file__).with_name('n810-ui-window.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            try:module.open_window('Repeaters')
            except (OSError,RuntimeError) as exc:notice=str(exc)
        elif key==ord('s'):
            try:save(path,data);dirty=False;notice='Library saved'
            except OSError as exc:notice='Save failed: '+str(exc)
        elif key==ord('n'):editing=('new_bank','');notice=''
        elif key==ord('N') and banks and banks[bi]['id']!='core':editing=('rename_bank',banks[bi]['name']);notice=''
        elif key==ord('a') and banks and banks[bi]['id']!='core':
            bank_id=banks[bi]['id'];data=edit(data,'add_channel',bank_id=bank_id);ci=len(data['banks'][bi]['channels'])-1;focus=2;fi=0;dirty=True
        elif key==ord('c') and banks:
            data=edit(data,'copy_bank',bank_id=banks[bi]['id']);bi=len(data['banks'])-1;ci=0;focus=0;dirty=True
        elif key in (curses.KEY_LEFT,curses.KEY_RIGHT,9):focus=max(0,focus-1) if key==curses.KEY_LEFT else min(2,focus+1) if key==curses.KEY_RIGHT else (focus+1)%3
        elif key in (curses.KEY_UP,curses.KEY_DOWN,ord('j'),ord('k')):
            delta=1 if key in (curses.KEY_DOWN,ord('j')) else -1
            if focus==0:bi=max(0,min(len(banks)-1,bi+delta));ci=0
            elif focus==1:ci=max(0,min(len(rows)-1,ci+delta))
            else:fi=(fi+delta)%len(FIELDS)
        elif key in (10,13,curses.KEY_ENTER):
            if focus<2:focus+=1
            elif rows:
                field=FIELDS[fi][0];value=rows[ci][field]
                if isinstance(value,bool):data=edit(data,'update_channel',bank_id=banks[bi]['id'],channel_id=rows[ci]['id'],changes={field:not value});dirty=True
                elif field in ('power','bandwidth'):
                    choices=('Low','Medium','High') if field=='power' else ('Narrow','Wide')
                    data=edit(data,'update_channel',bank_id=banks[bi]['id'],channel_id=rows[ci]['id'],changes={field:choices[(choices.index(value)+1)%len(choices)]});dirty=True
                else:editing=(field,'' if value is None else str(value))
