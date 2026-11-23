import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'shell'))
import field_companion as field
from field_views import FieldView
from native_data_setup import OfflineData
import wikivoyage


class PhrasebookTests(unittest.TestCase):
    def test_preview_then_save_and_reload(self):
        page = dict(title='Spanish phrasebook', revid=42,
                    text='<h3>Basics</h3><dl><dt>Hello</dt><dd><b>Hola</b> (OH-lah)</dd></dl>')
        book = wikivoyage.convert('Spanish', page)
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,XDG_STATE_HOME=tmp), patch.object(wikivoyage,'download',return_value=book):
            form=OfflineData()
            try:
                form.key('books')
                form.key('lang-Spanish')
                form.phrase_job.result(timeout=2)
                self.assertTrue(form.poll())
                self.assertIn('Hola', ''.join(form.lines()))
                view=FieldView('phrase')
                self.assertFalse(view.records)
                form.key('save-book')
                view.command('reload')
                self.assertEqual(view.records[0]['body'],'Hello\nHola (OH-lah)')
                self.assertIn('PermanentLink/42',view.records[0]['source'])
                self.assertIsNone(field.active(field.state_root()))
            finally:
                form.close()

    def test_unrecognised_page(self):
        with self.assertRaisesRegex(ValueError,'No phrase pairs'):
            wikivoyage.convert('French',dict(text='<p>Try again</p>'))
