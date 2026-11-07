# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""An optimized redraw must use the same theme as ordinary composition."""
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window
import themes

class ThemeRepaint(unittest.TestCase):
    def test_opaque_cache_matches_compositor_for_unstyled_app_text(self):
        for palette in themes.PRESETS:
            h=Host(60,20,[Window('ULS',2,2,30,12,lines=('Callsign','plain text'))])
            h.animate=False;h.shadow_enabled=False;h.window_opacity=1;h.window_fill=True
            h.set_palette(palette)
            w=h.window('ULS');w.styles={0:((0,8,'heading'),)}
            plane=h.opaque_plane(w,w.w,w.h)
            for y in range(w.h):
                for x in range(w.w):
                    self.assertEqual(plane[y][x],h.scene_cell(w.x+x,w.y+y,include_outline=False),(palette,x,y))

    def test_rollup_and_move_repaint_the_exposed_app_consistently(self):
        for palette in themes.PRESETS:
            h=Host(60,20,[Window('ULS',2,2,35,15,lines=('plain text',)),Window('Map',14,1,40,17)])
            h.animate=False;h.shadow_enabled=False;h.window_opacity=1;h.window_fill=True
            h.background_enabled=False;h.show_clock=False;h.show_connectivity=False
            h.set_palette(palette)
            m=h.window('Map');m.layer=(0,0,38,15,[(' ',0)]*(38*15))
            while h.damage:h.flush(2000)
            h.roll('Map');m.layer=None
            while h.damage:h.flush(2000)
            for x in (3,10,15,25,35):
                i=7*h.width+x
                self.assertEqual(h.front[i],h.scene_cell(x,7,include_outline=False),(palette,x))
            h.select('ULS');w=h.window('ULS');h.invalidate(w.rect);w.x=5;h.invalidate(w.rect)
            while h.damage:h.flush(2000)
            for x in (6,12,20,30):
                self.assertEqual(h.front[7*h.width+x],h.scene_cell(x,7,include_outline=False),(palette,x))

if __name__=='__main__' :unittest.main()
