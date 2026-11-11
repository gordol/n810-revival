"""Directory identity is shared locally beside the selected database."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from directory_preferences import save_self_calls,self_calls


class DirectoryPreferences(unittest.TestCase):
 def test_local_identity_sidecar_is_private_and_database_scoped(self):
  with tempfile.TemporaryDirectory() as root:
   db=Path(root)/'directory.sqlite'
   first=('identity-a','identity-b')
   save_self_calls(db,first)
   sidecar=Path(root)/'station-identity.json'
   self.assertEqual(self_calls({},db),first)
   self.assertEqual(sidecar.stat().st_mode&0o777,0o600)
   self.assertEqual(self_calls({},Path(root)/'other'/'other.sqlite'),())

 def test_legacy_saved_identity_is_used_until_local_sidecar_is_written(self):
  legacy={'station-self':{'self-call-00':'identity-a'}}
  with tempfile.TemporaryDirectory() as root:
   db=Path(root)/'directory.sqlite'
   self.assertEqual(self_calls(legacy,db),('identity-a',))
   save_self_calls(db,('identity-b',))
   self.assertEqual(self_calls(legacy,db),('identity-b',))


if __name__=='__main__':unittest.main()
