from pathlib import Path
import selectors
import socket
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from app_readiness import AppReadiness

class SharedReadinessTests(unittest.TestCase):
    def test_one_provider_wakes_both_views_without_duplicate_registration(self):
        read,write=socket.socketpair();self.addCleanup(read.close);self.addCleanup(write.close)
        selector=selectors.DefaultSelector();self.addCleanup(selector.close)
        calls=[]
        def first():read.recv(1);calls.append('connection')
        def second():calls.append('application')
        forms=[SimpleNamespace(readiness_sources=lambda:((read,first),)),SimpleNamespace(readiness_sources=lambda:((read,second),))]
        readiness=AppReadiness(selector);readiness.sync(forms);write.send(b'x')
        ready=selector.select(.1);self.assertEqual(len(ready),1);ready[0][0].data.callback()
        self.assertEqual(calls,['connection','application'])
        readiness.sync(forms[1:]);write.send(b'x');selector.select(.1)[0][0].data.callback()
        self.assertEqual(calls[-1],'application');readiness.close()

if __name__=='__main__':unittest.main()
