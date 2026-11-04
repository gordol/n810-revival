"""The existing radio adapter reuses its interpreter while the owner retains control."""
from pathlib import Path
import importlib.util,unittest
from unittest.mock import patch
SHELL=Path(__file__).resolve().parents[1]/'shell'
class RetryTests(unittest.TestCase):
 def modules(self):
  for path in (SHELL/'owner-service/uvpro-aprs-listen.py',SHELL/'vendor/packet-console/uvpro-aprs-listen.py'):
   spec=importlib.util.spec_from_file_location('uvpro_trial',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
   yield path,module
 def test_retry_reuses_main_without_restarting_process(self):
  for path,module in self.modules():
   with self.subTest(path=path),patch.object(module,'main',side_effect=[OSError('off'),OSError('off'),None]) as main,patch.object(module.time,'sleep') as sleep,patch('builtins.print'):
    self.assertEqual(module.run(retry=True),0);self.assertEqual(main.call_count,3)
    self.assertEqual([call.args for call in sleep.call_args_list],[(10,),(10,)])
 def test_stop_interrupts_retry_wait_and_one_shot_still_exits(self):
  for path,module in self.modules():
   with self.subTest(path=path),patch.object(module,'main',side_effect=OSError('off')),patch.object(module.time,'sleep',side_effect=KeyboardInterrupt),patch('builtins.print'):
    self.assertEqual(module.run(retry=True),0)
    self.assertEqual(module.run(retry=False),1)
 def test_offline_connection_does_not_import_bridge_machinery(self):
  for path,module in self.modules():
   with self.subTest(path=path),patch.object(module.signal,'signal'),patch.object(module.subprocess,'check_output',return_value='Channel: 1'),patch.object(module.socket,'socket') as socket,patch.object(module.socket,'AF_BLUETOOTH',31,create=True),patch.object(module.socket,'BTPROTO_RFCOMM',3,create=True),patch.object(module,'module') as load,patch('builtins.print'):
    socket.return_value.connect.side_effect=ConnectionError('off')
    with self.assertRaises(ConnectionError):module.main()
    load.assert_not_called();socket.return_value.close.assert_called_once()
