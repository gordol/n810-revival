"""Local station identity is shared by clients of the same directory DB."""
import tempfile
import unittest
import sys
from pathlib import Path

from reference_fixtures import activate
activate()
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from directory_preferences import self_calls,save_self_calls,with_self_calls


class DirectoryPreferencesTest(unittest.TestCase):
    def test_shared_identity_overrides_separate_desktop_sessions(self):
        with tempfile.TemporaryDirectory() as folder:
            db=Path(folder)/'directory.sqlite3'
            self.assertEqual(self_calls({},db),())
            save_self_calls(db,('TEST-1',))
            self.assertEqual(self_calls({},db),('TEST-1',))
            other_session=with_self_calls({},('OLD-1',))
            self.assertEqual(self_calls(other_session,db),('TEST-1',))
            self.assertEqual(self_calls(other_session,Path(folder)/'other.sqlite3'),('TEST-1',))
            self.assertEqual((Path(folder)/'station-identity.json').stat().st_mode&0o777,0o600)

    def test_messages_asks_for_identity_when_unset(self):
        from native_messages import Messages
        view=Messages('')
        self.assertEqual(view.state.call,'')
        self.assertIn('Set your APRS callsign','\n'.join(view.lines()))
        saved=[];view.save_identity=saved.append
        for character in 'TEST1':view.key(character)
        view.key('\r')
        self.assertEqual(saved,['TEST1'])
        self.assertEqual(view.state.call,'TEST1')
        self.assertIsNone(view.identity_editor)

    def test_directory_has_no_invented_self_identity(self):
        from importlib.util import module_from_spec,spec_from_file_location
        path=Path(__file__).resolve().parents[1]/'shell/vendor/packet-console/n810-directory-model.py'
        spec=spec_from_file_location('directory_without_identity',path)
        model=module_from_spec(spec);spec.loader.exec_module(model)
        self.assertEqual(model.self_call_snapshot(),())


if __name__=='__main__':unittest.main()
