"""Negotiated Kitty key edges; ordinary applications retain legacy key input."""
from types import SimpleNamespace
from keyboard_runtime import KeyboardRouter
from evdev_keys import MOTION_KEYS

MOTION=set(MOTION_KEYS.values())
FUNCTIONAL={27:'\x1b',13:'\r',9:'\t',127:'\x7f',57350:'left',57351:'right',57352:'up',57353:'down',57356:'home',57357:'end',57354:'pageup',57355:'pagedown',57364:'help',57368:'f5',57369:'f6'}

FUNCTIONAL.update({57364+n-1:'f'+str(n) for n in range(13,18)})

def legacy(key,mods=0):
    # Lock bits do not modify shortcuts. Kitty modifier values are mask + 1.
    mods &= 63
    if key in ('left','right') and mods==4:return 'desktop-'+key
    if key=='\t' and mods==1:return 'backtab'
    if key=='f6' and mods==1:return 'shift-f6'
    if len(key)==1:
        if mods&4:
            upper=key.upper()
            code=ord(upper) if len(upper)==1 else -1
            if 64<=code<=95:key=chr(code-64)
            elif key==' ':key='\0'
        elif mods&1:key=key.upper()
    if mods==2 and key in ('\t','\r','m','o'):
        return {'\t':'alt-tab','\r':'alt-enter','m':'alt-m','o':'alt-o'}[key]
    if mods&2:key='\x1b'+key
    return key

class TerminalKeys:
    def __init__(self,clock,enabled=True):
        self.clock=clock;self.enabled=enabled;self.pushed=False;self.confirmed=False;self.focused=True;self.received_flags=None;self.last_motion=None;self.requested=False
        self.source=SimpleNamespace(device={'motion_codes':list(MOTION_KEYS)},decoder=SimpleNamespace(modifiers=()),close=lambda:None)
        self.router=KeyboardRouter(self.source,clock,lambda:self.confirmed and self.focused)
    def start(self):return '\x1b[?u\x1b[c\x1b[?1004h' if self.enabled else ''
    def flags(self,value):
        if not self.enabled:return ''
        self.received_flags=value
        if not self.requested:
            self.requested=True;self.pushed=True
            return '\x1b[>27u\x1b[?u'
        self.confirmed=self.pushed and value&27==27
        if not self.confirmed:
            self.router.cancel()
            if self.pushed:
                self.pushed=False
                return '\x1b[<u'
        return ''
    def select(self,form):self.router.select(form)
    def cancel(self):self.router.cancel()
    def event(self,event):
        """Return normal key tuple, or None for consumed edge/protocol events."""
        if event[0]=='focus':
            self.focused=event[1]
            if not self.focused:self.cancel()
            return None
        if event[0]!='terminal_key':return event
        # Queued edges cannot become legacy app input while the terminal is unfocused.
        if not self.focused:return None
        _,key,kind,mods=event[:4]
        text=event[4] if len(event)>4 else None
        mods &= 63
        if key in MOTION:self.last_motion=dict(key=key,kind=kind,modifiers=mods,encoding=event[5] if len(event)>5 else None)
        self.source.decoder.modifiers=bool(mods)
        if mods:self.cancel()
        if key in MOTION and not mods and self.confirmed and self.router.target is not None:
            self.router.event(('key_event',key,kind));return None
        if kind=='release':return None
        if text and not mods&62:return ('key',text)
        return ('key',legacy(key,mods)) if key else None
    def status(self):
        return dict(enabled=self.enabled,pushed=self.pushed,confirmed=self.confirmed,focused=self.focused,received_flags=self.received_flags,last_motion=self.last_motion,router=self.router.status())
    def close(self):
        self.cancel()
        value=('\x1b[<u' if self.pushed else '')+('\x1b[?1004l' if self.enabled else '')
        self.pushed=False;self.confirmed=False
        return value
