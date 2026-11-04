"""Validated native-rate PCM events and antialiased integer conversion to8kHz."""
import base64
from collections import deque
import math
import struct


class Downsample:
    def __init__(self,rate):
        if rate not in (8000,16000,32000,48000):raise ValueError('supported native rates:8/16/32/48kHz')
        self.rate=rate;self.factor=rate//8000;self.index=0
        self.history=deque([0.]*193,maxlen=193)
        self.delay=0 if self.factor==1 else 96
        coefficients=[]
        for n in range(193):
            x=n-96;cutoff=3200/rate
            sinc=2*cutoff if not x else math.sin(2*math.pi*cutoff*x)/(math.pi*x)
            coefficients.append(sinc*(.42-.5*math.cos(2*math.pi*n/192)+.08*math.cos(4*math.pi*n/192)))
        scale=sum(coefficients);self.coefficients=[c/scale for c in coefficients]

    def feed(self,raw):
        if len(raw)%2 or len(raw)>65536:raise ValueError('invalid native PCM block size')
        if self.factor==1:return raw
        output=[]
        for (value,) in struct.iter_unpack('<h',raw):
            self.history.append(value)
            if self.index%self.factor==0:
                sample=sum(c*v for c,v in zip(self.coefficients,self.history))
                output.append(max(-32768,min(32767,round(sample))))
            self.index+=1
        return b''.join(struct.pack('<h',v) for v in output)


class Events:
    def __init__(self,factory,emit):
        self.factory=factory;self.emit=emit;self.receiver=None;self.format=None;self.resampler=None
        self.next_sequence=None;self.next_sample=None;self.epoch=0;self.samples_seconds=0.;self.anchor=None

    def reset(self,reason):
        if self.receiver:self.receiver.reset()
        self.receiver=None;self.resampler=None;self.next_sample=None;self.next_sequence=None;self.anchor=None
        self.epoch+=1;self.emit(dict(type='cw_input_reset',reason=reason,input_epoch=self.epoch))

    def configure(self,event):
        if event.get('direction','rx')!='rx':raise ValueError('receive-only PCM required')
        if event.get('encoding')!='s16le' or event.get('channels')!=1:raise ValueError('declared mono S16LE PCM required')
        rate=event.get('sample_rate')
        if type(rate) is not int or rate not in (8000,16000,32000,48000):raise ValueError('unsupported declared rate')
        if not isinstance(event.get('stream_id'),str) or not event['stream_id'] or len(event['stream_id'])>128:raise ValueError('stream identifier required')
        self.reset('format');self.format=event

    def consume(self,event):
        kind=event.get('type')
        if kind=='format':self.configure(event);return
        if kind=='gap':self.reset(str(event.get('reason','gap')));return
        if kind!='pcm':raise ValueError('expected format, gap or decoded PCM event')
        if event.get('direction','rx')!='rx':raise ValueError('receive-only PCM required')
        if self.format is None:raise ValueError('PCM received before format declaration')
        for key in ('stream_id','sample_rate','encoding','channels'):
            if event.get(key)!=self.format.get(key):raise ValueError('PCM format/stream changed without format event')
        for key in ('sequence','first_sample','sample_count'):
            if type(event.get(key)) is not int or event[key]<0:raise ValueError('invalid '+key)
        payload=event.get('pcm_b64')
        if not isinstance(payload,str) or len(payload)>87384:raise ValueError('invalid/big PCM payload')
        try:raw=base64.b64decode(payload,validate=True)
        except (ValueError,TypeError) as error:raise ValueError('invalid PCM base64') from error
        if not raw or len(raw)!=event['sample_count']*2 or len(raw)>65536:raise ValueError('PCM count/payload mismatch')
        if self.next_sequence is not None and (event['sequence']!=self.next_sequence or event['first_sample']!=self.next_sample):self.reset('sequence_or_sample_gap')
        if self.receiver is None:
            self.anchor=event['first_sample'];self.resampler=Downsample(self.format['sample_rate'])
            context=dict(receiver_id=self.format.get('receiver_id'),source_stream_id=self.format.get('source_stream_id'),input_epoch=self.epoch,audio_stream_id=self.format['stream_id'],native_rate=self.format['sample_rate'],native_anchor_sample=self.anchor,
                         resampler_delay_native_samples=self.resampler.delay,time_basis='converted_sample_count_within_epoch',capture_time_known=False)
            self.receiver=self.factory(lambda value:self.emit(dict(value,**context)))
        self.next_sequence=event['sequence']+1;self.next_sample=event['first_sample']+event['sample_count']
        self.samples_seconds+=event['sample_count']/self.format['sample_rate']
        converted=self.resampler.feed(raw)
        for offset in range(0,len(converted),4096):self.receiver.feed(converted[offset:offset+4096])

    def finish(self):
        if self.receiver:self.receiver.finish()
