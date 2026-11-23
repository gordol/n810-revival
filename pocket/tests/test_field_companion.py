from pathlib import Path
from tempfile import TemporaryDirectory
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

POCKET = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(POCKET/'shell'))
import app_registry
from core import Host
import field_companion as field


class FieldCompanionTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = patch.dict(os.environ, {'XDG_STATE_HOME': tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.store = field.state_root()
        self.file = self.root/'example.pack'
        subprocess.run([sys.executable, str(POCKET/'tools/fieldpack.py'), 'build',
                        str(POCKET/'examples/field-companion/region.json'), str(self.file)], check=True)

    def test_registered_apps_share_pack_and_observations_survive_replacement(self):
        registry = app_registry.discover()
        host = Host(88, 24, registry.windows(88, 24))
        host.app_forms = {}
        registry.bind(host)

        def open_app(key):
            self.assertTrue(registry.open(key))
            return registry.forms[registry.entries[key].title]

        def type_text(form, value):
            for key in value:
                self.assertTrue(form.key(key))
            form.key('\n')

        guide = open_app('field-guide')
        guide.key('i')
        type_text(guide, str(self.file))
        self.assertIn('Shelter notebook', '\n'.join(guide.lines()))
        phrases = open_app('field-phrases')
        phrases.key('\n')
        self.assertIn('agua potable', '\n'.join(phrases.lines()))
        log = open_app('field-log')
        log.key('n')
        type_text(log, 'Fixture shelter open')
        self.assertIn('Fixture shelter open', '\n'.join(log.lines()))

        external = field.observation('sample-valley', 'Fixture phone', 'transcript', 'Fixture voice note')
        transfer = self.root/'phone.json'
        field.write_log(transfer, [external])
        for count in (1, 0):
            log.key('m')
            type_text(log, str(transfer))
            self.assertIn(f'{count} observations imported', '\n'.join(log.lines()))
        data = field.read_file(self.file)
        data['region'] = 'Revised fictional valley'
        field.write_file(self.file, data)
        field.activate(self.file, self.store)
        log.key('r')
        self.assertIn('Revised fictional valley', '\n'.join(log.lines()))
        self.assertEqual(len(field.Journal(self.store).recent('sample-valley')), 2)

    def test_invalid_replacement_and_conflicting_batch_roll_back(self):
        previous = field.activate(self.file, self.store)
        bad = dict(previous, cards=[previous['cards'][0]] * 2)
        field.write_file(self.file, bad)
        with self.assertRaises(ValueError):
            field.activate(self.file, self.store)
        self.assertEqual(field.active(self.store), previous)
        journal = field.Journal(self.store)
        original = field.observation('sample-valley', 'Fixture phone', 'note', 'One')
        other = field.observation('sample-valley', 'Fixture phone', 'note', 'Two')
        journal.merge(dict(format=field.LOG, notes=[original]))
        with self.assertRaises(ValueError):
            journal.merge(dict(format=field.LOG, notes=[other, dict(original, body='Conflict')]))
        self.assertEqual(journal.recent('sample-valley'), [original])

    def test_export_pages_fit_transfer_limit_and_round_trip(self):
        journal = field.Journal(self.store)
        notes = [field.observation('sample-valley', 'Fixture phone', 'note', '雪'*4000) for _ in range(90)]
        for note in notes:
            journal.merge(dict(format=field.LOG, notes=[note]))
        batch, cursor = journal.export_page('sample-valley')
        self.assertIsNotNone(cursor)
        path = self.root/'page.json'
        field.write_log(path, batch)
        self.assertLessEqual(path.stat().st_size, field.LIMIT)
        self.assertEqual(field.read_log(path)['notes'], batch)
        tail, cursor = journal.export_page('sample-valley', cursor)
        self.assertIsNone(cursor)
        self.assertEqual(sorted(n['id'] for n in notes), [n['id'] for n in batch + tail])
