from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum'))
from session_owner import SessionOwner

class ShutdownTests(unittest.TestCase):
    def test_disconnect_does_not_interrupt_cleanup_with_a_second_signal(self):
        with tempfile.TemporaryDirectory() as temporary:
            owner=SessionOwner.__new__(SessionOwner)
            child=Mock();child.poll.return_value=None;child.returncode=0
            owner.child=child;owner.reader=None;owner.worker_socket=Path(temporary)/'owner.sock'
            owner._signal_child();owner._signal_child();owner._stop_child()
            child.terminate.assert_called_once();child.wait.assert_called_once_with(timeout=20)
            child.kill.assert_not_called();self.assertIsNone(owner.child)

if __name__=='__main__':unittest.main()
