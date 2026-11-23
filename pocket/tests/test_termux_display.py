import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'graphics'))
from termux_display import ensure_display


class DisplayTests(unittest.TestCase):
    def run_display(self, display, replies, expected_server=None, error=None):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'DISPLAY':display,'HOME':directory}), \
             patch('termux_display.ctypes.CDLL') as library, patch('termux_display.subprocess.Popen') as launch, \
             patch('termux_display.time.sleep'):
            library.return_value.XOpenDisplay.side_effect = replies
            if error:
                with self.assertRaisesRegex(SystemExit,error):
                    ensure_display()
            else:
                ensure_display()
                library.return_value.XCloseDisplay.assert_called_once()
            self.assertEqual(os.environ['DISPLAY'],display or ':1')
            if expected_server:
                self.assertEqual(launch.call_args.args[0],['termux-x11',expected_server])
            else:
                launch.assert_not_called()

    def test_existing_display(self):
        self.run_display(':3',[1])

    def test_start_and_wait(self):
        self.run_display('',[None,None,1],':1')
        self.run_display(':2.0',[None,1],':2')

    def test_unavailable_display(self):
        self.run_display('remote:0',[None],error='Cannot connect')
        self.run_display(':1',[None]*61,':1','pocket-x11.log')
