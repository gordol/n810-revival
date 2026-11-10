# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact native-view data and ownership transitions, without a GPU/device."""
from pathlib import Path
import ctypes as C,os,struct,sys,unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window
from cell_text import Glyphs
from native_runtime import select

class RetainedCellView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
        if not cls.path:raise unittest.SkipTest('native build unavailable')
    def setUp(self):
        self.cells=[(chr(65+i%26),1+i%3) for i in range(48)]
        self.w=Window('view',2,2,10,8,layer=(0,0,8,6,self.cells))
        self.h=Host(40,16,[self.w,Window('overlap',3,3,10,8)],ascii=False)
        self.h.animate=False;self.h.background_enabled=False
        self.assertTrue(self.h.enable_native(self.path));self.n=self.h._native
    def view(self):return self.n.cell_view(self.h,self.w,self.h.bounds(self.w))
    def counters(self):return (self.n.layer_cells_sampled,self.n.cell_view_builds,self.n.cell_view_export_bytes,self.n.cell_view_index_allocations)
    def exact(self):
        v=self.view();data,cw,ch,x,y=v;lx,ly,lw,lh,cells=self.w.layer
        left,top=max(0,lx),max(0,ly)
        expected=[]
        for yy in range(ch):
            for xx in range(cw):
                char,ink=cells[(yy+top-ly)*lw+xx+left-lx]
                if self.h.ascii and ord(char)>127:char=':'
                expected.append((yy*cw+xx,ord(char),ink))
        self.assertEqual(list(struct.iter_unpack('=IIQ',data)),expected)
        self.assertEqual((x,y),(self.w.x+1+left,self.w.y+1+top))
        return v
    def test_unchanged_move_overlap_and_palette_do_zero_work(self):
        first=self.exact();before=self.counters()
        for x,y in ((-20,-10),(20,6),(2,2)):
            self.w.x,self.w.y=x,y;self.h.focus='overlap';self.h.tinted=not self.h.tinted
            self.h.window_opacity=.5;self.h.shadow_enabled=not self.h.shadow_enabled
            self.assertIs(self.exact()[0],first[0]);self.assertEqual(self.counters(),before)
        for _ in range(1000):self.assertIs(self.view()[0],first[0])
        self.assertEqual(self.counters(),before)
        self.assertEqual(before,(48,1,48*16,1))
    def test_patch_scroll_replace_resize_and_glyph_policy(self):
        self.exact();self.cells[7]=('!',3);self.h.layer_patch('view',self.w.layer,[7]);self.exact()
        self.cells[:]=self.cells[8:]+self.cells[:8];self.h.layer_patch('view',self.w.layer,None);self.exact()
        fresh=list(self.cells);fresh[0]=('é',1)
        self.h.content('view',1,[],layer=(0,0,8,6,fresh));self.exact()
        self.w.w=7;self.w.h=5;self.exact()
        self.h.ascii=True;self.exact()
        before=self.n.cell_view_builds;self.h.glyphs=Glyphs({'?','A'});self.exact()
        self.assertEqual(self.n.cell_view_builds,before+1)
        self.assertEqual(self.n.cell_view_builds,7)
    def test_hidden_and_rolled_changes_survive_early_returns(self):
        self.exact();generation=self.w.layer_generation;self.w.visible=False
        self.cells[0]=('H',2);self.h.layer_patch('view',self.w.layer,[0])
        self.assertGreater(self.w.layer_generation,generation);self.w.visible=True;self.exact()
        self.w.rolled=True;self.assertIsNone(self.view());generation=self.w.layer_generation
        fresh=list(self.cells);fresh[1]=('R',3)
        self.h.content('view',2,[],layer=(0,0,8,6,fresh))
        self.assertGreater(self.w.layer_generation,generation);self.w.rolled=False;self.exact()
    def test_failed_update_does_not_publish_and_removed_view_retires(self):
        self.exact();old=self.n.cell_views['view']
        self.cells[0]=('X',-1);self.h.layer_patch('view',self.w.layer,[0])
        with self.assertRaises(ValueError):self.view()
        self.assertIs(self.n.cell_views['view'],old)
        self.cells[0]=('X',1);self.h.layer_patch('view',self.w.layer,[0]);self.exact()
        self.h.content('view',3,[],layer=None);self.assertIsNone(self.view());self.assertNotIn('view',self.n.cell_views)

    def test_scene_consumer_replaces_targets_for_content_and_ascii_changes(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
        from gpu_scene import Context
        ctx=object.__new__(Context);ctx.handle=1;ctx.layers={}
        patches=[];created=[];released=[]
        def target(*args):
            created.append(len(created)+10);return created[-1]
        def patch(handle,texture,records,width,height,*args):
            patches.append(C.string_at(records,width*height*16));return 0
        ctx.lib=SimpleNamespace(pocket_scene_window=target,pocket_scene_window_patch=patch)
        ctx.release=released.append
        ctx.platform=SimpleNamespace(host=self.h,renderer=SimpleNamespace(
            layer_key=(),layer_fallback=0,layer_palette=(C.c_uint32*20)()))
        def prepare():
            self.h.invalidate((0,0,self.h.width,self.h.height))
            self.h.flush(10000,serialize=False)
        self.cells[0]=('é',1);self.h.layer_patch('view',self.w.layer,[0]);prepare()
        first=ctx.layer(self.w)
        self.assertEqual(next(struct.iter_unpack('=IIQ',patches[-1]))[1],ord('é'))
        before=self.counters();self.w.x+=3
        self.assertEqual(ctx.layer(self.w),first)
        self.assertEqual(self.counters(),before);self.assertEqual(len(created),1)
        self.h.ascii=True;prepare();second=ctx.layer(self.w)
        self.assertNotEqual(first,second)
        self.assertEqual(next(struct.iter_unpack('=IIQ',patches[-1]))[1],ord(':'))
        self.cells[0]=('!',2);self.h.layer_patch('view',self.w.layer,[0]);prepare()
        third=ctx.layer(self.w)
        self.assertNotEqual(second,third)
        self.assertEqual(next(struct.iter_unpack('=IIQ',patches[-1]))[1:],(ord('!'),2))
        self.assertEqual(released,[first,second])

if __name__=='__main__':unittest.main()
