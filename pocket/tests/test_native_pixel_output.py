"""Pixel consumers retain exact cells without paying for terminal serialization."""
from array import array
from pathlib import Path
import os,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window
from native_cells import load
from native_runtime import select

class PixelOutput(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
        if not cls.path:raise unittest.SkipTest('native build unavailable')
        cls.lib=load(cls.path)

    def test_native_composition_parity_and_atomic_rejection(self):
        lib=self.lib;plane=lib.surface(32,8);ansi=lib.surface(32,8);pixels=lib.surface(32,8)
        for i in range(256):lib.set(plane,i,ord('A')+i%26,(1<<48)|(i*1234567&0xffffffffffff))
        dirty=array('I',range(256));args=(((plane,0,0),),dirty,(),0,0)
        text,changed=lib.flush(ansi,*args)
        self.assertTrue(text)
        self.assertEqual(lib.compose(pixels,*args),('',changed))
        self.assertEqual([lib.get(pixels,i) for i in dirty],[lib.get(ansi,i) for i in dirty])
        self.assertEqual(lib.compose(pixels,*args),('',0))
        lib.set(plane,0,ord('!'),1)
        before=[lib.get(pixels,i) for i in dirty]
        with self.assertRaises(ValueError):lib.compose(pixels,((plane,0,0),),array('I',[0,256]),(),0,0)
        self.assertEqual([lib.get(pixels,i) for i in dirty],before)
        self.assertEqual(lib.compose_budget(pixels,((plane,0,0),),dirty,(),0,0,None,0.),('',1,64))

    def host(self,native):
        h=Host(40,16,[Window('View',2,2,25,10,lines=['exact cells','with colors'])],ascii=True)
        h.background_enabled=False;h.animate=False;h.show_clock=False;h.show_connectivity=False
        if native:self.assertTrue(h.enable_native(self.path))
        h.observe_composition=True
        return h

    def test_independent_frontends_and_budget_parity(self):
        for native in (False,True):
            with self.subTest(native=native):
                terminal=self.host(native);pixels=self.host(native)
                for step in range(4):
                    for h in (terminal,pixels):
                        h.window('View').x=2+step;h.invalidate((0,0,40,16))
                    while terminal.damage or pixels.damage:
                        a=terminal.flush(64,max_seconds=.1)
                        b=pixels.flush(64,max_seconds=.1,serialize=False)
                        self.assertEqual(b[0],'');self.assertEqual(a[1:],b[1:])
                        self.assertEqual(list(terminal.front),list(pixels.front))
                        self.assertEqual(list(terminal.composed_indices),list(pixels.composed_indices))
                self.assertEqual(pixels.flush(1000,serialize=False),('',0,0))
                self.assertEqual(terminal.flush(1000),('',0,0))

if __name__=='__main__':unittest.main()
