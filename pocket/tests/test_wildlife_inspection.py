"""Exercise the graphical Wildlife catalog, touch controls and pose interpolation."""
import hashlib
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

POCKET = Path(__file__).resolve().parents[1]
for directory in ('graphics', 'shell', 'shell/apps/landscape-lab'):
    sys.path.insert(0, str(POCKET / directory))

from wildlife_pixels import NAMES, PHOTOS, PixelWildlife, pose, reference_photo


class WildlifeInspectionTests(unittest.TestCase):
    def test_offline_touch_browsing(self):
        window = SimpleNamespace(opened=True, rolled=False)
        app = PixelWildlife(SimpleNamespace(focus='Wildlife', window=lambda _: window,
                                            shown=lambda _: True))
        app.open()
        for species, name in NAMES.items():
            self.assertEqual(app.lines()[0], name)
            self.assertTrue(app.photo)
            self.assertTrue(name.isascii())
            width, height, pixels = reference_photo(species)
            self.assertEqual(len(pixels), width * height * 2)
            asset = PHOTOS / (species + '.rgb565.gz')
            self.assertEqual(hashlib.sha256(asset.read_bytes()).hexdigest(),
                             app.credits[species]['digest'])
            self.assertTrue(app.pointer(75, app.height - 1, 100))
            self.assertFalse(app.photo)
            self.assertTrue(app.pointer(30, app.height - 1, 100))
            self.assertTrue(app.photo)
            self.assertTrue(app.pointer(10, app.height - 1, 100))
        self.assertEqual(app.species, 'marmot')

    def test_pose_interpolation(self):
        for species in NAMES:
            with self.subTest(species=species):
                points, faces = pose(species, 0, False)
                count = len(points) // 4
                self.assertGreater(count, 0)
                self.assertLess(max(max(faces[i::4]) for i in range(3)), count)
                for phase in (1, 2):
                    other, triangles = pose(species, phase, False)
                    self.assertEqual(faces, triangles)
                    self.assertEqual(len(points), len(other))
                    self.assertNotEqual(points, other)
                    self.assertTrue(all(map(math.isfinite, other)))
