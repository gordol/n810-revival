#!/usr/bin/env python3
"""Radio profile editor. Saved drafts only; never opens Bluetooth or a TX socket."""
import argparse
import importlib.util
import curses
import json
from pathlib import Path

_spec=importlib.util.spec_from_file_location('radio_profiles',Path(__file__).with_name('n810-radio-profiles.py'))
_profiles=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_profiles)
STORE=_profiles.STORE
FIELDS=_profiles.FIELDS
defaults=_profiles.defaults
validate=_profiles.validate
load=_profiles.load
save=_profiles.save
edit_profile=_profiles.edit_profile


def render(win,profiles,selected,field,focus,notice,editing,dirty,help_open):
    h,w=win.getmaxyx();win.erase();split=min(29,max(19,w//4))
    def put(y,x,text,attr=0):
        if 0<=y<h and x<w-1:
            try:win.addnstr(y,x,str(text),w-x-1,attr)
            except curses.error:pass
    put(0,1,'RADIO',curses.A_BOLD);put(1,1,'RADIO / SAVED PRESETS'+(' *' if dirty else ''))
    put(3,1,('> ' if focus=='profiles' else '  ')+'PROFILES',curses.A_BOLD)
    names=list(profiles)
    for i,name in enumerate(names):put(5+i*2,2,name,curses.A_REVERSE if i==selected else 0)
    put(3,split,('> ' if focus=='fields' else '  ')+names[selected],curses.A_BOLD)
    put(4,split,'Radio: not synchronized')
    for i,(key,label) in enumerate(FIELDS):
        value=profiles[names[selected]][key]
        text=('On' if value else 'Off') if isinstance(value,bool) else ('Off' if value is None else ('%.3f'%value if key.endswith('mhz') else str(value)))
        if i==field and editing is not None:text=editing+'_'
        put(6+i,split,'%-22s %s'%(label,text),curses.A_REVERSE if focus=='fields' and i==field else 0)
    if notice:put(h-3,1,notice)
    put(h-1,1,'Up/down select  Left/right panel  Enter edit  v on radio  c saved banks  r services  s save  ? help  q back')
    if help_open:
        win.erase()
        lines=['RADIO / HELP','','Saved presets are local drafts for programming the radio.',
               'Saving changes only the profile file. No radio commands are issued.',
               'Live apply/readback will use the shared radio owner when available.',
               '', 'c opens the saved radio-bank manager; p returns to profiles.', 'Left/right: choose profiles or fields. Up/down: select.',
               'Enter: toggle on/off, or edit a number. Enter accepts; Esc cancels.',
               'CTCSS: enter off to clear. Frequencies are MHz; tones are Hz.',
               'Memory indices are zero-based. KISS port numbers are separate.',
               'Voice Alert test starts with RX tone only; TX tone stays off.',
               'Bluetooth audio fields are requested settings; streaming is not connected.',
               '', 's saves all profile drafts. q returns to On radio. Unsaved edits prompt before leaving.',
               '? closes help.']
        for y,line in enumerate(lines):put(y,1,line)
    win.refresh()


def run(win,args):
    curses.curs_set(0);win.keypad(True);win.timeout(200)
    profiles=load(args.store);selected=field=0;focus='profiles';editing=None;notice='';dirty=False;help_open=False;quit_pending=False;redraw=True
    while True:
        if redraw:render(win,profiles,selected,field,focus,notice,editing,dirty,help_open);redraw=False
        key=win.getch()
        if key==-1:continue
        redraw=True
        if key==curses.KEY_RESIZE:continue
        if editing is not None:
            if key==27:editing=None;continue
            if key in (10,13,curses.KEY_ENTER):
                try:profiles=edit_profile(profiles,list(profiles)[selected],{FIELDS[field][0]:editing});dirty=True;editing=None;notice=''
                except ValueError as exc:notice=str(exc)
            elif key in (curses.KEY_BACKSPACE,127,8):editing=editing[:-1]
            elif 32<=key<127 and len(editing)<16:editing+=chr(key)
            continue
        if key==ord('?'):help_open=not help_open;continue
        if help_open:continue
        if key in (ord('q'),ord('v')):
            if not dirty or quit_pending:return 'radio'
            quit_pending=True;notice='Unsaved draft: s save, q discard and go back, any other key returns';continue
        quit_pending=False
        if key==ord('r'):
            spec=importlib.util.spec_from_file_location('ui_window',Path(__file__).with_name('n810-ui-window.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            try:module.open_window('Repeaters')
            except (OSError,RuntimeError) as exc:notice=str(exc)
        elif key==ord('c'):
            spec=importlib.util.spec_from_file_location('radio_banks',Path(__file__).with_name('n810-radio-banks.py'))
            banks=importlib.util.module_from_spec(spec);spec.loader.exec_module(banks)
            try:banks.run(win,args.store.with_name('banks.json'))
            except ValueError as exc:notice=str(exc)
        elif key==ord('s'):
            try:save(args.store,profiles);dirty=False;notice='Drafts saved'
            except OSError as exc:notice='Save failed: '+str(exc)
        elif key in (curses.KEY_LEFT,curses.KEY_RIGHT,9):focus='profiles' if key==curses.KEY_LEFT else 'fields' if key==curses.KEY_RIGHT else ('fields' if focus=='profiles' else 'profiles')
        elif key in (curses.KEY_DOWN,curses.KEY_UP,ord('j'),ord('k')):
            delta=1 if key in (curses.KEY_DOWN,ord('j')) else -1
            if focus=='profiles':selected=(selected+delta)%len(profiles)
            else:field=(field+delta)%len(FIELDS)
        elif key in (10,13,curses.KEY_ENTER):
            if focus=='profiles':focus='fields';continue
            name=list(profiles)[selected];keyname=FIELDS[field][0];value=profiles[name][keyname]
            if keyname=='digital_channel':notice='Digital memory is fixed at 0';continue
            if isinstance(value,bool):profiles=edit_profile(profiles,name,{keyname:not value});dirty=True
            else:editing=''


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--store',type=Path,default=STORE)
    p.add_argument('--profiles',action='store_true',help='Open local drafts instead of downloaded settings')
    p.add_argument('--json',action='store_true',help='Print saved profile drafts')
    p.add_argument('--import-csv',type=Path,help='Import a CSV as a new local bank')
    p.add_argument('--bank-name',default='Imported bank')
    p.add_argument('--export-bank',help='Print one named local bank as CSV')
    p.add_argument('--banks-json',action='store_true',help='Print the local bank library')
    args=p.parse_args()
    if args.import_csv or args.export_bank or args.banks_json:
        spec=importlib.util.spec_from_file_location('radio_banks',Path(__file__).with_name('n810-radio-banks.py'))
        banks=importlib.util.module_from_spec(spec);spec.loader.exec_module(banks)
        path=args.store.with_name('banks.json');data=banks.load(path)
        if args.import_csv:
            bank=banks.import_csv(data,args.import_csv.read_text(),args.bank_name);banks.save(path,data)
            print('Imported %d channels into %s'%(len(bank['channels']),bank['name']))
        elif args.export_bank:
            matches=[b for b in data['banks'] if b['name']==args.export_bank]
            if len(matches)!=1:p.error('Bank name must match exactly one local bank')
            print(banks.export_csv(matches[0]),end='')
        else:print(json.dumps(data))
    elif args.json:print(json.dumps(load(args.store)))
    else:
        spec=importlib.util.spec_from_file_location('radio_readback',Path(__file__).with_name('n810-radio-readback.py'))
        readback=importlib.util.module_from_spec(spec);spec.loader.exec_module(readback)
        def interface(win):
            path,data=readback.latest()
            view='profiles' if args.profiles or data is None else 'radio'
            while True:
                if view=='profiles':
                    run(win,args)
                    path,data=readback.latest()
                    if data is None:return
                    view='radio'
                else:
                    view=readback.run(win,path,data)
                    if view!='profiles':return
        curses.wrapper(interface)

if __name__=='__main__':main()
