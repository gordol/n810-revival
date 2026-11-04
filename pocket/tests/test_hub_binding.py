"""Logical hub selection survives restart without saving a transient PTY."""
import sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell'))
sys.path.insert(0,str(ROOT/'shell/vendor/apps/domains/reticulum'))
from endpoints import Endpoint
from profile_store import ProfileStore
from session_owner import SessionOwner
from vendor.apps.domains.meshcore.hub_provider import configure,configured_hubs,configured_port

class BindingTests(unittest.TestCase):
    def test_registry_and_selected_logical_port_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            state=Path(tmp)/'radio';state.mkdir(mode=0o700)
            registry=Path(tmp)/'hubs'
            identity,_=configure('rfcomm://aa:bb:cc:dd:ee:ff/1',registry)
            uri='hub://'+identity+'/3'
            self.assertEqual(configured_hubs(registry)[0]['port'],uri)
            with patch.object(SessionOwner,'_hub_api') as api:
                api.return_value.configured_port=lambda i:configured_port(i,registry)
                owner=SessionOwner(state,'test','radio','usb','/dev/ttyUSB0',2,17)
                try:owner.dispatch(dict(version=1,action='select_connection',payload=dict(connection='hub',port=uri)))
                finally:owner.close()
            restored=SessionOwner(state,'test','radio','usb','/dev/ttyUSB0',2,17)
            try:
                self.assertEqual(restored.connection,'hub')
                self.assertEqual(restored.store.endpoint.port,uri)
                store=restored.store
                profile=dict(id='test',label='Test',frequency=912345000,bandwidth=500000,txpower=2,spreadingfactor=7,codingrate=5)
                store.commit({'test':profile},'test')
                with self.assertRaises(ValueError):store.configuration()
                for path in ('/dev/pts/101','/dev/pts/202'):
                    config=store.configuration(resolved_port=path)
                    self.assertIn('port = '+path,config)
                    self.assertIn('flow_control = True',config)
                self.assertEqual(store.endpoint.port,uri)
                from discovery_codec import unpack
                self.assertNotIn('/dev/pts/',unpack((state/'radio-device.msgpack').read_bytes())['port'])
            finally:restored.close()

if __name__=='__main__':unittest.main()
