"""Bounded PCM visualization metrics; no I/O, codec, resampling or waveform storage."""
import array
import base64
from collections import deque
import math
import sys
import time


def dbfs(amplitude):return max(-100.,20*math.log10(max(1e-5,amplitude)))


def spectrum(samples,size=256):
    """One-sided Hann-window amplitude spectrum in dBFS, not calibrated RF power."""
    if size not in (128,256,512):raise ValueError('Unsupported FFT size')
    values=list(samples)[-size:]
    if len(values)<size:return ()
    window=[.5-.5*math.cos(2*math.pi*i/(size-1)) for i in range(size)]
    values=[complex(v*w/32768) for v,w in zip(values,window)]
    j=0
    for i in range(1,size):
        bit=size>>1
        while j&bit:j^=bit;bit>>=1
        j^=bit
        if i<j:values[i],values[j]=values[j],values[i]
    length=2
    while length<=size:
        angle=-2*math.pi/length;step=complex(math.cos(angle),math.sin(angle))
        for start in range(0,size,length):
            phase=1+0j
            for i in range(start,start+length//2):
                left=values[i];right=values[i+length//2]*phase
                values[i]=left+right;values[i+length//2]=left-right;phase*=step
        length*=2
    scale=sum(window)
    return tuple(dbfs(abs(v)*(1 if i in (0,size//2) else 2)/scale) for i,v in enumerate(values[:size//2+1]))


class AudioMetrics:
    """Native-rate mono/stereo S16LE. Producer owns codec and capture-clock truth."""
    def __init__(self,fps=2,fft_size=256,history=48,clock=time.monotonic):
        if not 1<=fps<=10 or fft_size not in (128,256,512) or not 1<=history<=120:raise ValueError('Invalid monitor bounds')
        self.clock=clock;self.fps=fps;self.fft_size=fft_size;self.waterfall=deque(maxlen=history)
        self.connected=False;self.format=None;self.last_pcm=None;self.last_snapshot=0.;self.sequence=None;self.next_sample=None
        self.tail=[];self.squares=[];self.peaks=[];self.clips=[];self.count=0;self.gaps=0;self.reason='Disconnected';self.channel=0;self._last={}
    def clear_segment(self,reason):
        self.reason=reason;self.sequence=None;self.next_sample=None;self.last_pcm=None;self.count=0
        channels=self.format['channels'] if self.format else 0
        self.tail=[deque(maxlen=self.fft_size) for _ in range(channels)]
        self.squares=[0]*channels;self.peaks=[0]*channels;self.clips=[0]*channels
        self.waterfall.clear();self._last={}
    def feed(self,event):
        kind=event.get('type')
        if kind in ('format','pcm') and event.get('direction') not in (None,'rx'):raise ValueError('Receive PCM required')
        if kind=='status':
            self.connected=event.get('state')=='connected'
            if not self.connected:self.clear_segment(str(event.get('state') or 'Disconnected'))
            return
        if kind=='gap':self.gaps+=1;self.clear_segment(str(event.get('reason') or 'Audio gap'));return
        if kind=='format':
            rate=event.get('sample_rate');channels=event.get('channels')
            if type(rate)!=int or rate not in (8000,16000,32000,44100,48000) or type(channels)!=int or channels not in (1,2) or event.get('encoding')!='s16le' or not isinstance(event.get('stream_id'),str):raise ValueError('Unsupported declared PCM format')
            self.format={k:event.get(k) for k in ('stream_id','sample_rate','source_sample_rate','channels','encoding','receiver_id','codec','clock_domain','time_basis','source_stream_id','direction','capture_time_known','clock_uncertainty_ns')}
            self.channel=min(self.channel,channels-1);self.clear_segment('Waiting for PCM');return
        if kind!='pcm':return
        if not self.format or event.get('stream_id')!=self.format['stream_id']:raise ValueError('PCM requires matching format/stream')
        if any(event.get(k)!=self.format[k] for k in ('sample_rate','channels','encoding')):raise ValueError('PCM changed format without a format event')
        sequence=event.get('sequence');first=event.get('first_sample');count=event.get('sample_count')
        if type(sequence)!=int or sequence<0 or type(first)!=int or first<0 or type(count)!=int or not 1<=count<=4096:raise ValueError('Invalid PCM segment counters')
        encoded=event.get('pcm_b64')
        if not isinstance(encoded,str) or len(encoded)>22000:raise ValueError('PCM block exceeds bound')
        try:raw=base64.b64decode(encoded,validate=True)
        except ValueError as error:raise ValueError('Invalid PCM encoding') from error
        channels=self.format['channels']
        if len(raw)!=count*channels*2:raise ValueError('PCM count/byte mismatch')
        if self.sequence is not None and (sequence!=self.sequence+1 or first!=self.next_sample):
            self.gaps+=1;self.clear_segment('Sample discontinuity')
        samples=array.array('h');samples.frombytes(raw)
        if sys.byteorder!='little':samples.byteswap()
        for channel in range(channels):
            values=samples[channel::channels]
            self.squares[channel]+=sum(v*v for v in values)
            self.peaks[channel]=max(self.peaks[channel],max(abs(v) for v in values))
            self.clips[channel]+=sum(v>=32767 or v<=-32768 for v in values)
            self.tail[channel].extend(values[-self.fft_size:])
        self.sequence=sequence;self.next_sample=first+count;self.count+=count;self.last_pcm=self.clock();self.connected=True;self.reason='PCM received'
        return raw
    def set_channel(self,channel):
        if self.format and 0<=channel<self.format['channels']:
            self.channel=channel;self.waterfall.clear();self._last={};self.last_snapshot=0
    def snapshot(self,force=False):
        now=self.clock();age=None if self.last_pcm is None else max(0,now-self.last_pcm)
        state='Disconnected' if not self.connected else 'No audio' if age is None or age>2 else 'Receiving'
        if self.count and (force or now-self.last_snapshot>=1/self.fps):
            levels=spectrum(self.tail[self.channel],self.fft_size)
            if levels:
                bands=bytes(max(0,min(255,round((value+90)*255/90))) for value in levels)
                self.waterfall.append(bands)
            self._last=dict(rms_dbfs=tuple(dbfs(math.sqrt(v/self.count)/32768) for v in self.squares),
                            peak_dbfs=tuple(dbfs(v/32768) for v in self.peaks),full_scale_samples=tuple(self.clips),
                            spectrum_dbfs=levels,window_samples=self.count)
            self.squares=[0]*len(self.tail);self.peaks=[0]*len(self.tail);self.clips=[0]*len(self.tail);self.count=0;self.last_snapshot=now
        return dict(self._last,state=state,format=dict(self.format) if self.format else None,age=age,gaps=self.gaps,reason=self.reason,
                    channel=self.channel,waterfall=tuple(self.waterfall),playback=False)
