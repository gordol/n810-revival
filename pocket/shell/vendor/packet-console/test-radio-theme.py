"""Application colors use extended slots and release them when the view closes."""
import importlib.util,io,unittest
from pathlib import Path
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('radio_theme',Path(__file__).with_name('n810-radio-theme.py'))
theme=importlib.util.module_from_spec(spec);spec.loader.exec_module(theme)
class ThemeTests(unittest.TestCase):
    def tearDown(self):theme._active=False
    def test_extended_slots_and_exact_rgb_values(self):
        out=io.StringIO()
        with patch.object(theme.curses,'COLORS',256,create=True),patch.object(theme.sys,'stdout',out),patch.object(theme.atexit,'register'):
            theme.activate()
            for name,rgb in theme.COLORS.items():
                self.assertGreaterEqual(theme.SLOTS[name],16)
                self.assertIn('%d;#%s'%(theme.SLOTS[name],rgb),out.getvalue())
                self.assertEqual(theme.color(name),theme.SLOTS[name])
            before=out.getvalue();theme.activate();self.assertEqual(out.getvalue(),before)
    def test_close_restores_only_application_slots(self):
        out=io.StringIO();theme._active=True
        with patch.object(theme.sys,'stdout',out):
            theme.deactivate();first=out.getvalue();theme.deactivate()
        self.assertEqual(first,'\x1b]104;'+ ';'.join(map(str,theme.SLOTS.values()))+'\x1b\\')
        self.assertEqual(out.getvalue(),first);self.assertFalse(theme._active)
    def test_small_palette_uses_terminal_defaults(self):
        with patch.object(theme.curses,'COLORS',16,create=True),patch.object(theme.sys,'stdout',io.StringIO()) as out:
            theme.activate();self.assertEqual(out.getvalue(),'')
            for name,value in theme.FALLBACK.items():self.assertEqual(theme.color(name),value)
if __name__=='__main__':unittest.main()
