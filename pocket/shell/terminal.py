"""Terminal character-grid geometry."""
from collections import namedtuple
import fcntl
import os
import struct
import termios

Geometry = namedtuple('Geometry', 'columns rows')


def console_wake():
    """Poke Linux VT blanking on entry/input, including direct evdev touch.

    This is the console's existing unblank command, not a blank-timer change.
    Direct evdev reads bypass the keyboard path that normally does this.
    """
    return '\x1b[13]' if os.environ.get('TERM') == 'linux' else ''


def measure(fd):
    try:columns,rows=max(1,int(os.environ.get('COLUMNS') or 80)),max(1,int(os.environ.get('LINES') or 24))
    except ValueError:columns,rows=80,24
    try:
        r,c,_,_ = struct.unpack('HHHH', fcntl.ioctl(fd, termios.TIOCGWINSZ, bytes(8)))
        if r and c: rows,columns = r,c
    except (OSError, ValueError):
        pass
    return Geometry(columns,rows)


class Presentation:
    """Hold multi-batch damage behind DEC synchronized output when supported."""
    begin='\x1b[?2026h'
    end='\x1b[?2026l'
    def __init__(self):
        self.opened=False;self.started=0;self.buffer=[];self.queued_since=None
        self.queued_chars=0;self.max_queued_chars=0;self.last_urgent_debt_chars=0;self.max_urgent_debt_chars=0
    def write(self,output,complete,now,max_hold=.35,atomic=False,urgent=False):
        if atomic or self.buffer:
            if urgent:
                self.last_urgent_debt_chars=self.queued_chars
                self.max_urgent_debt_chars=max(self.max_urgent_debt_chars,self.queued_chars)
            if output:
                if self.queued_since is None:self.queued_since=now
                self.buffer.append(output)
                self.queued_chars+=len(output);self.max_queued_chars=max(self.max_queued_chars,self.queued_chars)
            expired=self.queued_since is not None and now-self.queued_since>=max_hold
            if not complete and not urgent and not expired:return ''
            output=''.join(self.buffer);self.buffer.clear();self.queued_since=None;self.queued_chars=0
        prefix=suffix=''
        if output and not self.opened:
            prefix=self.begin;self.opened=True;self.started=now
        if self.opened and (complete or urgent or now-self.started>=max_hold):
            suffix=self.end;self.opened=False
        return prefix+output+suffix
    def close(self):
        self.buffer.clear();self.queued_since=None;self.queued_chars=0
        output=self.end if self.opened else ''
        self.opened=False
        return output

    def stats(self):
        return dict(buffered_chars=self.queued_chars,max_buffered_chars=self.max_queued_chars,
                    last_urgent_debt_chars=self.last_urgent_debt_chars,max_urgent_debt_chars=self.max_urgent_debt_chars)
