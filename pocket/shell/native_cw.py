"""Explicit, bounded offline WAV decoding using the existing CW reference model."""
import importlib.util
from pathlib import Path
import stat
import sys
import textwrap
import wave
from threading import Event, Lock
from concurrent.futures import ThreadPoolExecutor
from app_widgets import AdaptivePanels, PanelSpec, Canvas, SelectList, TextInput

MAX_BYTES=1024*1024
MAX_FRAMES=240000
MAX_SECONDS=30


def load_decoder():
    here=Path(__file__).resolve().parent
    roots=(here/'vendor/apps/cw-reference',)
    root=next((p for p in roots if (p/'decode.py').is_file() and (p/'reference.py').is_file()),None)
    if root is None:raise ImportError('Offline CW reference is not bundled')
    spec=importlib.util.spec_from_file_location('pocket_cw_reference',root/'reference.py')
    reference=importlib.util.module_from_spec(spec);sys.modules[spec.name]=reference;spec.loader.exec_module(reference)
    previous=sys.modules.get('reference');sys.modules['reference']=reference
    try:
        spec=importlib.util.spec_from_file_location('pocket_cw_decode',root/'decode.py')
        decoder=importlib.util.module_from_spec(spec);spec.loader.exec_module(decoder)
    finally:
        if previous is None:sys.modules.pop('reference',None)
        else:sys.modules['reference']=previous
    return decoder


def decode_file(path,decoder,tone=700,wpm=20,*,cancelled=None,progress=None):
    """Validate metadata, then stream through the owner's bounded decoder."""
    path=Path(path).expanduser()
    info=path.stat()
    if not stat.S_ISREG(info.st_mode):raise ValueError('Choose a regular WAV file')
    if info.st_size>MAX_BYTES:raise ValueError('WAV exceeds 1 MiB offline preview limit')
    with wave.open(str(path),'rb') as audio:
        if audio.getnchannels()!=1 or audio.getsampwidth()!=2 or audio.getcomptype()!='NONE':
            raise ValueError('Uncompressed mono 16-bit PCM WAV required')
        rate=audio.getframerate();frames=audio.getnframes()
        if rate<=0 or rate>48000 or frames>MAX_FRAMES or frames/rate>MAX_SECONDS:
            raise ValueError('Preview limit: 30 seconds, 240000 samples, up to 48000 Hz')
    text=decoder.decode_wav(path,tone=tone,wpm=wpm,cancelled=cancelled,progress=progress,
                            max_seconds=MAX_SECONDS,max_frames=MAX_FRAMES,max_bytes=MAX_BYTES)
    return dict(path=str(path),rate=rate,frames=frames,seconds=frames/rate,tone=tone,wpm=wpm,text=text)


class CW:
    def __init__(self,decoder=None):
        self.decoder=decoder or load_decoder();self.width=84;self.height=26
        self.path=TextInput(limit=1024);self.tone=TextInput('700',limit=8);self.wpm=TextInput('20',limit=5)
        self.fields=SelectList(('WAV path','Tone Hz','Speed WPM','Decode file'))
        self.layout=AdaptivePanels((PanelSpec('file','File',30,38),PanelSpec('result','Decoded text',30,54)))
        self.result=None;self.error=None;self.status='Choose a WAV, then Decode';self.scroll=0
        self._cancel=Event();self._progress_lock=Lock();self._progress=None;self._shown_progress=None
        self._progress_percent=None;self._wakeup=None
        self._executor=None;self._future=None;self._closed=False;self._rects={};self._spans=[];self._hits=[]
    def bind_wakeup(self,callback):
        """Attach the desktop's existing inbox; progress only posts readiness."""
        if callback is not None and not callable(callback):raise TypeError('wakeup must be callable')
        with self._progress_lock:self._wakeup=callback if not self._closed else None
    def decode(self):
        if self._closed or self._future is not None:return False
        try:
            if not self.path.text.strip():raise ValueError('Choose a local WAV file first')
            tone=float(self.tone.text);wpm=float(self.wpm.text)
            if not(150<tone<24000 and 1<=wpm<=30):raise ValueError('Use tone 151–23999 Hz and speed 1–30 WPM')
        except ValueError as error:self.error=str(error);return True
        if self._executor is None:self._executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='offline-cw')
        self._cancel.clear()
        with self._progress_lock:self._progress=None;self._progress_percent=None
        self._shown_progress=None
        self._future=self._executor.submit(decode_file,self.path.text,self.decoder,tone,wpm,
                                          cancelled=self._cancel.is_set,progress=self._record_progress)
        self.result=None;self.error=None;self.status='Decoding selected file…';return True
    def _record_progress(self,done,total):
        # Worker only replaces one value; UI state is changed by poll().
        with self._progress_lock:
            if self._closed:return
            self._progress=(done,total)
            percent=min(100,int(100*done/max(1,total)))
            if percent==self._progress_percent:return
            self._progress_percent=percent;callback=self._wakeup
        if callback is not None:callback()
    def poll(self):
        if self._closed or self._future is None:return False
        if not self._future.done():
            with self._progress_lock:progress=self._progress
            if progress is None:return False
            done,total=progress;percent=min(100,int(100*done/max(1,total)))
            if percent==self._shown_progress:return False
            self._shown_progress=percent;self.status=f'Analyzing audio… {percent}%'
            return True
        future=self._future;self._future=None
        try:self.result=future.result();self.error=None;self.status='Offline decode complete';self.layout.select('result');self.scroll=0
        except Exception as error:self.error=str(error);self.status='File was not decoded'
        return True
    def close(self):
        with self._progress_lock:self._closed=True;self._wakeup=None
        self._cancel.set()
        if self._future:self._future.cancel()
        if self._executor:self._executor.shutdown(wait=False,cancel_futures=True)
    def key(self,key):
        if key in ('\t','backtab'):self.layout.cycle(-1 if key=='backtab' else 1)
        elif self.layout.focus=='result':
            if key in ('up','down','pageup','pagedown'):self.scroll=max(0,self.scroll+(-1 if key in ('up','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1))
            elif key=='home':self.scroll=0
            else:return False
        elif key in ('up','down'):self.fields.key(key)
        elif key in ('\r','\n'):return self.decode()
        elif self.fields.index<3:return (self.path,self.tone,self.wpm)[self.fields.index].key(key)
        else:return False
        return True
    def pointer(self,column,row,width,button=0,released=False):
        if released or button&32:return False
        for x,y,w,key in self._hits:
            if y==row and x<=column<x+w and button==0:self.layout.select(key);return True
        for key,(x,y,w,h) in self._rects.items():
            if not(x<=column<x+w and y<=row<y+h):continue
            self.layout.select(key)
            if button&64:return self.key('down' if button&1 else 'up')
            if button!=0:return False
            if key=='file':
                offsets={2:0,5:1,8:2,11:3};index=offsets.get(row-y)
                if index is not None:
                    self.fields.index=index
                    if index==3:return self.decode()
            return True
        return False
    def lines(self):
        self.poll();c=Canvas(self.width,self.height);self._spans=[];self._hits=[]
        c.put(0,0,'CW · offline file decoder');self._spans.append((0,0,self.width,'toolbar'))
        rects=self.layout.layout(self.width,max(1,self.height-3))
        self._rects={key:(x,y+1,w,h) for key,(x,y,w,h) in rects.items()}
        if self.layout.tabbed:
            x=0
            for panel in self.layout.panels:
                text='['+panel.title+']' if panel.key==self.layout.focus else panel.title
                c.put(x,1,text);self._hits.append((x,1,len(text),panel.key));x+=len(text)+2
        for key,(x,y,w,h) in self._rects.items():
            c.put(x,y,('> ' if key==self.layout.focus else '')+('Selected file' if key=='file' else 'Decoded text'),w)
            self._spans.append((y,x,w,'toolbar'))
            if key=='file':
                for i,(label,field) in enumerate(zip(('Local WAV path','Tone frequency · Hz','Fixed speed · WPM'),(self.path,self.tone,self.wpm))):
                    c.put(x,y+1+i*3,label,w);c.put(x,y+2+i*3,field.draw(w),w)
                    self._spans.append((y+2+i*3,x,w,'input' if self.fields.index==i else 'muted'))
                c.put(x,y+11,'[ Decoding… ]' if self._future else '[ Decode file ]',w)
                c.put(x,y+13,'Mono 16-bit PCM · max 30 s',w);c.put(x,y+14,'No live audio or transmission',w)
            else:
                body=[]
                if self.result:
                    r=self.result;body=[f'{r["rate"]} Hz · {r["frames"]} samples · {r["seconds"]:.2f} s',f'{r["tone"]:g} Hz tone · {r["wpm"]:g} WPM','',r['text'] or '(No text detected)','','? means uncertain marks or timing.','Fixed-speed reference; inspect uncertain results.','Source: '+r['path']]
                elif self.error:body=['Could not decode this file','',self.error]
                else:body=['No file decoded yet.','',self.status]
                wrapped=[]
                for line in body:wrapped.extend(textwrap.wrap(line,max(1,w)) or [''])
                offset=min(self.scroll,max(0,len(wrapped)-max(1,h-1)))
                for n,line in enumerate(wrapped[offset:offset+max(1,h-1)]):c.put(x,y+1+n,line,w)
        c.put(0,self.height-2,self.error or self.status)
        c.put(0,self.height-1,'Tab pane · ↑/↓ field/scroll · Enter Decode file')
        return c.lines()
    def spans(self):return tuple(self._spans)
