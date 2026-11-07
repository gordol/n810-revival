"""Native text materials match the portable scene compositor, including overlap."""
from array import array
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window,STYLES
from native_runtime import select
from native_scene import flux
class NativeBlendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
        if not cls.path:raise unittest.SkipTest('native build unavailable')
    def host(self):
        h=Host(32,17,[Window('A',-2,1,23,12,lines=['alpha beta','under text','half ▄ glyph']*4),Window('B',9,5,22,12,lines=['bravo chars','selected row','  spaces   ']*4)])
        h.background_enabled=False;h.animate=False;h.show_clock=False;h.show_connectivity=False
        self.assertTrue(h.enable_native(self.path))
        if not hasattr(h._native.lib,'blend_scene'):self.skipTest('blend kernel unavailable')
        h.background(h.scene_cells(flux(h._native.lib,h.width,h.height,3,False,1.,.15,2)))
        h.window('A').styles={0:((0,5,'heading'),),1:((0,10,'selected'),)}
        h.window('B').styles={1:((0,6,'control'),(4,10,'warning'))}
        return h
    def test_materials_match_portable_scene(self):
        h=self.host();lib=h._native.lib;target=lib.surface(h.width,h.height);dirty=array('I',range(h.width*h.height))
        for style,fill,opacity,show,direction,shadow in [('thin',True,.88,False,'SE',.4),('bare',True,.4,True,'NW',.7),('double',False,.3,True,'SW',.25),('thin',True,1.,True,'E',1.),('thin',True,0.,False,'S',0.)]:
            h.style=style;h.window_fill=fill;h.window_opacity=opacity;h.show_underlying_text=show;h.shadow_direction=direction;h.shadow_enabled=shadow>0;h.shadow_opacity=shadow
            plans=h._native.prepare(h,h.windows,STYLES)[0];dx,dy={'SE':(1,1),'NW':(-1,-1),'SW':(-1,1),'E':(1,0),'S':(0,1)}[direction]
            lib.blend_scene(target,h.backdrop.native_surface,tuple((p,b[0],b[1]) for w,b,p in plans),dirty,int(fill),opacity,int(show),dx,dy,h.shadow_size,shadow)
            for i in range(h.width*h.height):
                expected=h.scene_cell(i%h.width,i//h.width,include_outline=False)
                with self.subTest(style=style,fill=fill,opacity=opacity,point=(i%h.width,i//h.width)):
                    self.assertEqual(lib.get(target,i),(ord(h.glyphs.cell(expected.char,h.ascii)),expected.color))
    def test_semantic_themes_match_portable_materials(self):
        import themes
        h=self.host();lib=h._native.lib;target=lib.surface(h.width,h.height)
        dirty=array('I',range(h.width*h.height))
        for name in themes.PRESETS:
            h.set_palette(name);h.window_opacity=.88;h.shadow_enabled=False
            plans=h._native.prepare(h,h.windows,STYLES)[0]
            lib.blend_scene(target,h.backdrop.native_surface,tuple((p,b[0],b[1]) for w,b,p in plans),dirty,1,.88,0,1,1,1,0.)
            actual=[lib.get(target,i) for i in dirty]
            expected=[h.scene_cell(i%h.width,i//h.width,include_outline=False) for i in dirty]
            self.assertEqual(actual,[(ord(c.char),c.color) for c in expected],name)

    def test_integrated_output_matches_existing_mixed_renderer(self):
        from cell_text import Glyphs
        a,b=self.host(),self.host()
        a._native.supports_blend=lambda host,windows:False
        directions=('SE','S','SW','W','NW','N','NE','E')
        for step in range(16):
            for h in (a,b):
                h.glyphs=Glyphs(set(' ?')) if step%3==0 else Glyphs()
                h.style=('thin','bare','double','rounded')[step%4]
                h.window_fill=step%5!=2;h.window_opacity=(0.,.35,.88,1.)[step//4]
                h.ascii=step%3==1;h.tinted=step%4!=1
                h.show_underlying_text=bool(step%2);h.shadow_direction=directions[step%8]
                h.shadow_size=(.5,1.,2.25,3.)[step%4];h.shadow_opacity=(step%3)/2;h.shadow_enabled=True
                h.focus='A' if step%2 else 'B';h.palette='amber' if step%2 else 'ice'
                h.window('B').rolled=step%5==0
                h.window('A').x=step%5-3
                h.background(h.scene_cells(flux(h._native.lib,h.width,h.height,step,False,1.,.15,2)))
                h.invalidate((0,0,h.width,h.height))
            aa=[];bb=[]
            while a.damage:aa.append(a.flush(64))
            while b.damage:bb.append(b.flush(64,max_seconds=0.))
            self.assertEqual(bb,aa,(step,b.native_error))
            self.assertEqual(b.render_backend,'native_blend')
    def test_overlays_layers_and_pending_resize_keep_portable_path(self):
        h=self.host()
        self.assertTrue(h._native.supports_blend(h,h.windows))
        h.help_lines=['Help'];self.assertFalse(h._native.supports_blend(h,h.windows));h.help_lines=[]
        h.window('B').layer=(0,0,1,1,[('X',0)])
        self.assertFalse(h._native.supports_blend(h,h.windows));h.window('B').layer=None
        h.width+=1
        self.assertFalse(h._native.supports_blend(h,h.windows))
    def test_plain_desktop_uses_native_blend_without_animation(self):
        a,b=self.host(),self.host();a._native.supports_blend=lambda host,windows:False
        for h in (a,b):
            h.backdrop={};h.window_opacity=.88;h.shadow_enabled=True
            h.invalidate((0,0,h.width,h.height))
        aa=[];bb=[]
        while a.damage:aa.append(a.flush(64))
        while b.damage:bb.append(b.flush(64,max_seconds=0.))
        self.assertEqual(bb,aa);self.assertEqual(b.render_backend,'native_blend')
    def test_rejected_inputs_do_not_change_target(self):
        h=self.host();lib=h._native.lib;target=lib.surface(h.width,h.height)
        args=(target,h.backdrop.native_surface,(),array('I',[999999]),1,.8,0,1,1,1,.4)
        with self.assertRaises(IndexError):lib.blend_scene(*args)
        self.assertIsNone(lib.get(target,0))
        with self.assertRaises(ValueError):lib.blend_scene(target,target,(),array('I',[0]),1,.8,0,1,1,1,.4)
if __name__=='__main__':unittest.main()
