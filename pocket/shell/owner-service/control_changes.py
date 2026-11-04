"""Linux inotify readiness for the owner's existing explicit control files."""
import ctypes
import os
from pathlib import Path
import struct


class ControlChanges:
    def __init__(self, paths):
        self.paths = {Path(p) for p in paths}
        self.directories = {}
        libc = ctypes.CDLL(None, use_errno=True)
        self.fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), 'inotify_init1 failed')
        try:
            for directory in {p.parent for p in self.paths}:
                watch = libc.inotify_add_watch(self.fd, os.fsencode(directory),
                                               0x8 | 0x80 | 0x100 | 0x200 | 0x400 | 0x800)
                if watch < 0:
                    raise OSError(ctypes.get_errno(), 'inotify_add_watch failed')
                self.directories[watch] = directory
        except BaseException:
            os.close(self.fd)
            raise

    def drain(self):
        changed = set()
        while True:
            try:
                raw = os.read(self.fd, 65536)
            except BlockingIOError:
                return changed
            if not raw:
                raise OSError('control watch closed')
            position = 0
            while position < len(raw):
                watch, mask, _cookie, length = struct.unpack_from('iIII', raw, position)
                position += 16
                name = raw[position:position+length].split(b'\0', 1)[0]
                position += length
                if mask & 0x4000:
                    changed.update(self.paths)
                    continue
                if mask & (0x400 | 0x800 | 0x8000):
                    raise OSError('control directory watch lost')
                path = self.directories[watch] / os.fsdecode(name)
                if path in self.paths:
                    changed.add(path)

    def close(self):
        os.close(self.fd)
