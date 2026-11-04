"""Retained draw metadata must follow edits and must not retain app owners."""
from pathlib import Path
import gc,selectors,socket,sys,unittest,weakref
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from panel import Panels
from app_readiness import AppReadiness

class RenderPassReuseTests(unittest.TestCase):
    def test_minimize_targets_follow_hit_edits_origin_names_and_fallback(self):
        panels=Panels();panels.layout(100,30)
        p=panels.panels[0];p.hits=[(3,29,5,'One'),(20,29,4,'key:,')]
        expected={'One':(3,28,12,1),'Two':(20,28,12,1)}
        self.assertEqual(panels.minimize_targets(('One','Two'),(0,1)),expected)
        result=panels.minimize_targets(('One','Two'),(0,1));result.clear()
        self.assertEqual(panels.minimize_targets(('One','Two'),(0,1)),expected)
        p.hits[0]=(4,28,16,'One')
        self.assertEqual(panels.minimize_targets(('One',),(2,3)),{'One':(2,25,16,1)})
        p.hits.clear();p.rect=(7,20,30,2)
        self.assertEqual(panels.minimize_targets(('Other',),(2,3)),{'Other':(5,17,12,1)})

    def test_readiness_reuses_stable_listeners_but_replaces_callbacks_and_errors(self):
        read,write=socket.socketpair();self.addCleanup(read.close);self.addCleanup(write.close)
        selector=selectors.DefaultSelector();self.addCleanup(selector.close)
        calls=[]
        class Form:
            def __init__(self):self.callback=self.first;self.readiness_error=self.error
            def first(self):calls.append('first');raise ValueError('expected')
            def second(self):calls.append('second');raise ValueError('expected')
            def error(self,error):calls.append('error')
            def other_error(self,error):calls.append('other error')
            def readiness_sources(self):return ((read,self.callback),)
        a=Form();b=Form();ready=AppReadiness(selector)
        ready.sync((a,b));key=selector.get_key(read)
        ready.sync((a,b));self.assertIs(selector.get_key(read).data,key.data)
        a.callback=a.second;a.readiness_error=a.other_error
        ready.sync((a,b));selector.get_key(read).data.callback()
        self.assertEqual(calls,['second','other error','first','error'])
        ref=weakref.ref(a);del a;gc.collect();self.assertIsNone(ref())
        ready.sync((b,));calls.clear();selector.get_key(read).data.callback()
        self.assertEqual(calls,['first','error'])
        ready.close();self.assertEqual(len(selector.get_map()),0)

class IntegerReadinessTests(unittest.TestCase):
    def test_draw_only_rearms_reused_integer_descriptor(self):
        import os
        read,write=socket.socketpair();self.addCleanup(write.close)
        selector=selectors.DefaultSelector();self.addCleanup(selector.close)
        fd=read.fileno();calls=[]
        class Form:
            def ready(self):calls.append(os.read(fd,1))
            def readiness_sources(self):return ((fd,self.ready),)
        form=Form();readiness=AppReadiness(selector);readiness.sync((form,))
        read.close()
        replacement,peer=socket.socketpair();self.addCleanup(peer.close)
        if replacement.fileno()!=fd:
            os.dup2(replacement.fileno(),fd);replacement.close()
            self.addCleanup(os.close,fd)
        else:self.addCleanup(replacement.close)
        readiness.rearm_integers();peer.send(b'x')
        events=selector.select(.1);self.assertEqual(len(events),1)
        events[0][0].data.callback();self.assertEqual(calls,[b'x'])
        readiness.close()

if __name__=='__main__':unittest.main()
