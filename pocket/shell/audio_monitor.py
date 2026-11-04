"""Read-only, bounded local PCM subscription and native console monitor."""
import errno
import os
from pathlib import Path
import textwrap
import json
import select
import socket
import time
from audio_metrics import AudioMetrics
from app_widgets import Canvas,TextInput


DEFAULT_SOCKET='/tmp/n810-audio-trial/pcm.sock'

def default_socket():return os.environ.get('N810_AUDIO_SOCKET') or DEFAULT_SOCKET


class PCMSource:
    """Main-loop polling: no worker, outbound requests, replay queue, or codec."""
    def __init__(self,path=None,metrics=None,clock=time.monotonic):
        self.path=str(path) if path else None;self.metrics=metrics or AudioMetrics();self.clock=clock
        self.closed=False;self.socket=None;self.connecting=False;self.buffer=bytearray();self.retry=0.;self.error='Waiting for shared audio service' if self.path else 'No audio source configured';self.playback=None
    def disconnect(self,reason):
        if self.socket:self.socket.close()
        self.socket=None;self.buffer.clear();self.connecting=False;self.retry=self.clock()+2;self.error=reason
        self.metrics.feed(dict(type='status',state='disconnected'))
        if self.playback:self.playback.stop()
    def configure(self,path):
        path=str(Path(path).expanduser()) if path else None
        if path and (not Path(path).is_absolute() or '\0' in path or len(os.fsencode(path))>100):raise ValueError('Use an absolute local socket path (100 bytes maximum)')
        self.disconnect('Waiting for shared audio service' if path else 'No audio source configured')
        self.path=path;self.closed=False;self.retry=0.;self.metrics.format=None;self.metrics.clear_segment('Waiting for PCM')
    def poll(self):
        if self.closed:return
        if self.playback:self.playback.poll()
        if not self.path:return
        try:
            if self.socket is None:
                if self.clock()<self.retry:return
                self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.socket.setblocking(False)
                result=self.socket.connect_ex(self.path)
                if result not in (0,errno.EINPROGRESS,errno.EAGAIN):raise OSError(result,'Audio socket unavailable')
                self.connecting=result!=0;self.error='Connecting'
            if self.connecting:
                if not select.select([], [self.socket], [], 0)[1]:return
                result=self.socket.getsockopt(socket.SOL_SOCKET,socket.SO_ERROR)
                if result:raise OSError(result,'Audio connect failed')
                self.connecting=False
            # At most 64 KiB per desktop iteration; partial JSON line <=32 KiB.
            budget=65536
            while budget>0:
                try:chunk=self.socket.recv(min(16384,budget))
                except BlockingIOError:break
                if not chunk:raise ConnectionError('Audio source closed')
                budget-=len(chunk);self.buffer.extend(chunk)
                while b'\n' in self.buffer:
                    line,_,rest=self.buffer.partition(b'\n');self.buffer=bytearray(rest)
                    if len(line)>32768:raise ValueError('Audio event exceeds bound')
                    event=json.loads(line)
                    if not isinstance(event,dict):raise ValueError('Audio event must be an object')
                    raw=self.metrics.feed(event)
                    if self.playback:
                        if event.get('type') in ('gap','format'):self.playback.stop()
                        if raw:self.playback.write(raw,self.metrics.format)
                    self.error=''
                if len(self.buffer)>32768:raise ValueError('Unterminated audio event exceeds bound')
        except (OSError,ValueError,TypeError,UnicodeError) as error:
            reason='Waiting for shared audio service' if isinstance(error,OSError) and error.errno in (errno.ENOENT,errno.ECONNREFUSED) else str(error)[:160]
            self.disconnect(reason)
    def close(self):self.closed=True;self.disconnect('Closed')


class AudioMonitor:
    def __init__(self,path=None,provider=None):
        self.explicit_source=path is not None;self.active=True;self.editing=False;self.input=TextInput('',limit=100);self.notice=''
        self.source=PCMSource(path if path is not None else provider if provider is not None else default_socket());self.metrics=self.source.metrics;self.width=80;self.height=26;self._spans=();self._cache=None;self._cache_key=None;self._buttons=[]
        from audio_playback import Playback
        self.source.playback=Playback();self.playback=self.source.playback
    def set_active(self,active):
        if self.active and not active:self.source.disconnect('Audio Monitor closed');self.dismiss()
        if active and not self.active:self.source.retry=0
        self.active=active
    def poll_interval(self):return (.02 if self.source.socket else .25) if self.active and self.source.path else .05 if self.playback.build else None
    def poll(self):
        if self.active:self.source.poll()
        else:self.playback.poll()
    def bind_session(self,callback):self._session_callback=callback
    def _session_changed(self):
        callback=getattr(self,'_session_callback',None)
        if callback:callback()
    def session_state(self):return dict(audio_socket=self.source.path,refresh=self.metrics.fps)
    def restore_session(self,state):
        if not isinstance(state,dict):return
        path=state.get('audio_socket')
        if not self.explicit_source and 'audio_socket' in state and (path is None or isinstance(path,str)):
            try:self.source.configure(path)
            except ValueError:pass
        fps=state.get('refresh')
        if type(fps)==int and 1<=fps<=10:self.metrics.fps=fps
    def configure_source(self,path):
        previous=self.source.path
        try:self.source.configure(path)
        except ValueError as error:self.notice=str(error);return False
        self.dismiss();self.notice=''
        if self.source.path!=previous:self._session_changed()
        return True
    def dismiss(self):
        self.playback.enabled=False;self.playback.stop();self.playback.status='off' if self.playback.available else 'unavailable on this host'
    def close(self):self.active=False;self.source.close();self.playback.close()
    def key(self,key):
        if self.editing:
            if key=='\x1b':self.editing=False;self.notice='';return True
            if key in ('\r','\n'):
                if self.configure_source(self.input.text.strip()):self.editing=False
                return True
            if key=='\x15':self.input=TextInput('',limit=100);return True
            return self.input.key(key)
        if key=='s':self.input=TextInput(self.source.path or '',limit=100);self.editing=True;self.notice='';return True
        if key=='r':return self.configure_source(self.source.path)
        if key=='p':self.playback.toggle();return True
        if key=='c' and self.metrics.format:self.metrics.set_channel((self.metrics.channel+1)%self.metrics.format['channels']);return True
        if key in ('+','=','-'):
            previous=self.metrics.fps
            self.metrics.fps=max(1,min(10,self.metrics.fps+(1 if key!='-' else -1)))
            if self.metrics.fps!=previous:self._session_changed()
            return True
        return False
    def pointer(self,column,row,width,button=0,released=False):
        if self.editing:return False
        if button==0 and not released and row==2:
            for start,end,key in self._buttons:
                if start<=column<end:return self.key(key)
        return False
    def lines(self):
        s=self.metrics.snapshot();fmt=s['format'] or {};channel=s['channel'];w,h=self.width,self.height
        # No raster work between metric updates unless status/layout changes.
        key=(w,h,self.metrics.last_snapshot,s['state'],s['gaps'],s['reason'],self.source.error,self.playback.status,self.metrics.fps,channel,self.source.path,self.editing,self.input.text,self.input.cursor,self.notice)
        if key==self._cache_key:return self._cache
        c=Canvas(w,h);c.pane(0,0,w,h,'Audio Monitor · receive',True)
        c.put(1,1,s['state']+' · '+(str(fmt['sample_rate'])+' Hz / '+str(fmt['channels'])+' ch / S16LE' if fmt else 'Waiting for declared PCM format'))
        c.role(1,1,w-2,'status' if s['state']=='Receiving' else 'muted')
        self._buttons=[];x=1
        for label,action in (('[s Source]','s'),('[r Retry]','r'),('[p Playback: '+self.playback.status+']','p')):
            c.put(x,2,label);c.role(x,2,min(w-x,len(label)),'control');self._buttons.append((x,x+len(label),action));x+=len(label)+1
        if self.editing or s['state']!='Receiving':
            c.put(1,4,'Source socket');c.role(1,4,w-2,'heading')
            source=self.input.draw(max(1,w-2)) if self.editing else self.source.path or 'No source selected'
            parts=[source] if self.editing else textwrap.wrap(source,max(1,w-2))
            for y,line in enumerate(parts[:3],5):c.put(1,y,line)
            if self.editing:c.role(1,5,w-2,'input')
            y=min(h-3,5+len(parts)+1)
            c.put(1,y,self.notice or ('Enter attach · Esc cancel · Ctrl-U clear' if self.editing else self.source.error or s['reason']));c.role(1,y,w-2,'warning' if self.notice else 'muted')
            if not self.editing:c.put(1,min(h-2,y+2),'Levels and plots appear when PCM arrives.');c.role(1,min(h-2,y+2),w-2,'muted')
            c.put(1,h-1,'s source · r retry · p playback (off until enabled)');c.role(1,h-1,w-2,'control')
            self._spans=c.styled_spans();self._cache=c.lines();self._cache_key=key;return self._cache
        rms=s.get('rms_dbfs',());peak=s.get('peak_dbfs',());clips=s.get('full_scale_samples',())
        if rms and s['state']=='Receiving':
            size=max(1,min(36,w-24));filled=round(max(0,min(1,(rms[channel]+60)/60))*size)
            c.put(1,4,'RMS  ['+'━'*filled+'·'*(size-filled)+'] '+f'{rms[channel]:.1f} dBFS')
            c.put(1,5,f'Peak {peak[channel]:.1f} dBFS · full-scale samples {clips[channel]}');c.role(1,5,w-2,'warning' if clips[channel] else 'muted')
        else:c.put(1,4,'No current PCM levels');c.role(1,4,w-2,'muted')
        c.put(1,7,'Spectrum / amplitude dBFS · '+str(fmt.get('sample_rate',0)//2)+' Hz →');c.role(1,7,w-2,'muted')
        bands=s.get('spectrum_dbfs',()) if s['state']=='Receiving' else ()
        width=max(1,w-2);sh=max(1,min(5,h//5))
        for x in range(width):
            if not bands:break
            lo=x*len(bands)//width;hi=max(lo+1,(x+1)*len(bands)//width)
            value=max(bands[lo:hi]);count=round(max(0,min(1,(value+90)/90))*sh)
            for y in range(count):c.put(1+x,8+sh-1-y,'▂' if y==count-1 else '│');c.role(1+x,8+sh-1-y,1,'accent')
        top=9+sh;bottom=max(top,h-4);c.put(1,top,'Waterfall · channel '+str(channel+1));c.role(1,top,w-2,'muted')
        history=s['waterfall'][-max(0,bottom-top-1):]
        glyphs=' ·:░▒▓'
        for y,row in enumerate(history):
            for x in range(width):
                lo=x*len(row)//width;hi=max(lo+1,(x+1)*len(row)//width);value=max(row[lo:hi])
                c.put(x+1,top+1+y,glyphs[min(len(glyphs)-1,value*len(glyphs)//256)])
            c.role(1,top+1+y,w-2,'accent')
        c.put(1,h-3,'Gaps '+str(s['gaps'])+' · '+(self.source.error or s['reason']));c.role(1,h-3,w-2,'muted')
        c.put(1,h-2,'Audio levels ≠ RSSI · capture time unknown · no recording');c.role(1,h-2,w-2,'muted')
        c.put(1,h-1,f'p playback · c channel · +/- refresh {self.metrics.fps} Hz');c.role(1,h-1,w-2,'control')
        self._spans=c.styled_spans();self._cache=c.lines();self._cache_key=key;return self._cache
    def spans(self):return self._spans
