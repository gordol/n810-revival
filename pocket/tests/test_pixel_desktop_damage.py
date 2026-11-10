"""Native desktop model boundaries; no hardware/device ownership required."""
from pathlib import Path
import os,struct,sys,unittest
from types import SimpleNamespace
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'graphics'),str(Path(__file__).resolve().parents[1]/'shell')]
from core import Host
from effects import pnw
from pixel_scene import Context,landscape_marks

class PixelDesktopTests(unittest.TestCase):
    def context(self):
        h=Host(100,28,[]);h.animate=False;h.background_async=False
        if os.environ.get("POCKET_TEST_NATIVE"):self.assertTrue(h.enable_native(os.environ["POCKET_TEST_NATIVE"]))
        h.clock=lambda:120.;h.effect_epoch=0
        r=SimpleNamespace(layer_palette=[0]*16,prepare_palette=lambda:None)
        c=Context.__new__(Context);c.platform=SimpleNamespace(host=h,renderer=r,dirty=False)
        c.pending_damage=None;c.full_damage=False;c.background=None;c.background_key=None
        c.landscape=None;c.landscape_base=None;c.panels={};h.render_context=c
        return c,h
    def test_pnw_switch_and_return_preserve_all_artwork(self):
        c,h=self.context()
        h.set_effect('flux');h.set_background_enabled(True);c.prepare_model()
        h.set_effect('pnw');c.prepare_model()
        scene=pnw(h.width,h.height,h.background_step,h.ascii,h.weather,seed=h.scene_seed,nature_age=h.nature_age())
        for packed,layer in zip(c.landscape,(scene.base,scene.overlay)):
            decoded={((i%h.width),(i//h.width)):(chr(g),ink) for i,g,ink in struct.iter_unpack('=IIQ',packed)}
            self.assertEqual(decoded,layer)
        base=c.landscape[0];c.update_background(h,h.background_step+1)
        self.assertIs(c.landscape[0],base)
        h.set_background_enabled(False);c.prepare_model()
        h.set_background_enabled(True);c.prepare_model()
        h.set_effect('flux');c.prepare_model()
        self.assertTrue(c.full_damage)
    def test_damage_survives_model_consumption_and_panels_skip_identical_text(self):
        c,h=self.context();h.set_background_enabled(False);c.prepare_model()
        c.full_damage=False;c.pending_damage=None;c.platform.dirty=False
        h.shadow_enabled=False;h.invalidate((3,4,2,1));c.prepare_model()
        self.assertFalse(h.damage);ox,oy=h.origin
        self.assertEqual(c.pending_damage,((3+ox)*8,(4+oy)*16,16,16))
        self.assertTrue(c.panel_text(0,0,'Battery',1,2));c.pending_damage=None
        self.assertFalse(c.panel_text(0,0,'Battery',1,2));self.assertIsNone(c.pending_damage)
        self.assertTrue(c.panel_text(0,0,'Bat',1,2));self.assertEqual(c.pending_damage,(0,0,56,16))

if __name__=='__main__':unittest.main()
