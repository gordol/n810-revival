"""Transport, evidence boundaries and negative controls for the receive adapter."""
import random
import struct
import unittest
from stream_cw import Receiver
from test_decode import fixture


def pcm(samples):return b''.join(struct.pack('<h',round(max(-1,min(1,x))*32767)) for x in samples)


class StreamTests(unittest.TestCase):
    def run_stream(self,samples,block=4096,**config):
        events=[];r=Receiver(events.append,**config);raw=pcm(samples)
        for i in range(0,len(raw),block):r.feed(raw[i:i+block])
        r.finish();return events,r

    def test_packet_boundaries_preserve_text(self):
        samples=fixture('CQ N0DEM SOS 73')
        a,_=self.run_stream(samples);b,_=self.run_stream(samples,block=137)
        self.assertEqual([(e['text'],e['start_sample'],e['end_sample']) for e in a],[(e['text'],e['start_sample'],e['end_sample']) for e in b])
        self.assertEqual(' '.join(e['text'] for e in a),'CQ N0DEM SOS 73')
        self.assertTrue(all(not e['verified'] for e in a))

    def test_nonoverlapping_bounded_evidence(self):
        events,r=self.run_stream(fixture('CQ '*15),window_seconds=2)
        self.assertTrue(events)
        for e in events:self.assertLessEqual(e['end_sample']-e['start_sample'],16000)
        for a,b in zip(events,events[1:]):self.assertLessEqual(a['end_sample'],b['start_sample'])
        self.assertTrue(any(e['boundary_uncertain'] for e in events))
        self.assertFalse(r.buffer)

    def test_eof_fractional_window_has_real_timestamp(self):
        events,r=self.run_stream(fixture('CQ')+[.01]*7,block=139)
        self.assertEqual(r.position,len(fixture('CQ'))+7)
        self.assertEqual(events[-1]['end_sample'],r.position)

    def test_gap_reset_discards_partial_frame(self):
        events=[];r=Receiver(events.append);r.feed(pcm(fixture('E'))+b'\x00');r.reset()
        self.assertEqual(events[-1]['type'],'input_gap');self.assertEqual(r.pending,b'')
        r.feed(pcm(fixture('T')));r.finish()
        self.assertEqual(events[-1]['text'],'T')

    def test_negative_controls(self):
        import math
        rng=random.Random(261018)
        for samples in ([0.]*24000,[rng.uniform(-.1,.1) for _ in range(24000)],
                        [.2*math.sin(2*math.pi*700*i/8000) for i in range(24000)]):
            events,_=self.run_stream(samples)
            self.assertFalse([e for e in events if e['type']=='cw_candidate'],events)

    def test_truncated_sample_and_oversize(self):
        r=Receiver(lambda e:None);r.feed(b'\0')
        with self.assertRaises(ValueError):r.finish()
        with self.assertRaises(ValueError):r.feed(bytes(65537))

if __name__=='__main__':unittest.main()
