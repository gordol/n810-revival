"""Exercise persistent Bluetooth identity without a controller or root."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HELPER=Path(__file__).resolve().parents[1]/'scripts/n810-bluetooth-address'
class BluetoothAddressTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir='/tmp');self.addCleanup(self.temp.cleanup)
  self.root=Path(self.temp.name);self.node=self.root/'sys/serial0/bdaddr'
  self.node.parent.mkdir(parents=True);self.node.write_text('00:00:00:00:00:00\n')
  (self.node.parent/'driver').symlink_to(self.root/'drivers/nokia-bluetooth')
  self.state=self.root/'state/bdaddr';random=self.root/'random';random.write_bytes(bytes(range(6)))
  self.env=dict(os.environ,N810_BDADDR_TEST_MODE='1',N810_BDADDR_SYSFS_ROOT=str(self.root/'sys'),N810_BDADDR_STATE_FILE=str(self.state),N810_BDADDR_RANDOM_SOURCE=str(random))
 def run_helper(self):return subprocess.run(['sh',str(HELPER)],env=self.env,capture_output=True,text=True)
 def test_generates_stable_private_unicast_address_and_reuses_it(self):
  first=self.run_helper();self.assertEqual(first.returncode,0,first.stderr)
  self.assertEqual(self.state.read_text(),'02:01:02:03:04:05\n')
  self.assertEqual(self.state.stat().st_mode&0o777,0o600)
  before=self.node.stat().st_mtime_ns
  second=self.run_helper();self.assertEqual(second.returncode,0,second.stderr)
  self.assertEqual(self.node.stat().st_mtime_ns,before,'An already provisioned controller must not be rewritten')
 def test_rejects_redirected_state(self):
  target=self.root/'other';target.mkdir();self.state.parent.symlink_to(target)
  result=self.run_helper();self.assertNotEqual(result.returncode,0)
  self.assertIn('unexpected state directory link',result.stderr)
  self.assertFalse(list(target.iterdir()))
if __name__=='__main__':unittest.main()
