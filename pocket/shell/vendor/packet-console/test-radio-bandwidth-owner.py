"""Verify proposed owner hooks in an isolated source copy, never the device."""
import collections
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        for path in ROOT.glob('*.py'):shutil.copy2(path,cls.root/path.name)
        shutil.copy2(ROOT/'radio-read-layouts.json',cls.root/'radio-read-layouts.json')
        cls.bridge=load(cls.root/'n810-kiss-bridge.py','patched_bridge')
        cls.live=load(cls.root/'n810-radio-live.py','patched_live')
        cls.fixture=load(cls.root/'test-radio-bandwidth.py','bandwidth_fixture')
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def test_bridge_only_accepts_guarded_slot0_bandwidth(self):
        bridge=object.__new__(self.bridge.Bridge);bridge.writer=None;bridge.tx=collections.deque();bridge.tx_size=0;bridge.modify_radio=lambda:None
        raw=self.fixture.channel();wide=raw[:13]+bytes([raw[13]|16])+raw[14:]
        bridge.bandwidth_request(14,wide,raw)
        self.assertEqual(bridge.tx[0][0][8:],wide)
        self.assertIsNone(bridge.tx[0][2])
        bridge.tx.clear();bridge.tx_size=0;bridge.writer=object()
        with self.assertRaises(RuntimeError):bridge.bandwidth_request(14,wide,raw)
        bridge.writer=None
        for command,payload in ((13,b'\1\2'),(11,b''),(31,b'RF'),(60,b'\0')):
            with self.assertRaises(ValueError):bridge.bandwidth_request(command,payload)
        wrong=wide[:-1]+bytes([wide[-1]^1])
        with self.assertRaises(ValueError):bridge.bandwidth_request(14,wrong,raw)
    def test_transaction_receives_replies_while_telemetry_paused(self):
        events=[]
        class Control:
            active=True
            def consume(self,word,body):events.append((word,body))
            def tick(self,now):events.append(('tick',now))
        live=self.live.Telemetry(lambda _:None,self.root/'state.json',self.root/'control.json',self.root/'gps.json');live.bandwidth=Control();live.publish=lambda:events.append('publish')
        body=b'\0'+self.fixture.channel()
        frame=b'\xff\1\0'+bytes([len(body)])+b'\0\2\x80\x0d'+body
        live.feed(frame)
        self.assertEqual(events[0],(0x800d,body))
        live.tick(123);self.assertIn(('tick',123),events)
        self.assertIn('publish',events)


if __name__=='__main__':unittest.main()
