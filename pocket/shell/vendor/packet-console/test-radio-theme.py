"""Radio palette selection and terminal restoration."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('theme',Path(__file__).with_name('n810-radio-theme.py'))
theme=importlib.util.module_from_spec(spec);spec.loader.exec_module(theme)

class ThemeTests(unittest.TestCase):
    def test_rgb_palette(self):
        data=theme.sequence(theme.PALETTE)
        for index,rgb in enumerate(theme.PALETTE):
            self.assertIn(('%d;#%s'%(index,rgb)).encode(),data)
        self.assertIn(b'\x1b]11;#0b1015\x1b\\',data)
        self.assertEqual(theme.PALETTE[theme.TERRAIN['water']],'193f59')
        self.assertEqual(theme.PALETTE[theme.TERRAIN['summit']],'adb6b5')
    def test_console_palette_round_trip(self):
        original=bytes(range(48))
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'palette';path.write_bytes(original)
            with patch.object(theme,'CONSOLE_PALETTE',path):
                data=theme.reset_sequence(True)
                self.assertIn(b'\x1b]P0000102',data)
                self.assertIn(b'\x1b]Pf2d2e2f',data)
    def test_restore_on_window_change_and_detach(self):
        rows='/dev/pts/8|xterm-256color|%5\n/dev/tty1|linux|%5\n'
        active=True
        def tmux(*args):
            if args[0]=='list-clients':return rows
            return 'on\n' if active else '\n'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);palette=root/'palette';palette.write_bytes(bytes(range(48)))
            with patch.object(theme,'STATE',root/'state'),patch.object(theme,'CONSOLE_PALETTE',palette),patch.object(theme,'tmux',side_effect=tmux),patch.object(theme.os,'open',return_value=42),patch.object(theme.os,'close'),patch.object(theme.os,'write') as write:
                theme.sync();self.assertEqual(write.call_count,2)
                theme.sync();self.assertEqual(write.call_count,2)
                active=False;theme.sync();self.assertEqual(write.call_count,4)
                self.assertEqual(write.call_args_list[2].args[1],theme.reset_sequence())
                self.assertEqual(write.call_args_list[3].args[1],theme.reset_sequence(True))
                active=True;theme.sync();rows='';theme.sync()
                self.assertEqual(write.call_count,8)
    def test_invalid_palette(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'palette';path.write_bytes(b'bad')
            with patch.object(theme,'CONSOLE_PALETTE',path),self.assertRaises(ValueError):theme.reset_sequence(True)

if __name__=='__main__':unittest.main()
