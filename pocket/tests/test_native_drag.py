"""Pointer outlines use retained native surfaces without changing gesture results."""
from array import array
import os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window
from native_runtime import select
class DragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path=os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
        if not cls.path:raise unittest.SkipTest('native build unavailable')
    def host(self,reference=False,alpha=False,ascii=False):
        h=Host(70,25,[Window('Other',1,1,43,18,lines=['Other content']*16),Window('System',14,4,40,15,lines=['CPU 35%','Battery 65%']*7)],ascii=ascii)
        h.background_enabled=False;h.animate=False;h.snap_windows=False;h.window_opacity=.88 if alpha else 1.;h.shadow_enabled=alpha;h.show_clock=False;h.show_connectivity=False
        self.assertTrue(h.enable_native(self.path))
        if not hasattr(h._native.lib,'outline'):self.skipTest('native outline unavailable')
        if reference:h._native.supports_outline=lambda host:False
        return h
    def test_move_resize_release_and_cancel_match_portable_output(self):
        for resize,alpha,ascii,cancel in ((False,False,False,False),(True,False,True,False),(False,True,False,False),(True,True,False,True)):
            a,b=self.host(True,alpha,ascii),self.host(False,alpha,ascii)
            for h in (a,b):
                while h.damage:h.flush(1750)
                w=h.window('System');x,y=(w.x+w.w-1,w.y+w.h-1) if resize else (w.x+10,w.y)
                h.pointer(0,x,y);self.assertIsNotNone(h.drag)
            for dx,dy in ((0,0),(1,1),(3,2),(-4,-2),(8,3)):
                outputs=[]
                for h in (a,b):
                    h.pointer(32,x+dx,y+dy);parts=[]
                    while h.damage or h.latest is not None:parts.append(h.flush(64,max_seconds=0.))
                    outputs.append(parts)
                self.assertEqual(outputs[0],outputs[1],(resize,alpha,ascii,dx,dy,b.native_error))
                self.assertEqual(b.render_backend,'native_blend' if alpha else 'native')
            for h in (a,b):
                if cancel:h.finish(False)
                else:h.pointer(0,x+dx,y+dy,True)
            self.assertEqual(a.window('System').rect,b.window('System').rect)
            aa=[];bb=[]
            while a.damage:aa.append(a.flush(64))
            while b.damage:bb.append(b.flush(64))
            self.assertEqual(aa,bb)
    def test_held_text_boundary_is_not_fragmented_after_setup_uses_budget(self):
        reference,candidate=self.host(),self.host()
        for h in (reference,candidate):
            while h.damage:h.flush(1750)
            w=h.window('System');h.pointer(0,w.x+10,w.y);h.pointer(32,w.x+13,w.y+2)
        expected=reference.flush(1750)
        actual=candidate.flush(1750,max_seconds=0.)
        self.assertEqual(actual,expected)
        self.assertFalse(candidate.damage)
        self.assertEqual(candidate.render_backend,'native')

    def test_mutable_cell_layers_keep_bounded_sampling(self):
        h=self.host();w=h.window('System')
        h.layer_patch(w.name,(0,0,5,3,[('x',0)]*15),None)
        while h.damage:h.flush(1750)
        h.pointer(0,w.x+10,w.y);h.pointer(32,w.x+13,w.y+2)
        _,_,computed=h.flush(1750,max_seconds=0.)
        self.assertEqual(computed,64)
        self.assertTrue(h.damage)

    def test_gpu_drag_outline_exports_only_populated_border(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
        from gpu_scene import overlay_records
        import struct
        h=self.host();w=h.window('System')
        h.pointer(0,w.x+10,w.y);h.pointer(32,w.x+13,w.y+2)
        h._native.prepare_outline(h)
        pointer,_,_=h._native.outline_layer
        cols,rows,_=h._native.outline_plane[0]
        with self.assertRaises(ValueError):
            h._native.lib.export_cells(pointer,array('I',range(cols*rows)))
        with self.assertRaises(ValueError):h._native.lib.export_cells(pointer,array('I',[cols*rows]),True)
        records=overlay_records(h._native.lib,pointer,cols,rows,True)
        ids=[v[0] for v in struct.iter_unpack('=IIQ',records)]
        expected=list(range(cols*rows))
        self.assertEqual(ids,expected)
        self.assertEqual(struct.unpack_from('=IIQ',records,(cols+1)*16),(cols+1,32,0))
        self.assertEqual(len(ids),len(set(ids)))
        self.assertIsNone(h._native.lib.get(pointer,cols+1))
        h.pointer(0,w.x+13,w.y+2,True)
        self.assertIsNone(h.drag)

    def test_hollow_plane_does_not_erase_underlying_cells(self):
        h=self.host();lib=h._native.lib
        outline=lib.outline(12,4,tuple(map(ord,'++++-|')))
        self.assertIsNone(lib.get(outline,13))
        self.assertEqual(lib.get(outline,0),(ord('+'),3))
        base=lib.surface(12,4)
        for row in range(4):lib.row(base,row,'underlying!!',0)
        front=lib.surface(12,4)
        lib.flush(front,((outline,0,0),(base,0,0)),array('I',range(48)),((0,'\x1b[0m'),(3,'\x1b[0m')),0,0)
        self.assertEqual(lib.get(front,13),(ord('n'),0))
        with self.assertRaises(ValueError):lib.outline(1,4,tuple(map(ord,'++++-|')))
if __name__=='__main__':unittest.main()
