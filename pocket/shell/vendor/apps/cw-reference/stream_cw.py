"""Bounded receive-only CW candidates from contiguous 8 kHz mono S16 PCM."""
import argparse
import json
import math
import select
import socket
import struct
import sys
import time
import wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/'corpus'))
from decode import decode_samples
from probabilistic import decode_evidence
from reference import analyze
from strategies import matched,route


class Receiver:
    def __init__(self,emit,*,tone=700,wpm=20,method='route',window_seconds=12,gap_seconds=.8,source='pcm'):
        if not 300<=tone<=3000 or not 5<=wpm<=30:raise ValueError('tone300–3000Hz and speed5–30WPM required')
        if not 2<=window_seconds<=24 or not .3<=gap_seconds<=2:raise ValueError('window2–24s and gap0.3–2s required')
        if method not in ('route','probabilistic','matched','timing'):raise ValueError('unknown method')
        self.emit=emit;self.tone=tone;self.wpm=wpm;self.method=method;self.limit=round(window_seconds*8000);self.gap=round(gap_seconds*100)
        self.source=source;self.position=0;self.start=0;self.buffer=[];self.pending=b'';self.idle=0;self.sequence=0;self.last_boundary=0

    def feed(self,raw):
        # Callers supply bounded transport blocks. Preserve split S16 samples/windows.
        if len(raw)>65536:raise ValueError('transport block exceeds64KiB')
        self.pending+=raw
        while len(self.pending)>=160:
            frame,self.pending=self.pending[:160],self.pending[160:]
            values=[v[0]/32768 for v in struct.iter_unpack('<h',frame)]
            item=analyze(values,8000,self.tone,10)[0]
            active=item.tone_power>max(1e-7,4*item.noise_power)
            if not self.buffer:
                self.start=self.position
                if not active:self.position+=80;continue
            self.buffer.extend(values)
            self.idle=0 if active else self.idle+1
            if self.idle>=math.ceil(2.5*1.2/self.wpm/.01):self.last_boundary=len(self.buffer)
            self.position+=80
            if self.idle>=self.gap:self.flush('gap')
            elif len(self.buffer)>=self.limit:
                cut=self.last_boundary if self.last_boundary>=self.limit-8000 else len(self.buffer)
                rest=self.buffer[cut:];idle=self.idle;self.buffer=self.buffer[:cut]
                self.flush('window_gap' if rest else 'window_limit')
                self.buffer=rest;self.start=self.position-len(rest);self.idle=idle if rest else 0;self.last_boundary=0

    def flush(self,reason):
        if not self.buffer:return
        samples=self.buffer;self.buffer=[];self.idle=0;self.last_boundary=0;self.sequence+=1
        # A short synthetic EOF tail is excluded from evidence timestamps.
        padded=samples+[0.]*4800
        started=time.monotonic();selection,evidence=route(samples,8000,self.tone,self.wpm)
        chosen=selection if self.method=='route' else self.method
        details={}
        if chosen=='fixed':
            text=decode_samples(padded,8000,self.tone,self.wpm)
            if '?' in text:
                result=decode_evidence(analyze(padded,8000,self.tone,10),rate=8000,wpm=self.wpm)
                text=result.text;chosen='probabilistic';details=dict(uncertain=result.uncertain,fallback_reason='fixed decoder produced malformed symbols')
        elif chosen=='matched':text=matched(padded,8000,self.tone,self.wpm).text
        elif chosen=='probabilistic':
            result=decode_evidence(analyze(padded,8000,self.tone,10),rate=8000,wpm=self.wpm);text=result.text
            details=dict(uncertain=result.uncertain)
        else:
            from overlap_lattice import decode
            result,model=decode(samples,tone=self.tone,conditioned=True,diverse=True);text=result.text
            details=dict(repairs=len(result.repairs))
        event=dict(type='cw_candidate' if text.strip() else 'cw_abstain',source=self.source,sequence=self.sequence,
            start_sample=self.start,end_sample=self.start+len(samples),sample_rate=8000,
            text=text,method=chosen,tone_hz=self.tone,initial_wpm=self.wpm,
            verified=False,reason=reason,boundary_uncertain=reason in ('window_limit','window_gap','input_gap'),
            clipping_samples=sum(abs(v)>=.999 for v in samples),decode_host_seconds=time.monotonic()-started,
            routing=evidence,**details)
        self.emit(event)

    def reset(self):
        self.flush('input_gap');self.pending=b'';self.idle=0
        self.emit(dict(type='input_gap',source=self.source,at_sample=self.position))

    def finish(self):
        if self.pending:
            if len(self.pending)%2:raise ValueError('truncated S16 sample at EOF')
            values=[v[0]/32768 for v in struct.iter_unpack('<h',self.pending)]
            if not self.buffer:self.start=self.position
            self.buffer.extend(values);self.position+=len(values);self.pending=b''
        self.flush('eof')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--wav',type=Path,help='Replay mono8kHz S16 WAV without capture')
    inputs.add_argument('--ndjson',type=Path,help='Replay declared PCM event file; no radio access')
    inputs.add_argument('--socket',type=Path,help='Connect to an existing decoded-PCM UNIX stream')
    inputs.add_argument('--stdin',action='store_true',help='Read raw8kHz mono S16_LE PCM; no resampling')
    parser.add_argument('--tone',type=float,default=700)
    parser.add_argument('--wpm',type=float,default=20)
    parser.add_argument('--method',choices=('route','probabilistic','matched','timing'),default='route')
    parser.add_argument('--window',type=float,default=12)
    parser.add_argument('--gap',type=float,default=.8)
    parser.add_argument('--seconds',type=float,default=120,help='Bounded input duration, maximum3600s')
    parser.add_argument('--idle-timeout',type=float,default=10,help='Stop after this many seconds without stdin PCM')
    parser.add_argument('--format',choices=('json','text'),default='json')
    args=parser.parse_args()
    if not math.isfinite(args.seconds) or not 0<args.seconds<=3600:parser.error('seconds must be0–3600')
    if not math.isfinite(args.idle_timeout) or not 0<args.idle_timeout<=60:parser.error('idle timeout must be0–60s')
    def emit(event):
        if args.format=='json':print(json.dumps(event,allow_nan=False),flush=True)
        elif event['type']=='cw_candidate':print('[candidate %.2f–%.2fs %s] %s'%(event['start_sample']/8000,event['end_sample']/8000,event['method'],event['text']),flush=True)
        elif event['type']=='cw_abstain':print('[no reliable text]',flush=True)
        else:print('[%s: %s]'%(event['type'],event.get('reason','')),flush=True)
    try:
        receiver=Receiver(emit,tone=args.tone,wpm=args.wpm,method=args.method,window_seconds=args.window,gap_seconds=args.gap,source='wav_replay' if args.wav else 'raw_pcm')
        if args.ndjson or args.socket:
            from pcm_input import Events
            events=Events(lambda output:Receiver(output,tone=args.tone,wpm=args.wpm,method=args.method,window_seconds=args.window,gap_seconds=args.gap,source='pcm_events'),emit)
            def consume_events(source):
                deadline=time.monotonic()+args.seconds+args.idle_timeout
                while events.samples_seconds<args.seconds:
                    if time.monotonic()>deadline:raise ValueError('PCM event wall-time limit reached')
                    line=source.readline(131073)
                    if not line:break
                    if len(line)>131072:raise ValueError('PCM event line too large')
                    event=json.loads(line)
                    if not isinstance(event,dict):raise ValueError('PCM event must be an object')
                    events.consume(event)
                events.finish()
            if args.ndjson:
                with args.ndjson.open('rb') as source:consume_events(source)
            else:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                    client.settimeout(args.idle_timeout);client.connect(str(args.socket))
                    with client.makefile('rb') as source:consume_events(source)
            return
        remaining=round(args.seconds*8000)*2
        def consume(read):
            nonlocal remaining
            while remaining:
                raw=read(min(4096,remaining))
                if not raw:break
                remaining-=len(raw);receiver.feed(raw)
            receiver.finish()
        if args.wav:
            with wave.open(str(args.wav)) as wav:
                if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getcomptype())!=(1,2,8000,'NONE'):raise ValueError('WAV must be8kHz mono S16 PCM; convert explicitly first')
                consume(lambda count:wav.readframes(count//2))
        else:
            def read_pcm(count):
                ready,_,_=select.select([sys.stdin.buffer],[],[],args.idle_timeout)
                if not ready:raise ValueError('no PCM received within idle timeout')
                return sys.stdin.buffer.read1(count)
            consume(read_pcm)
    except KeyboardInterrupt:
        print('CW receiver stopped',file=sys.stderr)
    except (ValueError,OSError,wave.Error) as error:parser.exit(2,str(error)+'\n')


if __name__=='__main__':main()
