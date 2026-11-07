# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Fresh app processes must not depend on an owner's earlier sys.path setup."""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'shell'

class DiscoveryPackageImport(unittest.TestCase):
    def test_private_package_and_standalone_codec(self):
        for packaged in (True, False):
            script = '''
import importlib, sys
from pathlib import Path
root = Path(sys.argv[1])
if sys.argv[2] == 'package':
    sys.path.insert(0, str(root))
    from app_registry import Registry
    Registry(root).configure_reticulum(register=False)
    prefix = next(n for n in sys.modules if n.startswith('_pocket_reticulum_')) + '.'
else:
    sys.path.insert(0, str(root / 'vendor/apps/domains/reticulum'))
    prefix = ''
for name in ('endpoints', 'contacts', 'profile_store'):
    importlib.import_module(prefix + name)
codec = importlib.import_module(prefix + 'discovery_codec')
assert codec.unpack(codec.pack({'ready': True})) == {'ready': True}
'''
            result = subprocess.run([sys.executable, '-I', '-c', script, str(ROOT),
                                     'package' if packaged else 'standalone'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
