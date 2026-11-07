import contextlib
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import console_accept as test


class FakeConsole:
    vt = 8

    def __init__(self, fail_font=False):
        self.events = []
        self.fail_font = fail_font

    def switch(self, vt):
        self.events.append(('switch', vt))

    def font(self, saved):
        self.events.append(('font', saved))
        if self.fail_font:
            raise OSError('injected font restore failure')

    def write(self, text):
        self.events.append(('write', text))


class AcceptanceTests(unittest.TestCase):
    def test_default_mode_opens_no_device(self):
        with patch.object(sys, 'argv', ['console_accept.py']), \
             patch.object(test.os, 'open', side_effect=AssertionError('device opened')), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            test.main()
        self.assertIn('Plan only', output.getvalue())

    def test_success_restores_font_before_original_vt(self):
        c = FakeConsole()
        with patch.object(test.signal, 'setitimer'):
            with test.isolated(c, 1, {'data': b'font'}):
                c.events.append(('test', None))
        self.assertEqual([e[0] for e in c.events], ['switch', 'test', 'font', 'write', 'switch'])
        self.assertEqual(c.events[-1], ('switch', 1))

    def test_failure_restores_font_and_vt(self):
        c = FakeConsole()
        with patch.object(test.signal, 'setitimer'):
            with self.assertRaisesRegex(RuntimeError, 'injected test failure'):
                with test.isolated(c, 1, {}):
                    raise RuntimeError('injected test failure')
        self.assertEqual(c.events[-1], ('switch', 1))
        self.assertIn(('font', {}), c.events)

    def test_font_failure_still_restores_original_vt(self):
        c = FakeConsole(fail_font=True)
        with patch.object(test.signal, 'setitimer'):
            with self.assertRaisesRegex(RuntimeError, 'Restore errors: font'):
                with test.isolated(c, 1, {}):
                    pass
        self.assertEqual(c.events[-1], ('switch', 1))

    def test_termination_exception_runs_restoration(self):
        c = FakeConsole()
        with patch.object(test.signal, 'setitimer'):
            with self.assertRaises(KeyboardInterrupt):
                with test.isolated(c, 1, {}):
                    raise KeyboardInterrupt()
        self.assertEqual(c.events[-1], ('switch', 1))

    def test_font_ioctl_uses_native_pointer_alignment(self):
        size = test.ctypes.sizeof(test.ctypes.c_void_p)
        self.assertEqual(test.FontOp.data.offset, 20 if size == 4 else 24)
        self.assertEqual(test.FontOp.op.offset, 0)


if __name__ == '__main__':
    unittest.main()
