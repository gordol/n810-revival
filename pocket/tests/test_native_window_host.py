"""Native retained windows preserve the existing Python preparation contract."""
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window,STYLES
from paint import control_ink
from cell_text import Glyphs
from native_runtime import select
class PortablePlan:
    def __init__(self,lib):self.lib=lib
    def __getattr__(self,name):
        if name=='window_host':raise AttributeError(name)
        return getattr(self.lib,name)
class NativeWindowHost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library=os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
        if cls.library is None:raise unittest.SkipTest('explicit native build unavailable')
    def make(self,native):
        h=Host(100,30,[Window('System',2,2,50,17),Window('Connections',20,6,60,18)])
        h.background_enabled=False;h.shadow_enabled=False;h.window_opacity=1;h.animate=False;h.show_clock=False;h.show_connectivity=False
        self.assertTrue(h.enable_native(self.library),h.native_error)
        if not hasattr(h._native.lib,'window_host'):self.skipTest('native host kernel unavailable')
        if not native:h._native.lib=PortablePlan(h._native.lib)
        return h
    def compare(self,hosts,full=False):
        output=[h.flush(3000) for h in hosts]
        self.assertEqual(output[0],output[1])
        indices=range(len(hosts[0].front)) if full else range(0,len(hosts[0].front),97)
        self.assertEqual([hosts[0].front[i] for i in indices],[hosts[1].front[i] for i in indices])
        self.assertTrue(all(h.render_backend=='native' for h in hosts))
    def test_content_styles_font_focus_geometry_and_chrome_match(self):
        hosts=[self.make(False),self.make(True)];self.compare(hosts,full=True)
        for step in range(80):
            for h in hosts:
                name=('System','Connections')[step%2]
                lines=('Observed host: n810 · connected','Sample age: '+str(step)+'s','Arrow → / wide 中 / combining e\u0301 / tab\t',*('cached row '+str(i) for i in range(step%12)))
                h.content(name,step,lines,spans=((0,-3,8,'heading'),(1,0,10,'selected'),(2,4,200,'match')) if step%3 else ())
                if step%7==0:h.focus=name
                if step%9==0:h.ascii=not h.ascii
                if step%11==0:h.style=('thin','double','rounded')[step%3]
                if step%13==0:h.palette=('amber','ice')[step%2]
                if step%17==0:h.glyphs=Glyphs(' ?→·ABCabcdefghijklmnopqrstuvwxyz0123456789:/-[]')
                if step%19==0:h.window(name).w=40+step%20
                if step%23==0:h.window(name).rolled=not h.window(name).rolled
                if step%29==0:h.window_controls=('left','right')[step%2]
                h.invalidate((0,0,h.width,h.height))
            self.compare(hosts)
    def test_in_place_style_edits_and_removal_are_seen(self):
        hosts=[self.make(False),self.make(True)]
        for h in hosts:h.content('System',1,('before','still'),spans=((0,0,4,'input'),))
        self.compare(hosts)
        for h in hosts:h.window('System').styles[0][0]=(0,4,'warning');h.invalidate((0,0,100,30))
        self.compare(hosts)
        for h in hosts:h.content('System',2,('after',));h.invalidate((0,0,100,30))
        self.compare(hosts)
    def test_unchanged_rows_are_retained_and_window_close_releases_plan(self):
        h=self.make(True);h.content('System',0,tuple('Static row '+str(i) for i in range(15)));h.flush(3000)
        before=h._native.row_builds
        h.content('System',1,('New first row',*h.window('System').lines[1:]));h.flush(3000)
        self.assertEqual(h._native.row_builds-before,1)
        h.window('System').opened=h.window('System').visible=False;h.invalidate((0,0,100,30));h.flush(3000)
        self.assertNotIn('System',h._native.planes)
    def test_large_style_bounds_match_existing_clipping(self):
        hosts=[self.make(False),self.make(True)]
        for h in hosts:h.content('System',1,('bounds',),spans=((0,-10**100,10**100,'accent'),(0,10**100,3,'input')))
        self.compare(hosts)
    def test_malformed_native_plans_raise_without_corrupting_lifetime(self):
        h=self.make(True);lib=h._native.lib
        args=[None,12,4,'System',('body',),(),STYLES['rounded'],2,Glyphs(),False,control_ink,'ice',True,('context',)]
        for index,value in ((0,object()),(1,0),(2,0),(4,(False,)),(5,((0,((0,'bad','input'),)),)),(6,('bad',))):
            changed=list(args);changed[index]=value
            with self.subTest(index=index),self.assertRaises((ValueError,TypeError,OverflowError)):
                lib.window_host(*changed)
        plan,plane,inks,built=lib.window_host(*args)
        self.assertTrue(inks);self.assertEqual(built,4)
        self.assertEqual(lib.get(plane,0),(ord('S'),2))
        del plan,plane
if __name__=='__main__':unittest.main()
