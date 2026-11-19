# SPDX-License-Identifier: GPL-2.0-or-later
"""Private build defaults must not block the unprivileged desktop user."""
import os
from pathlib import Path
import stat
import tempfile
import unittest
from stage_desktop import make_readable_tree


class PublicRuntimeModes(unittest.TestCase):
    def test_private_umask_keeps_only_public_runtime_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            old = os.umask(0o077)
            try:
                directory = root / 'usr/local/share/pocket/graphics'
                directory.mkdir(parents=True)
                code = directory / 'nokia.py'
                code.write_text('print("fixture")\n')
                private = root / 'etc/ssh'
                private.mkdir(parents=True)
                key = private / 'ssh_host_ed25519_key'
                key.write_text('fictional private key')
                link = directory / 'key-link'
                link.symlink_to(key)
                root_mode = stat.S_IMODE(root.stat().st_mode)
                make_readable_tree(root, 'usr/local/share/pocket')
                for path in (directory, *directory.parents):
                    if path == root:
                        break
                    self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE(code.stat().st_mode), 0o644)
                self.assertEqual(stat.S_IMODE(key.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(root.stat().st_mode), root_mode)
            finally:
                os.umask(old)


if __name__ == '__main__':
    unittest.main()
