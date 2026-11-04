"""Incremental bounded terminal input decoding (SGR cell-coordinate mouse)."""
import re

MOUSE = re.compile(rb'\x1b\[<(\d{1,3});(\d{1,5});(\d{1,5})([Mm])')
PHONE_KEYS={b'\x1b[18~':'wm-menu',b'\x1b[19~':'wm-windows',b'\x1b[20~':'wm-close',b'\x1b[21~':'wm-maximize',b'\x1b[24~':'wm-next'}
SS3_KEYS={b'\x1bOA':'up',b'\x1bOB':'down',b'\x1bOC':'right',b'\x1bOD':'left',b'\x1bOP':'help',b'\x1bOH':'home',b'\x1bOF':'end'}

WM_ESCAPES={'ctrl-]':'\x1d','ctrl-backslash':'\x1c','ctrl-^':'\x1e','ctrl-_':'\x1f'}


class Input:
    def __init__(self,passthrough=False,phone_keys=False,extended_keys=False):
        self.pending = b''
        self.passthrough=passthrough
        self.phone_keys=phone_keys
        self.extended_keys=extended_keys

    def feed(self, data, expire=False):
        self.pending += data
        events = []
        while self.pending:
            if self.pending.startswith(b'\x1b[<'):
                match = MOUSE.match(self.pending)
                if match:
                    button, x, y = map(int, match.group(1, 2, 3))
                    events.append(('mouse', button, x-1, y-1, match[4] == b'm'))
                    self.pending = self.pending[match.end():]
                    continue
                if not expire and len(self.pending) < 40:
                    break
                self.pending = self.pending[3:]
                continue
            if self.pending[:3] in SS3_KEYS:
                name=SS3_KEYS[self.pending[:3]]
                events.append(('terminal_key',name,'press',0,None,self.pending[:3].hex()) if self.extended_keys and name in ('up','down','left','right') else ('key',name))
                self.pending=self.pending[3:]
                continue
            if self.pending.startswith(b'\x1b['):
                # Full CSI grammar is bounded and incremental, including colon
                # subparameters used by explicit press/repeat/release events.
                report=re.match(rb'\x1b\[([?]?[0-9:;]*)([A-Za-z~])',self.pending)
                if report:
                    params,final=report.groups();raw=report[0]
                    if final==b'u' and params.startswith(b'?'):
                        if params[1:].isdigit():events.append(('keyboard_flags',int(params[1:])))
                        self.pending=self.pending[len(raw):];continue
                    if final==b'c' and params.startswith(b'?'):
                        self.pending=self.pending[len(raw):];continue
                    if not params and final in (b'I',b'O'):
                        events.append(('focus',final==b'I'));self.pending=self.pending[len(raw):];continue
                    if final==b'u' or self.extended_keys and final in (b'A',b'B',b'C',b'D') or b':' in params and final in (b'A',b'B',b'C',b'D',b'H',b'F',b'P',b'Q',b'R',b'S',b'~'):
                        from terminal_keys import FUNCTIONAL
                        fields=params.split(b';');key=None;kind='press';mods=0
                        try:
                            code=int(fields[0].split(b':')[0] or b'1')
                            modifiers=fields[1].split(b':') if len(fields)>1 else [b'1']
                            mods=int(modifiers[0] or b'1')-1
                            phase=int(modifiers[1]) if len(modifiers)>1 else 1
                            kind={1:'press',2:'repeat',3:'release'}[phase]
                            if final==b'u':
                                key=FUNCTIONAL.get(code)
                                if key is None and 0<=code<=0x10ffff and not 0xd800<=code<=0xdfff and not 57344<=code<=63743:key=chr(code)
                            elif final==b'~':
                                key={15:'f5',17:'f6'}.get(code)
                                if key is None and self.phone_keys:key={18:'wm-menu',19:'wm-windows',20:'wm-close',21:'wm-maximize',24:'wm-next'}.get(code)
                            else:key={b'A':'up',b'B':'down',b'C':'right',b'D':'left',b'H':'home',b'F':'end',b'P':'help'}.get(final)
                            if key is not None and 0<=mods<=255:
                                event=('terminal_key',key,kind,mods)
                                if len(fields)>2 and fields[2]:
                                    codes=[int(v) for v in fields[2].split(b':')]
                                    if len(codes)<=32 and all(32<=v<=0x10ffff and not 0xd800<=v<=0xdfff for v in codes):event+=( ''.join(map(chr,codes)), )
                                if key in ('w','a','s','d','i','k','left','right','up','down'):
                                    if len(event)==4:event+=(None,)
                                    event+=(raw.hex(),)
                                events.append(event)
                        except (ValueError,KeyError):pass
                        self.pending=self.pending[len(raw):];continue
            if self.pending.startswith(b'\x1b'):
                if not expire and (len(self.pending) == 1 or b'\x1b[<'.startswith(self.pending) or any(seq.startswith(self.pending) for seq in SS3_KEYS)):
                    break
                if self.pending.startswith(b'\x1b['):
                    match = re.match(rb'\x1b\[[0-9;]*[A-Za-z~]', self.pending)
                    if match:
                        keys = {b'\x1b[21;2~':'context-menu',b'\x1b[15~':'f5',b'\x1b[17~':'f6',b'\x1b[17;2~':'shift-f6',b'\x1b[A':'up',b'\x1b[B':'down',b'\x1b[C':'right',b'\x1b[D':'left',b'\x1b[11~':'help',b'\x1b[Z':'backtab', b'\x1b[1;5D':'desktop-left', b'\x1b[1;5C':'desktop-right'}
                        keys.update({b'\x1b[H':'home',b'\x1b[F':'end',b'\x1b[1~':'home',b'\x1b[4~':'end',
                                     b'\x1b[7~':'home',b'\x1b[8~':'end',b'\x1b[5~':'pageup',b'\x1b[6~':'pagedown'})
                        name = PHONE_KEYS.get(match[0]) if self.phone_keys else None
                        if name is None:name = keys.get(match[0])
                        if name: events.append(('key',name))
                        elif self.passthrough:events.append(('key',match[0].decode('ascii')))
                        self.pending = self.pending[match.end():]
                        continue
                    if not expire and len(self.pending) < 32: break
                events.append(('key', '\x1b'))
                self.pending = self.pending[1:]
                continue
            if self.passthrough and self.pending[0]>=128:
                count=2 if 0xc2<=self.pending[0]<=0xdf else 3 if 0xe0<=self.pending[0]<=0xef else 4 if 0xf0<=self.pending[0]<=0xf4 else 1
                if len(self.pending)<count and not expire:break
                part=self.pending[:count]
                try:char=part.decode('utf-8')
                except UnicodeError:char='�';count=1
                events.append(('key',char));self.pending=self.pending[count:];continue
            events.append(('key', chr(self.pending[0])))
            self.pending = self.pending[1:]
        return events


def phone_action(key,host,launcher,open_menu):
    """Handle explicit phone window actions before app capture; no desktop quit."""
    if key not in PHONE_KEYS.values():return False
    if host.screensaver:
        host.screensaver=False;host.set_effect(host.screensaver_effect)
    if host.help_lines:host.toggle_help()
    launcher.active=False
    host.finish(False)
    if key=='wm-menu':
        if host.overview:host.toggle_overview()
        open_menu()
    elif key=='wm-windows':host.toggle_overview()
    elif key=='wm-next':host.cycle_focus()
    else:
        name=host.overview_selection if host.overview else host.focus
        if name and host.window(name).opened:
            (host.close if key=='wm-close' else host.maximize)(name)
    return True
