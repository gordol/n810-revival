"""Exercise actual Pocket Pull UI against synthetic cached banks; no device I/O."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parent
WORLD=ROOT.parent/'explorations/current-world'
sys.path.insert(0,str(WORLD))
from radio_manager import State,RadioManager
from radio_drafts import Drafts,library


def state():
    fixture=json.loads((ROOT/'fixtures/radio-pull-review.json').read_text())
    result=State(clock=lambda:2000000000);result.payload=fixture;result.update(True)
    return result


class Tests(unittest.TestCase):
    def test_review_cancel_has_no_local_or_source_mutation(self):
        with tempfile.TemporaryDirectory() as folder:
            source=state();before=copy.deepcopy(source.payload)
            form=RadioManager(source,folder);form.page=2;form.bank=0;form.key('p')
            self.assertEqual(form.review['source']['bank_index'],2)
            self.assertEqual(form.review['source']['captured_at'],'2026-10-16T23:00:00Z')
            self.assertTrue(form.review['can_apply_locally'])
            self.assertIn('COPY DOWNLOADED BANK', '\n'.join(form.lines()))
            form.key('\x1b')
            self.assertIsNone(form.review);self.assertIsNone(form.drafts.documents['banks'])
            self.assertEqual(list(Path(folder).iterdir()),[]);self.assertEqual(source.payload,before)

    def test_confirm_then_explicit_atomic_save_reload_retains_identity_and_raw(self):
        with tempfile.TemporaryDirectory() as folder:
            source=state();before=copy.deepcopy(source.payload)
            form=RadioManager(source,folder);form.page=2;form.key('p')
            plan=copy.deepcopy(form.review);bank_id=plan['proposed_bank']['id'];row_id=plan['proposed_bank']['channels'][0]['id']
            form.key('\r')
            self.assertTrue(form.drafts.dirty('banks'));self.assertEqual(list(Path(folder).iterdir()),[])
            form.key('S')
            path=Path(folder)/'banks.json';self.assertEqual(path.stat().st_mode&0o777,0o600)
            saved=Drafts(folder);local=saved.documents['banks']
            row=library.get_channel(local,bank_id,row_id)
            self.assertEqual(row['radio_origin']['bank_index'],2)
            self.assertEqual(row['radio_origin']['raw']['decoded']['fixture_unknown_flag'],73)
            self.assertNotIn('hardware_slot',row)
            self.assertEqual([c['hardware_slot'] for c in library.get_bank(local,'core')['channels']],[0,1,2])
            self.assertFalse(form.drafts.dirty('banks'));self.assertEqual(source.payload,before)
            self.assertFalse(source.result['capabilities']['hardware_commands'])

    def test_unsupported_mapping_visible_and_enter_cannot_apply(self):
        with tempfile.TemporaryDirectory() as folder:
            form=RadioManager(state(),folder);form.page=2;form.bank=1;form.key('p')
            self.assertEqual(form.review['source']['bank_index'],5)
            self.assertFalse(form.review['can_apply_locally'])
            self.assertIn('DCS not represented','\n'.join(form.lines()))
            form.key('\r')
            self.assertIsNotNone(form.review);self.assertIsNone(form.drafts.documents['banks'])
            self.assertEqual(list(Path(folder).iterdir()),[])
            form.key('\x1b');self.assertIsNone(form.review)

    def test_save_after_external_change_preserves_external_file(self):
        with tempfile.TemporaryDirectory() as folder:
            form=RadioManager(state(),folder);form.page=2;form.key('p');form.key('\r')
            path=Path(folder)/'banks.json'
            original={'version':1,'banks':[library.core_bank()]}
            path.write_text(json.dumps(original));external=path.read_bytes()
            form.key('S')
            self.assertIn('externally',form.message)
            self.assertEqual(path.read_bytes(),external);self.assertTrue(form.drafts.dirty('banks'))


if __name__=='__main__':unittest.main()
