#!/usr/bin/env python3
"""Read-only browser for downloaded radio configuration snapshots."""
import curses
import json
import importlib.util
from pathlib import Path

ROOT=Path('~/.local/state/n810-radio/backups').expanduser()


def latest(root=ROOT):
    for path in sorted(Path(root).glob('*/backup.json'),reverse=True):
        try:
            data=json.loads(path.read_text())
            if data.get('complete') and ('restore_bank' not in data or data.get('restored')):return path,data
        except (OSError,ValueError):pass
    return None,None


def tone(value):
    if not value:return 'Off'
    return 'DCS %d'%value if value<6700 else '%.1f Hz'%(value/100)


def channel_details(row):
    p=row.get('decoded')
    if not p:return [('Read result',str(row.get('response',{}).get('status')))]
    power='High' if p['tx_at_max_power'] else 'Medium' if p['tx_at_med_power'] else 'Low'
    return [('Name',p['name_str']),('Index',str(row['index'])),
            ('RX','%.6f MHz'%(p['rx_freq']/1e6)),('TX','%.6f MHz'%(p['tx_freq']/1e6)),
            ('Offset','%+.3f MHz'%((p['tx_freq']-p['rx_freq'])/1e6)),
            ('RX tone',tone(p['rx_sub_audio'])),('TX tone',tone(p['tx_sub_audio'])),
            ('RX mode',{0:'FM',1:'AM',2:'DMR'}.get(p['rx_mod'],str(p['rx_mod']))),
            ('Bandwidth','Wide' if p['bandwidth'] else 'Narrow'),('Power',power),
            ('Transmit','Disabled' if p['tx_disable'] else 'Enabled'),
            ('Scan','On' if p['scan'] else 'Off'),('Mute','On' if p['mute'] else 'Off'),
            ('Talk around','On' if p['talk_around'] else 'Off'),
            ('De/emph bypass','On' if p['pre_de_emph_bypass'] else 'Off')]


def sections(data,tab):
    if tab==1:
        settings=data.get('settings',{})
        return [(key.replace('_',' '),str(value)) for key,value in settings.items() if not key.startswith('_')]
    if tab==2:
        return [(key.replace('_',' '),str(value)) for key,value in data.get('beacon',{}).items() if not key.startswith('_')]
    return [(name,'status '+str(row.get('status'))+' / '+str(row.get('reply_hex'))) for name,row in data.get('reads',{}).items()]


def draw(win,data,tab,bi,ci,focus,scroll,path):
    h,w=win.getmaxyx();win.erase()
    def put(y,x,text,attr=0,width=None):
        if 0<=y<h and x<w-1:
            try:win.addnstr(y,x,str(text),min(width or w,w-x-1),attr)
            except curses.error:pass
    put(0,1,'RADIO / ON RADIO',curses.A_BOLD)
    put(1,1,'Downloaded '+data.get('finished',data.get('started',''))+' / read only')
    settings=data.get('settings',{});status=data.get('status',{});device=data.get('device',{})
    active=status.get('curr_region');bank=next((b for b in data['banks'] if b['index']==active),{})
    a=(settings.get('channel_a_upper',0)<<4)|settings.get('channel_a_lower',0)
    b=(settings.get('channel_b_upper',0)<<4)|settings.get('channel_b_lower',0)
    encoded=(settings.get('auto_share_loc_ch_upper',0)<<5)|settings.get('auto_share_loc_ch',0)
    digital=str(encoded-1) if encoded else 'current'
    put(2,1,'At download: %s / A %d / B %d / digital %s / KISS %s / firmware %s'%(
        bank.get('name',str(active)),a,b,digital,'On' if settings.get('kiss_en') else 'Off',device.get('soft_ver','?')))
    x=1
    for i,name in enumerate(['Banks','Settings','APRS','Raw replies']):
        title='%d %s  '%(i+1,name);put(3,x,title,curses.A_REVERSE if i==tab else 0);x+=len(title)
    if tab==0:
        a=max(20,w//5);b=max(a+26,w//2);banks=sorted(data['banks'],key=lambda bank:bank['index'])
        put(5,1,('> ' if focus==0 else '  ')+'BANKS',curses.A_BOLD)
        put(5,a,('> ' if focus==1 else '  ')+'CHANNELS',curses.A_BOLD)
        put(5,b,'CHANNEL',curses.A_BOLD)
        for i,bank in enumerate(banks):put(7+i,1,'%d %s'%(bank['index'],bank['name']),curses.A_REVERSE if bi==i else 0,a-2)
        if banks:
            rows=banks[bi]['channels'];visible=max(1,h-10);start=max(0,ci-visible+1)
            for y,(i,row) in enumerate(list(enumerate(rows))[start:start+visible],7):
                p=row.get('decoded',{});label=p.get('name_str','Read failed')
                put(y,a,'%02d %-10s %s'%(row['index'],label,'%.3f'%(p['rx_freq']/1e6) if 'rx_freq' in p else ''),curses.A_REVERSE if ci==i else 0,b-a-2)
            if rows:
                for y,(label,value) in enumerate(channel_details(rows[ci]),7):put(y,b,'%-16s %s'%(label,value))
    else:
        rows=sections(data,tab)
        for y,(label,value) in enumerate(rows[scroll:scroll+max(1,h-9)],6):
            put(y,1,'%-30s %s'%(label,value))
    put(h-1,1,'1 banks  2 settings  3 APRS  4 raw  Arrows select  p saved presets  d services  r reload  q close')
    win.refresh()


def run(win,path=None,data=None):
    if data is None:path,data=latest()
    if data is None:return 'profiles'
    win.keypad(True);win.timeout(200);curses.curs_set(0)
    tab=bi=ci=focus=scroll=0;dirty=True;size=None
    while True:
        banks=sorted(data['banks'],key=lambda bank:bank['index']);bi=max(0,min(bi,len(banks)-1))
        rows=banks[bi]['channels'] if banks else [];ci=max(0,min(ci,len(rows)-1))
        if dirty or size!=win.getmaxyx():draw(win,data,tab,bi,ci,focus,scroll,path);dirty=False;size=win.getmaxyx()
        key=win.getch()
        if key==-1:continue
        dirty=True
        if key in (ord('q'),27):return 'close'
        if key==ord('p'):return 'profiles'
        if key==ord('d'):
            spec=importlib.util.spec_from_file_location('ui_window',Path(__file__).with_name('n810-ui-window.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            module.open_window('Services Directory')
        if ord('1')<=key<=ord('4'):tab=key-ord('1');scroll=0
        elif key==ord('r'):
            new_path,new_data=latest()
            if new_data:path,data=new_path,new_data
        elif key in (curses.KEY_LEFT,curses.KEY_RIGHT):focus=0 if key==curses.KEY_LEFT else 1
        elif key in (10,13,curses.KEY_ENTER) and tab==0:focus=1-focus
        elif key in (curses.KEY_UP,curses.KEY_DOWN,ord('j'),ord('k')):
            delta=1 if key in (curses.KEY_DOWN,ord('j')) else -1
            if tab!=0:scroll=max(0,min(max(0,len(sections(data,tab))-1),scroll+delta))
            elif focus==0:bi=max(0,min(len(banks)-1,bi+delta));ci=0
            else:ci=max(0,min(len(rows)-1,ci+delta))

if __name__=='__main__':curses.wrapper(run)
