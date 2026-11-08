import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tests'))
from reference_fixtures import maps
"""Readability constraints for the opt-in APRS TUI palette."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('aprs_theme', ROOT / 'n810-aprs-theme.py')
theme = importlib.util.module_from_spec(spec)
spec.loader.exec_module(theme)


def luminance(color):
    values = [value / 255 for value in color]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4
              for value in values]
    return sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))


def contrast(a, b):
    low, high = sorted((luminance(a), luminance(b)))
    return (high + .05) / (low + .05)


class ThemeTests(unittest.TestCase):
    def test_terrain_has_color_and_preserves_land_water_unknown_distinction(self):
        colors = theme.REGIONAL + (theme.LOW, theme.HIGH, theme.LAND)
        self.assertTrue(all(0<=channel<=255 for color in colors for channel in color))
        self.assertGreater(theme.WATER[2]-theme.WATER[0],70)
        self.assertGreater(theme.REGIONAL[3][0]-theme.REGIONAL[3][2],60)
        self.assertGreater(luminance(theme.REGIONAL[6]),.7)
        self.assertEqual(len({theme.WATER, theme.LAND, theme.NODATA}), 3)
        self.assertGreater(theme.WATER[2], theme.WATER[1])
        self.assertGreater(theme.LAND[1], theme.LAND[2])
        heights = [luminance(color) for color in theme.REGIONAL[1:7]]
        self.assertEqual(heights, sorted(heights))

    def test_existing_label_foregrounds_keep_strong_contrast(self):
        # Native gray text, mint station labels and gold used-relay labels.
        for foreground in ((173, 182, 181), (147, 207, 165), (196, 191, 140)):
            self.assertGreaterEqual(contrast(foreground, theme.BACKPLATE), 7)
        self.assertGreaterEqual(contrast((11, 16, 21), (221, 228, 223)), 12)
        self.assertGreaterEqual(contrast(theme.SELECTION_TEXT, theme.SELECTION_FILL), 7)

    def test_panel_text_is_readable_over_brightest_terrain(self):
        for color in theme.REGIONAL:
            panel = theme.blend(color, theme.PANEL_TINT, theme.PANEL_OPACITY)
            self.assertGreaterEqual(contrast((221, 228, 223), panel), 7)

    def test_opt_in_wiring_keeps_default_and_foreground_separate(self):
        spec = importlib.util.spec_from_file_location('theme_view', ROOT / 'n810-aprs-view.py')
        view = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(view)
        current, candidate = view.State(), view.State()
        view.init_map(current, str(maps()), 'next')
        view.init_map(candidate, str(maps()), 'next', 'color')
        self.assertIs(current.map_engine.palette, current.map_engine.rgb)
        self.assertEqual(candidate.map_engine.palette.WATER, theme.WATER)
        self.assertEqual(view.label_backplate(current), (14, 21, 18))
        self.assertEqual(view.label_backplate(candidate), theme.BACKPLATE)
        frames = []
        for state in (current, candidate):
            state.map_engine.style = 'rgb'
            viewport = state.map_next.Viewport([47.38, -122.52], 200, 55, 18)
            frame, _ = state.map_engine.prepare(viewport, terrain=True, roads=False)
            frames.append(frame)
            self.assertEqual(state.map_engine.view.key, viewport.key)
        old, new = frames
        water_masks=[[(cell[1]==state.map_engine.palette.WATER,cell[2]==state.map_engine.palette.WATER) for cell in frame]
                     for state,frame in zip((current,candidate),frames)]
        self.assertEqual(*water_masks)
        self.assertGreater(sum(luminance(cell[2]) for cell in new),
                           sum(luminance(cell[2]) for cell in old) * .8)
        # Palette selection does not alter the shared encoder/foreground palette.
        self.assertEqual(candidate.map_engine.rgb.REGIONAL, current.map_engine.rgb.REGIONAL)


if __name__ == '__main__':
    unittest.main()
