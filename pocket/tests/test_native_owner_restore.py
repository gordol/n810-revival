"""The GPU owner's exit must restore the console after one ioctl fails."""
import ast
from pathlib import Path
import struct
import unittest
from types import SimpleNamespace


SOURCE = Path(__file__).resolve().parents[1] / 'platform/n810/native_owner.py'


class NativeOwnerRestore(unittest.TestCase):
    def test_failed_graphics_ioctl_does_not_skip_vt_or_update_mode(self):
        tree = ast.parse(SOURCE.read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'restore_display')
        events = []

        def ioctl(fd, request, *args):
            events.append(('ioctl', fd, request))
            if request in (0x4f25, 0x4b3a):
                raise OSError('VT is busy')

        def close(fd):
            events.append(('close', fd))

        def open_tty(path, flags):
            events.append(('open', path))
            return 22

        def pwrite(fd, data, offset):
            events.append(('pwrite', fd, offset))
            return len(data)

        def write_mode(value):
            events.append(('mode', value))

        scope = {'fcntl': SimpleNamespace(ioctl=ioctl), 'struct': struct,
                 'os': SimpleNamespace(pwrite=pwrite, close=close, open=open_tty,
                                       O_RDWR=2, O_NOCTTY=256, O_CLOEXEC=1)}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                     str(SOURCE), 'exec'), scope)
        errors = scope['restore_display'](10, 12, 11, 3, 0, 'tty1',
                                          SimpleNamespace(write_text=write_mode), '1\n',
                                          bytes(768000), True)
        self.assertGreaterEqual(len(errors), 2)
        self.assertIn(('ioctl', 11, 0x5606), events)
        self.assertIn(('ioctl', 11, 0x5607), events)
        self.assertIn(('mode', '1\n'), events)
        self.assertIn(('close', 10), events)
        self.assertIn(('close', 22), events)
        self.assertIn(('close', 11), events)


if __name__ == '__main__':
    unittest.main()
