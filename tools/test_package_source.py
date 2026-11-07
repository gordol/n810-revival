"""Source exports retain notices and reject unreviewed working-tree bytes."""
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('package_source', Path(__file__).with_name('package-source.py'))
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class SourceExportTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        for name, value in [('LICENSE', 'retained terms\n'), ('build.py', 'print("build")\n')]:
            (self.root / name).write_text(value)
        (self.root / 'build.py').chmod(0o755)
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)

    def test_internal_audit_records_are_excluded(self):
        self.assertIsNone(package.release_bytes('LICENSE-PROVENANCE.json', b'private review'))
        self.assertIsNone(package.release_bytes('maintainers/local-review-result.json', b'local state'))
        self.assertEqual(package.release_bytes('licenses/upstream/LICENSE', b'notice'), b'notice')
        scope = {'version': 2, 'files': [{'path': 'a.py', 'license': 'GPL-2.0-or-later',
                  'grant': 'licenses/grant.md', 'evidence': {'review': 'internal'}}]}
        result = json.loads(package.release_bytes('LICENSE-SCOPE.json', json.dumps(scope).encode()))
        self.assertNotIn('evidence', result['files'][0])
        self.assertEqual(result['files'][0]['license'], 'GPL-2.0-or-later')

    def test_documentation_is_separate_from_source(self):
        image = self.root / 'docs/assets/demo.png'
        image.parent.mkdir(parents=True)
        image.write_bytes(b'fixture image')
        (self.root / 'docs/index.md').write_text('Documentation')
        subprocess.run(['git', 'add', '.'], cwd=self.root, check=True)
        for media_only in (False, True):
            output = self.root / ('media.tgz' if media_only else 'source.tgz')
            package.export(self.root, output, media_only)
            with tarfile.open(output) as archive:
                names = archive.getnames()
                self.assertEqual('n810-revival/docs/assets/demo.png' in names, media_only)
                self.assertEqual('n810-revival/docs/index.md' in names, media_only)
                self.assertEqual('n810-revival/LICENSE' in names, not media_only)

    def test_archive_matches_index_and_is_repeatable(self):
        a, b = self.root / 'a.tgz', self.root / 'b.tgz'
        self.assertEqual(package.export(self.root, a), package.export(self.root, b))
        self.assertEqual(a.read_bytes(), b.read_bytes())
        with tarfile.open(a) as archive:
            self.assertEqual(archive.getmember('n810-revival/build.py').mode, 0o755)
            manifest = json.load(archive.extractfile('n810-revival/SOURCE-SNAPSHOT.json'))
            self.assertEqual(set(manifest['files']), {'LICENSE', 'build.py'})
            for name, entry in manifest['files'].items():
                raw = archive.extractfile('n810-revival/' + name).read()
                self.assertEqual(hashlib.sha256(raw).hexdigest(), entry['sha256'])

    def test_unstaged_change_rejects_and_removes_partial_export(self):
        (self.root / 'build.py').write_text('unreviewed\n')
        with self.assertRaisesRegex(ValueError, 'Stage reviewed'):
            package.export(self.root, self.root / 'a.tgz')
        self.assertFalse((self.root / 'a.tgz').exists())
        self.assertFalse((self.root / 'a.tgz.partial').exists())

    def test_symlink_substitution_is_rejected(self):
        (self.root / 'build.py').unlink()
        (self.root / 'build.py').symlink_to('LICENSE')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            package.export(self.root, self.root / 'a.tgz')


if __name__ == '__main__':
    unittest.main()
