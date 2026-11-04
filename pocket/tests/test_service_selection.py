import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'shell'))
from service_selection import Selection
from app_registry import Registry


class SelectionTests(unittest.TestCase):
    def test_local_auto_skips_missing_and_external_configuration(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            calls=[]
            selection=Selection(SimpleNamespace(configure_reticulum=lambda **kw:calls.append(kw)),tmp)
            self.addCleanup(selection.close)
            for config in (None,dict(socket='/tmp/forwarded-owner.sock')):
                if config is not None:Path(tmp,'reticulum-owner.json').write_text(json.dumps(config))
                self.assertTrue(selection.connect('local-auto'))
                self.wait(lambda:not selection.busy)
                self.assertEqual(selection.error,'');self.assertIsNone(selection.provider)
            self.assertFalse(calls)

    def test_local_auto_attaches_idle_local_owner_without_connect_request(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            Path(tmp,'reticulum-owner.json').write_text(json.dumps(dict(mode='local',state=tmp+'/owner',interpreter=sys.executable,station='test',carriers=[dict(type='tcp',host='127.0.0.1',port=7777)])))
            calls=[];requests=[]
            provider=SimpleNamespace(close=lambda:None,request=lambda *args:requests.append(args))
            def factory(**kw):calls.append(kw);return provider
            selection=Selection(SimpleNamespace(configure_reticulum=factory),tmp)
            self.addCleanup(selection.close)
            self.assertTrue(selection.connect('local-auto'));self.wait(lambda:not selection.busy)
            self.assertIs(selection.provider,provider);self.assertEqual(len(calls),1);self.assertFalse(requests)

    def wait(self, predicate):
        end = time.monotonic()+3
        while not predicate():
            if time.monotonic()>end: self.fail('Selection did not settle')
            time.sleep(.005)

    def test_remote_selection_keeps_gateway_until_final_detach(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            path=str(Path(tmp)/'owner.sock');listener=socket.socket(socket.AF_UNIX);listener.bind(path);self.addCleanup(listener.close)
            closed=[]
            def provider(name):
                r,w=socket.socketpair()
                return SimpleNamespace(path=path,readable=r,drain=lambda:None,snapshot=lambda:dict(version=1,owner_online=True),
                    close=lambda:(closed.append(name),r.close(),w.close()),remote=lambda peer:provider(peer))
            gateway=provider('gateway')
            selection=Selection(SimpleNamespace(configure_reticulum=lambda **kw:provider('borrowed')),tmp,initial=gateway)
            self.addCleanup(selection.close)
            selection.connect('peer','first');self.wait(lambda:not selection.busy);selection.drain()
            self.assertIs(selection.carrier,gateway);self.assertFalse(closed)
            selection.connect('peer','second');self.wait(lambda:not selection.busy);selection.drain()
            self.wait(lambda:'first' in closed);self.assertNotIn('gateway',closed)
            selection.connect('socket',path);self.wait(lambda:not selection.busy);selection.drain()
            self.assertIs(selection.provider,gateway);self.assertIsNone(selection.carrier)
            self.wait(lambda:'second' in closed and 'borrowed' in closed);self.assertNotIn('gateway',closed)
            selection.disconnect();selection.drain();self.wait(lambda:'gateway' in closed)
            self.assertEqual(closed.count('gateway'),1)

    def test_switch_and_cancel_preserve_other_provider(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            listener = socket.socket(socket.AF_UNIX); self.addCleanup(listener.close)
            path = str(Path(tmp)/'owner.sock'); listener.bind(path)
            closed = []
            def factory(**options):
                r,w = socket.socketpair()
                return SimpleNamespace(readable=r,drain=lambda:None,snapshot=lambda:dict(version=1,owner_online=True),
                    close=lambda:(closed.append(True),r.close(),w.close()),request=lambda a,p:'accepted')
            registry = SimpleNamespace(configure_reticulum=factory)
            a,b = Selection(registry,tmp),Selection(registry,tmp)
            self.addCleanup(a.close);self.addCleanup(b.close)
            self.assertIsNone(a.pool)
            a.connect('socket',path);b.connect('socket',path)
            self.wait(lambda:not a.busy and not b.busy)
            self.assertTrue(a.snapshot()['owner_online']);self.assertTrue(b.snapshot()['owner_online'])
            self.assertEqual(len(a.readiness_sources(a.drain)),2)
            a.disconnect();a.drain()
            self.assertFalse(a.snapshot()['owner_online']);self.assertTrue(b.snapshot()['owner_online'])
            self.wait(lambda:len(closed)==1)

    def test_late_local_start_is_closed_after_cancel(self):
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            p=Path(tmp);(p/'reticulum-owner.json').write_text(json.dumps(dict(mode='external',socket='/tmp/fixture.sock')))
            started,release,closed=threading.Event(),threading.Event(),threading.Event()
            def factory(**options):
                started.set();release.wait(2)
                return SimpleNamespace(close=closed.set)
            selection=Selection(SimpleNamespace(configure_reticulum=factory),p);self.addCleanup(selection.close)
            selection.connect('local');self.assertTrue(started.wait(1));selection.disconnect()
            self.assertFalse(selection.connect('local'))
            release.set();self.assertTrue(closed.wait(1));self.assertIsNone(selection.provider)

    def test_owner_cleanup_failure_is_published(self):
        def fail(): raise RuntimeError('radio shutdown unconfirmed')
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            selection=Selection(None,tmp,initial=SimpleNamespace(close=fail))
            self.addCleanup(selection.close)
            selection.disconnect();selection.drain()
            self.wait(lambda:bool(selection.error))
            self.assertIn('radio shutdown unconfirmed',selection.error)
            self.assertIsNone(selection.provider)

if __name__=='__main__':unittest.main()
