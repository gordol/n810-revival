"""Native-format validation, reset handling and antialias rejection."""
import base64
import math
import struct
import unittest
from pcm_input import Downsample,Events
from stream_cw import Receiver
from test_stream_cw import pcm
from test_decode import fixture


class InputTests(unittest.TestCase):
    def test_antialias_and_passband(self):
        for rate in (16000,32000,48000):
            powers=[]
            for tone in (700,5700):
                raw=pcm([.5*math.sin(2*math.pi*tone*i/rate) for i in range(rate//4)])
                values=[];d=Downsample(rate)
                for i in range(0,len(raw),478):values.extend(v[0]/32768 for v in struct.iter_unpack('<h',d.feed(raw[i:i+478])))
                powers.append(sum(v*v for v in values[100:])/len(values[100:]))
                self.assertEqual(len(values),2000)
            self.assertGreater(powers[0],.1)
            self.assertLess(powers[1]/powers[0],1e-5)

    def test_chunk_independent_resampling(self):
        raw=pcm([.5*math.sin(2*math.pi*700*i/32000) for i in range(2048)])
        a=Downsample(32000).feed(raw);d=Downsample(32000)
        b=b''.join(d.feed(raw[i:i+94]) for i in range(0,len(raw),94))
        self.assertEqual(a,b)

    def test_event_gap_and_format(self):
        output=[];events=Events(lambda emit:Receiver(emit),output.append)
        fmt=dict(type='format',stream_id='test',sample_rate=8000,encoding='s16le',channels=1)
        events.consume(fmt);raw=pcm(fixture('CQ'))
        def event(seq,first):return dict(fmt,type='pcm',sequence=seq,first_sample=first,sample_count=len(raw)//2,pcm_b64=base64.b64encode(raw).decode())
        events.consume(event(0,0));events.consume(event(2,len(raw)//2+80));events.finish()
        self.assertTrue(any(e.get('reason')=='sequence_or_sample_gap' for e in output))
        candidates=[e for e in output if e['type']=='cw_candidate']
        self.assertTrue(candidates);self.assertTrue(all(e['capture_time_known'] is False for e in candidates))
        self.assertEqual(candidates[-1]['native_anchor_sample'],len(raw)//2+80)

    def test_declared32k_known_message(self):
        output=[];events=Events(lambda emit:Receiver(emit),output.append)
        fmt=dict(type='format',stream_id='32k',sample_rate=32000,encoding='s16le',channels=1)
        events.consume(fmt);raw=pcm(fixture('CQ N0CALL SOS 73',rate=32000))
        for sequence,offset in enumerate(range(0,len(raw),1280)):
            block=raw[offset:offset+1280]
            events.consume(dict(fmt,type='pcm',sequence=sequence,first_sample=offset//2,sample_count=len(block)//2,pcm_b64=base64.b64encode(block).decode()))
        events.finish()
        self.assertEqual(' '.join(e['text'] for e in output if e['type']=='cw_candidate'),'CQ N0CALL SOS 73')

    def test_reject_undeclared_mismatched_and_oversize(self):
        events=Events(lambda emit:Receiver(emit),lambda e:None)
        with self.assertRaises(ValueError):events.consume(dict(type='pcm'))
        for rate in (44100,8000.):
            with self.assertRaises(ValueError):events.consume(dict(type='format',sample_rate=rate,encoding='s16le',channels=1,stream_id='a'))
        events.consume(dict(type='format',sample_rate=8000,encoding='s16le',channels=1,stream_id='a'))
        with self.assertRaises(ValueError):events.consume(dict(type='pcm',sample_rate=8000,encoding='s16le',channels=1,stream_id='a',sequence=0,first_sample=0,sample_count=1,pcm_b64='bad!'))

if __name__=='__main__':unittest.main()
