"""Exercise the map sender and the N810 receiver shell against local fixture data."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


class PushTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("flock"), "receiver fixture requires Linux flock")
    def test_install_and_truncated_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            source = home / 'region'
            for name in ('geography', 'hydrography', 'maps', 'fine', 'downloads'):
                (source / name).mkdir(parents=True)
            for name in ('geography', 'hydrography'):
                (source / name / 'index.json').write_text('{"tiles":{}}')
            (source / 'fine/index.json').write_text('{"units":"meters","tile_size":256,"tiles":{}}')
            (source / 'elevation.json').write_text('{"version":1,"packs":["fine/index.json"]}')
            (source / 'maps/walk-layers.n8w').write_bytes(b'N8W1-test')
            (source / 'downloads/raw').write_text('excluded')
            tools = home / 'bin'
            tools.mkdir()
            ssh = tools / 'ssh'
            ssh.write_text('#!/bin/sh\nfor arg do command=$arg; done\nexec sh -c "$command"\n')
            ssh.chmod(0o755)
            installer = tools / 'n810-install-reference-data'
            shutil.copyfile(TOOLS / 'install_reference_data.py', installer)
            installer.chmod(0o755)
            env = dict(os.environ, HOME=directory, PATH=str(tools) + ':' + os.environ['PATH'])
            command = [sys.executable, str(TOOLS / 'push_reference_data.py'), str(source), 'fixture']
            result = subprocess.run(command, capture_output=True, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            target = home / '.local/share/pocket'
            self.assertFalse((target / 'downloads').exists())
            self.assertEqual((target / 'maps/walk-layers.n8w').read_bytes(), b'N8W1-test')
            (source / 'maps/walk-layers.n8w').write_bytes(b'N8W1-replacement')
            ssh.write_text('#!/bin/sh\nfor arg do command=$arg; done\nhead -c 100 | sh -c "$command"\n')
            self.assertNotEqual(subprocess.run(command, capture_output=True, env=env).returncode, 0)
            self.assertEqual((target / 'maps/walk-layers.n8w').read_bytes(), b'N8W1-test')
            self.assertFalse(list(target.parent.glob('.pocket-maps.*')))
