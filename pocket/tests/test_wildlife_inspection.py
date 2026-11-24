"""Exercise the graphical Wildlife catalog, touch controls and pose interpolation."""
from array import array
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

POCKET = Path(__file__).resolve().parents[1]
for directory in ('graphics', 'shell', 'shell/apps/landscape-lab'):
    sys.path.insert(0, str(POCKET / directory))

from pnw_species import REGIONAL
from wildlife_pixels import FOX_ASSETS, FOX_FRAMES, NAMES, PixelWildlife, pose


class WildlifeInspectionTests(unittest.TestCase):
    def test_offline_touch_browsing(self):
        window = SimpleNamespace(opened=True, rolled=False)
        app = PixelWildlife(SimpleNamespace(focus='Wildlife', window=lambda _: window,
                                            shown=lambda _: True))
        app.open()
        for species, name in NAMES.items():
            self.assertEqual(app.lines()[0], name)
            self.assertEqual(app.species, species)
            self.assertTrue(app.pointer(30, app.height - 1, 100))
            self.assertGreater(app.yaw, 0)
            self.assertTrue(app.pointer(50, app.height - 1, 100))
            self.assertLess(app.zoom, 1)
            for playing in (False, True):
                self.assertTrue(app.pointer(70, app.height - 1, 100))
                self.assertEqual(app.playing, playing)
            self.assertTrue(app.pointer(10, app.height - 1, 100))
        self.assertEqual(app.species, 'marmot')

    def test_rainier_uses_regional_wildlife_meshes(self):
        from rainier_pixels import ENCOUNTERS, append_animals

        self.assertEqual({entry[0] for entry in ENCOUNTERS}, set(NAMES) - {'arctic_fox','coho_salmon','chinook_salmon'})
        vertices = array('f')
        indices, spans = append_animals(vertices)
        for (species, _, _, scale), (first, stride, frames, offset, count) in zip(ENCOUNTERS, spans):
            with self.subTest(species=species):
                for frame in range(frames):
                    points, faces = pose(species, frame, False, species in REGIONAL)
                    self.assertEqual(count, len(faces) // 4 * 3)
                    for triangle in (0, len(faces) // 8, len(faces) // 4 - 1):
                        vertex, _, _, color = faces[4 * triangle:4 * triangle + 4]
                        x, y, z, light = points[4 * vertex:4 * vertex + 4]
                        start = 7 * (first + frame * stride + indices[offset + 3 * triangle])
                        rgb = [((color >> shift) & 255) * light / 255 for shift in (16, 8, 0)]
                        for actual, expected in zip(vertices[start:start + 6], (x * scale, y * scale, z * scale, *rgb)):
                            self.assertAlmostEqual(actual, expected, places=6)

    def test_pose_interpolation(self):
        for species in NAMES:
            with self.subTest(species=species):
                points, faces = pose(species, 0, False)
                count = len(points) // 4
                self.assertGreater(count, 0)
                self.assertLess(max(max(faces[i::4]) for i in range(3)), count)
                for phase in range(1, FOX_FRAMES if species in FOX_ASSETS else 3):
                    other, triangles = pose(species, phase, False)
                    self.assertEqual(faces, triangles)
                    self.assertEqual(len(points), len(other))
                    self.assertNotEqual(points, other)
                    self.assertTrue(all(map(math.isfinite, other)))
