"""Age projection reuses detached facts and preserves app-owned refresh deadlines."""
from pathlib import Path
import sys,tempfile,unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from native_catalog import Catalog
from app_registry import LazyApplication

class CatalogueUpdates(unittest.TestCase):
 def test_receive_copy_retains_old_publication_after_inplace_packet_edit(self):
  packet=dict(direction='radio_to_host',raw='original',time='2026-10-30T12:00:00+00:00')
  state=SimpleNamespace(payload=dict(live=dict(data=dict(packets=[packet]))),result={},error=None)
  with tempfile.TemporaryDirectory() as folder:
   catalog=Catalog(state,schedule=Path(folder)/'missing')
   self.assertTrue(catalog.update());old=catalog.feed
   packet['raw']='changed'
   self.assertTrue(catalog.update())
   self.assertEqual(old['evidence'][0]['raw'],'original')
   self.assertEqual(catalog.feed['evidence'][0]['raw'],'changed')
 def test_age_change_reuses_unchanged_owned_facts_and_inplace_edits_still_publish(self):
  walks=[dict(rows=[dict(value='original')])]
  state=SimpleNamespace(payload=dict(catalog=dict(walks=walks),live=dict(data={})),result=dict(statusbar=dict(feed=dict(age=1))),error=None)
  with tempfile.TemporaryDirectory() as folder:
   catalog=Catalog(state,schedule=Path(folder)/'missing')
   self.assertTrue(catalog.update());saved=catalog.metadata_input['walks']
   self.assertIsNot(saved,walks)
   state.result['statusbar']['feed']['age']=2
   self.assertTrue(catalog.update());self.assertIs(catalog.metadata_input['walks'],saved)
   walks[0]['rows'][0]['value']='changed'
   self.assertTrue(catalog.update())
   self.assertEqual(saved[0]['rows'][0]['value'],'original')
   self.assertEqual(catalog.metadata_input['walks'][0]['rows'][0]['value'],'changed')
 def test_lazy_app_forwards_its_forms_presentation_deadline(self):
  app=LazyApplication.__new__(LazyApplication);app.owner=None;app.error=''
  self.assertIsNone(app.presentation_interval())
  app.owner=SimpleNamespace(view=SimpleNamespace(presentation_interval=lambda:1.))
  self.assertEqual(app.presentation_interval(),1.)
  app.error='failed';self.assertIsNone(app.presentation_interval())
