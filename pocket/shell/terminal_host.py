"""Opt-in PTY child window. One bounded terminal screen, no scrollback/threads.

pyte parses terminal commands; this adapter bounds sequence size and output per
wake, provides alternate-screen storage and connects cells to the existing Host.
"""
import codecs
import errno
import fcntl
import os
import re
from pathlib import Path
import selectors
import signal
import struct
import subprocess
import sys
import termios
import time
from functools import lru_cache

sys.path.insert(0,str(Path(__file__).parent/'vendor/terminal'))
import pyte
from cell_text import RICH
from paint import ink

CSI_PARAMETERS=re.compile(r'[0-9;]*\Z')

PALETTE=dict(zip(('black','red','green','brown','blue','magenta','cyan','white'),
                 ((0,0,0),(205,0,0),(0,205,0),(205,205,0),(0,0,238),(205,0,205),(0,205,205),(229,229,229))))
PALETTE.update(dict(zip(('brightblack','brightred','brightgreen','brightbrown','brightblue','brightmagenta','brightcyan','brightwhite'),
                       ((127,127,127),(255,0,0),(0,255,0),(255,255,0),(92,92,255),(255,0,255),(0,255,255),(255,255,255)))))

PALETTE_INDEX={name:index for index,name in enumerate(PALETTE)}


def shell_argv():
    """Use a shell executable, never evaluate the environment value as a command."""
    shell=os.environ.get('SHELL','/bin/sh')
    if not os.path.isabs(shell) or not os.path.isfile(shell) or not os.access(shell,os.X_OK):shell='/bin/sh'
    return [shell,'-i']


@lru_cache(maxsize=2048)
def color(attr):
    def rgb(name,default):
        if name=='default':return default
        if name.startswith('index:'):name=pyte.graphics.FG_BG_256[int(name[6:])]
        if name in PALETTE:return PALETTE[name]
        try:return tuple(bytes.fromhex(name)) if len(name)==6 else default
        except ValueError:return default
    fg=rgb(attr.fg,(229,229,229));bg=rgb(attr.bg,(0,0,0))
    if attr.bold and attr.fg in PALETTE and not attr.fg.startswith('bright'):fg=PALETTE.get('bright'+attr.fg,fg)
    if attr.reverse:fg,bg=bg,fg
    return ink(*fg,background=bg)


class Screen(pyte.Screen):
    def __init__(self,width,height,reply):
        self.reply=reply;self.primary=None;self.palette={}
        self._colors=lru_cache(maxsize=2048)(self._color)
        super().__init__(width,height)
    def write_process_input(self,data):self.reply(data.encode('utf-8'))
    def _color(self,attr):
        fg=attr.fg
        if attr.bold and fg in PALETTE and not fg.startswith('bright'):fg='bright'+fg
        def resolve(name):
            if name.startswith('index:'):
                index=int(name[6:]);return self.palette.get(index,pyte.graphics.FG_BG_256[index])
            index=PALETTE_INDEX.get(name)
            return self.palette.get(index,name)
        return color(attr._replace(fg=resolve(fg),bg=resolve(attr.bg),bold=False))
    def color(self,attr):return self._colors(attr) if self.palette else color(attr)
    def select_graphic_rendition(self,*attrs):
        # Retain index identity so later palette changes recolor retained cells.
        indexed={};i=0
        while i<len(attrs):
            a=attrs[i];i+=1
            if a==0:indexed.clear()
            elif a in (38,48):
                key='fg' if a==38 else 'bg';indexed.pop(key,None)
                if i<len(attrs) and attrs[i]==5:
                    if i+1<len(attrs) and 0<=attrs[i+1]<256:indexed[key]='index:'+str(attrs[i+1])
                    i+=2
                elif i<len(attrs) and attrs[i]==2:i+=4
            elif 30<=a<=37 or a==39 or 90<=a<=97:indexed.pop('fg',None)
            elif 40<=a<=47 or a==49 or 100<=a<=107:indexed.pop('bg',None)
        super().select_graphic_rendition(*attrs)
        if indexed:self.cursor.attrs=self.cursor.attrs._replace(**indexed)
    def osc(self,text):
        parts=text.split(';');operation=parts.pop(0)
        try:
            if operation=='4':
                if not parts or len(parts)%2:return
                values={}
                for slot,spec in zip(parts[::2],parts[1::2]):
                    index=int(slot)
                    if not 0<=index<256:return
                    if re.fullmatch(r'#[0-9a-fA-F]{6}',spec):value=spec[1:].lower()
                    elif re.fullmatch(r'rgb:[0-9a-fA-F]{1,4}/[0-9a-fA-F]{1,4}/[0-9a-fA-F]{1,4}',spec):
                        value=''.join(f'{round(int(c,16)*255/(16**len(c)-1)):02x}' for c in spec[4:].split('/'))
                    else:return
                    values[index]=value
                if all(self.palette.get(k)==v for k,v in values.items()):return
                self.palette.update(values)
            elif operation=='104':
                slots=[int(slot) for slot in parts if slot]
                if any(not 0<=slot<256 for slot in slots):return
                if slots:
                    for slot in slots:self.palette.pop(slot,None)
                else:self.palette.clear()
            else:return
        except ValueError:return
        self._colors.cache_clear();self.dirty.update(range(self.lines))
    def report_device_status(self,mode=0,*extra,private=False):
        if extra:return
        if not private:return super().report_device_status(mode)
        # DEC private cursor-position request. Other private status queries are
        # unsupported; ignore them rather than inventing a successful response.
        if mode==6:
            y=self.cursor.y+1
            if pyte.modes.DECOM in self.mode and self.margins is not None:y-=self.margins.top
            self.write_process_input(f'\x1b[?{y};{min(self.cursor.x,self.columns-1)+1}R')
    def save_cursor(self):
        # VT has a saved cursor register, not an unbounded application stack.
        self.savepoints.clear();super().save_cursor()
    def set_mode(self,*modes,**kwargs):
        # Host owns content dimensions; ignore DECCOLM's requested 80/132 columns.
        if kwargs.get('private'):modes=tuple(m for m in modes if m!=3)
        if kwargs.get('private') and any(m in (47,1047,1049) for m in modes) and self.primary is None:
            saved=self.__dict__.copy();super().__init__(self.columns,self.lines);self.primary=saved
        super().set_mode(*modes,**kwargs)
    def reset_mode(self,*modes,**kwargs):
        if kwargs.get('private'):modes=tuple(m for m in modes if m!=3)
        if kwargs.get('private') and any(m in (47,1047,1049) for m in modes) and self.primary is not None:
            width,height=self.columns,self.lines;saved=self.primary
            self.__dict__.clear();self.__dict__.update(saved)
            self.resize(lines=height,columns=width);self.dirty.update(range(height))
        super().reset_mode(*modes,**kwargs)


class Parser:
    """No unbounded OSC strings/CSI arrays can reach the upstream parser."""
    def __init__(self,screen):
        self.screen=screen;self.stream=pyte.Stream(screen);self.stream.use_utf8=False
        # UTF-8 decoding stays here; enable VT G0/G1/ACS switching in pyte.
        self.decoder=codecs.getincrementaldecoder('utf-8')('replace')
        self.state='normal';self.sequence='';self.dropped=0
    def csi(self):
        sequence=self.sequence;parameters=sequence[2:-1] if sequence.startswith('\x1b[') else sequence[1:-1]
        if parameters.startswith('?'):
            # pyte applies private=True to any final byte, including handlers
            # which do not accept it. Admit only implemented DEC operations.
            if sequence[-1] not in 'hlJKnc':self.dropped+=1;return
            parameters=parameters[1:]
        # Unsupported secondary/keyboard/intermediate extensions must not be
        # misinterpreted as ordinary SGR/cursor commands by the upstream parser.
        if not CSI_PARAMETERS.fullmatch(parameters):self.dropped+=1;return
        self.stream.feed(sequence)
    def feed(self,data):
        text=self.decoder.decode(data);plain=[]
        def flush():
            if plain:self.stream.feed(''.join(plain));plain.clear()
        for ch in text:
            if self.state=='normal':
                if ch in ('\x1b','\x9b','\x9d','\x90','\x9e','\x9f'):
                    flush();self.sequence='' if ch=='\x9d' else ch
                    self.state={'\x1b':'escape','\x9b':'csi','\x9d':'osc','\x90':'discard','\x9e':'discard','\x9f':'discard'}[ch]
                else:plain.append(ch)
            elif self.state=='osc':
                if ch in ('\x07','\x9c'):
                    self.screen.osc(self.sequence);self.sequence='';self.state='normal'
                elif ch=='\x1b':self.state='osc_escape'
                else:
                    self.sequence+=ch
                    if len(self.sequence)>4096:self.sequence='';self.state='discard';self.dropped+=1
            elif self.state=='osc_escape':
                if ch=='\\':self.screen.osc(self.sequence);self.sequence='';self.state='normal'
                else:self.sequence='';self.state='discard'
            elif self.state=='discard':
                if ch in ('\x07','\x9c'):self.state='normal'
                elif ch=='\x1b':self.state='discard_escape'
            elif self.state=='discard_escape':self.state='normal' if ch=='\\' else 'discard'
            elif self.state=='escape':
                self.sequence+=ch
                if ch=='[':self.state='csi'
                elif ch==']':self.state='osc';self.sequence=''
                elif ch in 'P^_':self.state='discard';self.sequence=''
                elif ch in '()%#':self.state='third'
                else:self.stream.feed(self.sequence);self.sequence='';self.state='normal'
            elif self.state=='third':
                self.stream.feed(self.sequence+ch);self.sequence='';self.state='normal'
            elif self.state in ('csi','csi_discard'):
                if self.state=='csi':
                    self.sequence+=ch
                    if len(self.sequence)>1024:self.sequence='';self.state='csi_discard';self.dropped+=1
                if '@'<=ch<='~':
                    if self.state=='csi':self.csi()
                    self.sequence='';self.state='normal'
        flush()


class Terminal:
    MAX_INPUT=16384
    def __init__(self,host,name,argv,selector,env=None,cwd=None,metrics=None,show_cursor=False,blend_background=False):
        self.host,self.name,self.selector=host,name,selector
        self.argv=tuple(argv);self.environment={"POCKET_THEME":getattr(host,"palette","ice"),**(env or {})};self.cwd=cwd;self.metrics=metrics
        self.show_cursor=show_cursor;self.cursor_cell=None
        self.blend_background=blend_background
        self.fd=None;self.child=None;self.pending=bytearray();self.closed=False;self.eof=False
        self.received=0;self.patched=0;self.error=None;self.cells=[];self.size=None
        self.ready_calls=0;self.max_ready_ms=0
        w=host.window(name);width,height=max(1,w.w-2),max(1,w.h-2)
        if not argv or any(not isinstance(a,str) for a in argv):raise ValueError('explicit argv required')
        if width*height>262144:raise ValueError('terminal surface exceeds cell limit')
        master,slave=os.openpty()
        try:
            fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',height,width,0,0))
            child_env=dict(os.environ);child_env.update(TERM='xterm-256color',COLORTERM='truecolor',LANG='C.UTF-8')
            child_env.update(self.environment)
            # Exec bootstrap runs after Popen's safe session setup, no preexec_fn
            # in the threaded parent. One persistent process: the actual app.
            bootstrap='import fcntl,os,sys,termios;fcntl.ioctl(0,termios.TIOCSCTTY,0);os.execvpe(sys.argv[1],sys.argv[1:],os.environ)'
            self.child=subprocess.Popen([sys.executable,'-c',bootstrap,*argv],stdin=slave,stdout=slave,stderr=slave,env=child_env,cwd=cwd,start_new_session=True,close_fds=True)
            os.set_blocking(master,False);self.fd=master
            self.screen=Screen(width,height,self.send);self.parser=Parser(self.screen)
            self.resize();selector.register(master,selectors.EVENT_READ,self)
            host.window_cleanup[name]=self.close
            if blend_background:host.terminal_layers.add(name)
        except BaseException:
            if self.fd is None:os.close(master)
            if self.child is not None:self.close()
            raise
        finally:os.close(slave)
    def interest(self):
        if self.fd is not None and not self.eof:
            try:self.selector.modify(self.fd,selectors.EVENT_READ|(selectors.EVENT_WRITE if self.pending else 0),self)
            except KeyError:pass
    def send(self,data):
        if self.closed or self.eof:return False
        if len(self.pending)+len(data)>self.MAX_INPUT:self.error='input queue full';return False
        self.pending.extend(data);self.interest();return True
    def key(self,key):
        arrows={'up':'A','down':'B','right':'C','left':'D','home':'H','end':'F'}
        if key in arrows:key='\x1b'+('O' if 1<<5 in self.screen.mode else '[')+arrows[key]
        else:key={'context-menu':'\x1b[21;2~','f5':'\x1b[15~','help':'\x1bOP','pageup':'\x1b[5~','pagedown':'\x1b[6~','delete':'\x1b[3~','backtab':'\x1b[Z','backspace':'\x7f','desktop-left':'\x1b[1;5D','desktop-right':'\x1b[1;5C'}.get(key,key)
        return self.send(key.encode('utf-8'))
    def pointer(self,button,x,y,released):
        modes=self.screen.mode
        if not ((1000<<5 in modes or 1002<<5 in modes or 1003<<5 in modes) and 1006<<5 in modes):return False
        if button&32 and not (1002<<5 in modes or 1003<<5 in modes):return False
        return self.send(f'\x1b[<{button};{x+1};{y+1}{"m" if released else "M"}'.encode())
    def resize(self):
        w=self.host.window(self.name);width,height=max(1,w.w-2),max(1,w.h-2)
        if width*height>262144:raise ValueError('terminal surface exceeds cell limit')
        if self.size==(width,height):return False
        self.size=width,height;self.screen.resize(lines=height,columns=width)
        self.cursor_cell=None
        self.screen.dirty.update(range(height))
        self.cells=[(' ',ink(229,229,229,background=(0,0,0)))]*(width*height)
        self.host.layer_patch(self.name,(0,0,width,height,self.cells),None)
        if self.fd is not None:
            fcntl.ioctl(self.fd,termios.TIOCSWINSZ,struct.pack('HHHH',height,width,0,0))
            try:os.killpg(self.child.pid,signal.SIGWINCH)
            except ProcessLookupError:pass
        return True
    def present(self):
        cursor=self.screen.cursor
        position=cursor.y*self.size[0]+min(cursor.x,self.size[0]-1) if self.show_cursor and not cursor.hidden else None
        if not self.screen.dirty and position==self.cursor_cell:return 0
        if self.metrics:return self.metrics.call('pty_convert_dirty_rows',self._present,position)
        return self._present(position)
    def _present(self,position):
        width,height=self.size;changed=[]
        extra={i for i in (self.cursor_cell,position) if i is not None and i//width not in self.screen.dirty}
        if self.metrics:
            self.metrics.add('pty_dirty_rows',len(self.screen.dirty))
            self.metrics.add('pty_cells_scanned',len(self.screen.dirty)*width+len(extra))
        for y in sorted(self.screen.dirty):
            if not 0<=y<height:continue
            row=self.screen.buffer[y]
            for x in range(width):
                attr=row[x];text=attr.data;index=y*width+x;shade=self.screen.color(attr)
                if index==position:shade=(1<<48)|((shade&0xffffff)<<24)|((shade>>24)&0xffffff)
                # Preserve pyte's wide trailing blank and cell coordinates.
                value=(RICH.cell(text) if text else ' ',shade)
                if value!=self.cells[index]:self.cells[index]=value;changed.append(index)
        for index in extra:
            attr=self.screen.buffer[index//width][index%width];shade=self.screen.color(attr)
            if index==position:shade=(1<<48)|((shade&0xffffff)<<24)|((shade>>24)&0xffffff)
            value=(RICH.cell(attr.data) if attr.data else ' ',shade)
            if value!=self.cells[index]:self.cells[index]=value;changed.append(index)
        self.cursor_cell=position
        self.screen.dirty.clear();self.patched+=len(changed)
        if self.metrics:self.metrics.add('pty_patched_cells',len(changed))
        if changed:self.host.layer_patch(self.name,(0,0,width,height,self.cells),changed)
        return len(changed)
    def ready(self,mask,byte_budget=8192,time_budget=.004):
        started=time.monotonic();read=0
        try:
            if mask&selectors.EVENT_WRITE and self.pending:
                try:count=os.write(self.fd,self.pending[:4096]);del self.pending[:count]
                except BlockingIOError:pass
            if mask&selectors.EVENT_READ:
                while read<byte_budget:
                    try:
                        if self.metrics:data=self.metrics.call('pty_read',os.read,self.fd,min(2048,byte_budget-read))
                        else:data=os.read(self.fd,min(2048,byte_budget-read))
                    except BlockingIOError:break
                    except OSError as error:
                        if error.errno==errno.EIO:data=b''
                        else:raise
                    if not data:self.finish_read();break
                    read+=len(data);self.received+=len(data)
                    if self.metrics:self.metrics.add('pty_received_bytes',len(data))
                    if self.metrics:self.metrics.call('pty_parse',self.parser.feed,data)
                    else:self.parser.feed(data)
                    if time.monotonic()-started>=time_budget:break
        except OSError as error:self.error=str(error);self.finish_read()
        self.interest();self.present();self.ready_calls+=1
        self.max_ready_ms=max(self.max_ready_ms,(time.monotonic()-started)*1000)
        return read
    def finish_read(self):
        self.eof=True;self.pending.clear()
        if self.fd is not None:
            try:self.selector.unregister(self.fd)
            except KeyError:pass
            os.close(self.fd);self.fd=None
        self.child.poll()
    def close(self):
        if self.closed:return
        self.closed=True
        if self.fd is not None:self.finish_read()
        if self.child is not None:
            # Group may outlive its leader: terminate descendants as well.
            self.signal_group(signal.SIGTERM)
            try:self.child.wait(timeout=.25)
            except subprocess.TimeoutExpired:
                self.signal_group(signal.SIGKILL)
                try:self.child.wait(timeout=.25)
                except subprocess.TimeoutExpired:self.error='child did not exit after kill'
            self.signal_group(signal.SIGKILL)
        if self.host.window_cleanup.get(self.name)==self.close:
            self.host.window_cleanup.pop(self.name,None);self.host.terminal_layers.discard(self.name)
        w=self.host.window(self.name)
        if w.layer is not None and w.layer[4] is self.cells:
            w.layer=None;self.host.invalidate(w.rect)
        self.cells=[]
        if hasattr(self,'screen'):
            self.screen.buffer.clear();self.screen.primary=None
            self.screen._colors.cache_clear();self.screen.palette.clear()
    def signal_group(self,sig):
        try:os.killpg(self.child.pid,sig)
        except ProcessLookupError:pass
        except OSError as error:
            # An exited group can return EPERM in a sandbox. Cleanup failure
            # must never prevent restoring the parent's physical terminal.
            if self.child.poll() is None:
                self.error='process group signal: '+str(error)
                try:self.child.send_signal(sig)
                except OSError as direct:self.error='child signal: '+str(direct)
