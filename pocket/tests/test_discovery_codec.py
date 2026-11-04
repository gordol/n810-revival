"""Persisted discovery observations must not require the retired Python RNS SDK."""
import hashlib,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'))
import discovery_codec as storage
import _umsgpack as legacy
from session_owner import SessionOwner

class DiscoveryCodecTests(unittest.TestCase):
    def test_saved_legacy_observations_restart_without_rns(self):
        public=b'x'*64
        record=dict(destination=b'd'*16,identity=hashlib.sha256(public).digest()[:16],public_key=public,
                    service='unknown',advertised_name=None,last_heard=123.0,observation='announce',
                    announce_hash=None,path_known_at_observation=False,hops_at_observation=None,
                    path_interface_at_observation=None,station_id='test',radio_id='radio')
        value=dict(version=1,records=[record])
        self.assertEqual(storage.pack(value),legacy.packb(value))
        for codec,native in [(legacy,False),(storage._codec,storage.NATIVE_CODEC)]:
            with self.subTest(native=native),tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'heard.msgpack';path.write_bytes(legacy.packb(value));path.chmod(0o600)
                with patch.dict(sys.modules,{'RNS':None,'LXMF':None}),patch.object(storage,'_codec',codec),patch.object(storage,'NATIVE_CODEC',native):
                    owner=SessionOwner(tmp,'test','radio','usb','/dev/null',2,2)
                    try:self.assertEqual(owner.heard_store.records[(b'd'*16).hex()]['public_key'],public.hex())
                    finally:owner.close()
    def test_invalid_storage_uses_consistent_error(self):
        for codec,native in [(legacy,False),(storage._codec,storage.NATIVE_CODEC)]:
            with patch.object(storage,'_codec',codec),patch.object(storage,'NATIVE_CODEC',native):
                for raw in (b'',b'\xc1',b'\x81'):
                    with self.subTest(native=native,raw=raw),self.assertRaisesRegex(ValueError,'Invalid discovery'):
                        storage.codec().unpackb(raw)

if __name__=='__main__':unittest.main()
