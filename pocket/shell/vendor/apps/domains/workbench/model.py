"""Domain-owned jobs and persistence; snapshots never inspect files or run DSP."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import sys
import threading
import time
import uuid
import wave

ROOT=Path(__file__).resolve().parents[2]
MAX_FILE=32*1024*1024
MAX_OUTPUT=256*1024


class Cancelled(Exception):pass


class Workbench:
    def __init__(self,state_dir,*,wall_timeout=30):
        if not math.isfinite(wall_timeout) or not .01<=wall_timeout<=30:raise ValueError('wall timeout0.01–30s required')
        self.directory=Path(state_dir).expanduser().resolve();self.directory.mkdir(parents=True,exist_ok=True)
        self.reports=self.directory/'results';self.reports.mkdir(exist_ok=True)
        self.state_file=self.directory/'state.json';self.wall_timeout=wall_timeout
        self.lock=threading.RLock();self.worker=None;self.stop=threading.Event();self.process=None;self.closed=False
        self.state=dict(revision=0,status='idle',progress=None,selected=None,result=None,history=[],error=None,persistence_error=None,
            experiments=[dict(id='cw-replay',title='CW audio replay',kind='analysis',requires='User-selected8kHz mono S16 WAV'),
                         dict(id='fir-evidence',title='ARMv6 FIR measurements',kind='readonly_evidence',path=str(ROOT/'verification/fir-2026-10-18/REPORT.md'),status='not_loaded'),
                         dict(id='vfp-evidence',title='VFP measurements',kind='readonly_evidence',path=str(ROOT/'verification/vfp-2026-10-18/REPORT.md'),status='not_loaded')])
        if self.state_file.is_file():
            try:
                if self.state_file.stat().st_size>512*1024:raise ValueError('saved state exceeds limit')
                saved=json.loads(self.state_file.read_text())
                history=saved.get('history',[])
                if not isinstance(history,list):raise ValueError('invalid saved history')
                self.state['history']=[v for v in history[-20:] if isinstance(v,dict) and re.fullmatch('[0-9a-f]{32}',str(v.get('id','')))]
                # A restart never restores selected-file permission or starts an old job.
            except (OSError,ValueError,TypeError) as error:self.state['error']='Saved history unavailable: '+str(error)

    def snapshot(self):
        with self.lock:return copy.deepcopy(self.state)

    def _update(self,**changes):
        with self.lock:self.state.update(changes);self.state['revision']+=1

    def _persist(self):
        payload=json.dumps(dict(history=self.state['history']),ensure_ascii=True).encode()
        temp=self.directory/('state-'+uuid.uuid4().hex+'.tmp')
        try:
            with temp.open('xb') as target:os.chmod(temp,0o600);target.write(payload)
            temp.replace(self.state_file)
        finally:
            if temp.exists():temp.unlink()

    def _check(self):
        if self.stop.is_set():raise Cancelled()

    def _launch(self,kind,action,*,remember=True):
        with self.lock:
            if self.closed:raise RuntimeError('Workbench is closed')
            if self.worker and self.worker.is_alive():raise RuntimeError('A Workbench job is already active')
            job=uuid.uuid4().hex;self.stop=threading.Event()
            self._update(status='running',progress=dict(job_id=job,kind=kind,fraction=0.),error=None,result=None)
            def work():
                started=time.monotonic()
                try:
                    result=action();self._check();status='complete';error=None
                except Cancelled:result=None;status='cancelled';error=None
                except Exception as exc:result=None;status='failed';error=str(exc)[:1000]
                with self.lock:
                    report=dict(id=job,kind=kind,status=status,elapsed_seconds=time.monotonic()-started,result=result,error=error)
                    if remember:
                        try:
                            path=self.reports/(job+'.json')
                            with path.open('x') as target:os.chmod(path,0o600);json.dump(report,target)
                            entry=dict(id=job,kind=kind,status=status,artifact_ref=str(path),error=error)
                            self.state['history'].append(entry)
                            while len(self.state['history'])>20:
                                old=self.state['history'].pop(0);old_path=self.reports/(old['id']+'.json')
                                if old_path.is_file():old_path.unlink()
                            self._persist()
                        except OSError as exc:self.state['persistence_error']=str(exc)[:1000]
                    self._update(status=status,progress=dict(job_id=job,kind=kind,fraction=1. if status=='complete' else None),result=result,error=error)
            self.worker=threading.Thread(target=work,name='workbench-job',daemon=True);self.worker.start();return job

    def _open(self,path):
        target=Path(path).expanduser().resolve(strict=True)
        if not stat.S_ISREG(target.stat().st_mode):raise ValueError('Select a regular local file')
        fd=os.open(target,os.O_RDONLY|os.O_NONBLOCK|getattr(os,'O_NOFOLLOW',0))
        source=os.fdopen(fd,'rb')
        info=os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size>MAX_FILE:source.close();raise ValueError('Regular local files must be32MiB or smaller')
        return target,source,info

    def _hash(self,source):
        digest=hashlib.sha256();total=0
        while True:
            self._check();raw=source.read(65536)
            if not raw:break
            total+=len(raw)
            if total>MAX_FILE:raise ValueError('File grew beyond32MiB')
            digest.update(raw)
        source.seek(0);return digest.hexdigest()

    def select(self,path):
        def inspect():
            target,source,info=self._open(path)
            with source:
                digest=self._hash(source);metadata=dict(path=str(target),name=target.name,bytes=info.st_size,sha256=digest,kind='file',cw_supported=False)
                try:
                    with wave.open(source,'rb') as audio:
                        rate=audio.getframerate();frames=audio.getnframes()
                        metadata.update(kind='wav',sample_rate=rate,channels=audio.getnchannels(),sample_width=audio.getsampwidth(),frames=frames,seconds=frames/rate if rate else None,compression=audio.getcomptype())
                        metadata['cw_supported']=(rate,audio.getnchannels(),audio.getsampwidth(),audio.getcomptype())==(8000,1,2,'NONE')
                        if metadata['cw_supported']:
                            if frames*2>info.st_size:raise ValueError('Truncated PCM data declaration')
                            remaining=frames
                            while remaining:
                                self._check();count=min(32768,remaining);raw=audio.readframes(count)
                                if len(raw)!=count*2:raise ValueError('Truncated PCM data')
                                remaining-=count
                except (wave.Error,EOFError):metadata['note']='No supported PCM WAV header; inspection only'
                if not metadata['cw_supported']:metadata.setdefault('note','CW replay requires8kHz mono S16 PCM; explicit external conversion is needed')
            self._check();self._update(selected=metadata);return dict(kind='inspection',metadata=metadata)
        with self.lock:
            if self.closed:raise RuntimeError('Workbench is closed')
            if self.worker and self.worker.is_alive():raise RuntimeError('A Workbench job is already active')
            self._update(selected=None)
            return self._launch('inspect',inspect)

    def run_cw(self,*,tone=700,wpm=20,seconds=30,method='route'):
        if not all(isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v) for v in (tone,wpm,seconds)):raise ValueError('finite numeric CW parameters required')
        if not 300<=tone<=3000 or not 5<=wpm<=30 or not .1<=seconds<=60:raise ValueError('CW limits:300–3000Hz,5–30WPM,0.1–60s')
        if method not in ('route','probabilistic','matched','timing'):raise ValueError('Unsupported CW method')
        with self.lock:
            selected=copy.deepcopy(self.state['selected'])
            if not selected or not selected.get('cw_supported'):raise ValueError('Inspect a supported8kHz mono S16 WAV first')
            return self._launch('cw',lambda:self._cw(selected,tone,wpm,seconds,method))

    def _cw(self,selected,tone,wpm,seconds,method):
        path,source,info=self._open(selected['path'])
        with source:
            if info.st_size!=selected['bytes'] or self._hash(source)!=selected['sha256']:raise ValueError('Selected file changed; inspect it again')
            self._check();fd=source.fileno()
            command=[sys.executable,str(Path(__file__).with_name('runner.py')),'--wav','/dev/fd/'+str(fd),'--tone',str(tone),'--wpm',str(wpm),'--seconds',str(seconds),'--method',method]
            process=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(fd,))
            with self.lock:self.process=process
            selector=selectors.DefaultSelector();errors=bytearray();events=[];line=bytearray();size=0;deadline=time.monotonic()+self.wall_timeout
            selector.register(process.stdout,selectors.EVENT_READ,'out');selector.register(process.stderr,selectors.EVENT_READ,'err')
            try:
                while selector.get_map():
                    self._check()
                    if time.monotonic()>deadline:raise ValueError('CW replay wall-time limit reached')
                    for key,_ in selector.select(.05):
                        raw=os.read(key.fileobj.fileno(),16384)
                        if not raw:selector.unregister(key.fileobj);continue
                        size+=len(raw)
                        if size>MAX_OUTPUT:raise ValueError('CW output limit reached')
                        if key.data=='err':errors.extend(raw);continue
                        line.extend(raw)
                        while b'\n' in line:
                            value,_,rest=line.partition(b'\n');line=bytearray(rest);event=json.loads(value)
                            if not isinstance(event,dict):raise ValueError('Invalid CW event')
                            events.append(event)
                            if len(events)>256:raise ValueError('CW event limit reached')
                            end=event.get('end_sample',0)/8000
                            with self.lock:
                                progress=dict(self.state['progress']);progress.update(fraction=min(.99,end/seconds),audio_seconds=end,event_count=len(events));self._update(progress=progress)
                process.wait(timeout=1)
                self._check()
                if process.returncode:raise ValueError('CW replay failed: '+errors.decode(errors='replace')[:800])
                if line:raise ValueError('Truncated CW event')
                source.seek(0)
                if self._hash(source)!=selected['sha256']:raise ValueError('Selected file changed during replay')
                return dict(kind='cw',input=selected,settings=dict(tone=tone,wpm=wpm,seconds=seconds,method=method),events=events,text=' '.join(e.get('text','') for e in events if e.get('type')=='cw_candidate'),verified=False,scope='Local file replay; not live HF reception',processed_seconds=min(seconds,selected['seconds']))
            finally:
                selector.close()
                if process.poll() is None:
                    process.terminate()
                    try:process.wait(timeout=1)
                    except subprocess.TimeoutExpired:process.kill();process.wait()
                process.stdout.close();process.stderr.close()
                with self.lock:self.process=None

    def refresh_evidence(self):
        def read():
            evidence=[]
            for item in self.state['experiments']:
                if item['kind']!='readonly_evidence':continue
                self._check();entry=dict(item);path=Path(item['path'])
                try:
                    with path.open('rb') as source:raw=source.read(65537)
                    if len(raw)>65536:raise ValueError('Report exceeds64KiB')
                    entry.update(status='available',sha256=hashlib.sha256(raw).hexdigest(),text=raw.decode('utf8',errors='replace'))
                except (OSError,ValueError) as exc:entry.update(status='unavailable',error=str(exc))
                evidence.append(entry)
            return dict(kind='evidence',items=evidence,scope='Read-only existing reports; no experiment binary executed')
        return self._launch('evidence',read)

    def load_result(self,job_id):
        if not isinstance(job_id,str) or not re.fullmatch('[0-9a-f]{32}',job_id):raise ValueError('Invalid result identifier')
        with self.lock:
            if not any(item['id']==job_id for item in self.state['history']):raise ValueError('Result is not in retained history')
        def read():
            path=self.reports/(job_id+'.json')
            if path.is_symlink():raise ValueError('Result must not be a symlink')
            with path.open('rb') as source:raw=source.read(512*1024+1)
            if len(raw)>512*1024:raise ValueError('Saved result exceeds limit')
            value=json.loads(raw)
            if value.get('id')!=job_id:raise ValueError('Saved result identity mismatch')
            return dict(kind='history',report=value)
        return self._launch('history',read,remember=False)

    def cancel(self):
        with self.lock:
            if self.state['status'] not in ('running','cancelling') or not self.worker or not self.worker.is_alive():return False
            self.stop.set();self._update(status='cancelling');return True

    def close(self):
        with self.lock:self.closed=True;self.cancel();worker=self.worker
        if worker:worker.join(timeout=3)
