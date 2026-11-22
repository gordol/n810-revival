"""Seeded behavior through the registered slide's clock and render paths."""
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'shell'))
from app_registry import discover
from cell_text import RICH
from paint import BOLD_RGB, valid_ink


class CellsSimulation(unittest.TestCase):
    def test_denser_terminal_resamples_the_same_world(self):
        app = discover().entries['cells'].factory(SimpleNamespace(ascii=False, glyphs=RICH))
        self.addCleanup(app.close)
        before = (app.world.width, app.world.height, app.world.time,
                  [(c.x,c.y,c.radius) for c in app.world.cells])
        self.assertTrue(app.fill)
        original = app.layer()
        app.width *= 2
        app.height = (app.height-1)*2+1
        dense = app.layer()
        self.assertEqual(len(dense[4]),len(original[4])*4)
        self.assertGreater(len({cell.color & 0xffffff for cell in dense[4]}),64)
        self.assertTrue(any(cell.color & BOLD_RGB for cell in dense[4]))
        self.assertTrue(all(valid_ink(cell.color) for cell in dense[4]))
        self.assertEqual(before,(app.world.width,app.world.height,app.world.time,
                                 [(c.x,c.y,c.radius) for c in app.world.cells]))
        app.key('f')
        self.assertNotEqual(app.layer()[4], dense[4])

    def test_engulfment_and_division_survive_presentation(self):
        window = SimpleNamespace(rolled=False)
        host = SimpleNamespace(window=lambda name: window, shown=lambda w: True,
                               bounds=lambda w: (0,0,90,27), origin=(0,0),
                               ascii=False, glyphs=RICH)
        app = discover().entries['cells'].factory(host)
        self.addCleanup(app.close)
        world = app.world
        initial_cells = len(world.cells)
        states = set()
        for _ in range(6*90):
            app.deadline = 0
            app.poll()
            states.update(cell.state.value for cell in world.cells)
        self.assertTrue({'approach','enclose','digest','divide'} <= states)
        self.assertGreater(world.engulfed,0)
        self.assertGreater(len(world.cells),initial_cells)
        self.assertEqual(world.divisions, len(world.cells)-initial_cells)
        app.key(' ')
        before = world.time
        app.poll()
        self.assertEqual(len(app.layer()[4]),88*24)
        app.pixel_view = True
        stained = app.render_image()[0]
        self.assertEqual(len(stained),88*8*24*16*2)
        app.key('f')
        self.assertNotEqual(stained,app.render_image()[0])
        self.assertEqual(world.time,before)

    def test_close_releases_world_and_slide_caches(self):
        app = discover().entries['cells'].factory(SimpleNamespace(ascii=False, glyphs=RICH))
        slide = sys.modules[type(app).__module__]
        app.layer()
        self.assertGreater(slide.stain_tile.cache_info().currsize, 0)
        app.close()
        self.assertIsNone(app.world)
        self.assertEqual(slide.stain_tile.cache_info().currsize, 0)
        self.assertIsNone(app.render_image())
