"""One-time imports preserve contact trust, radio choices and original files."""
from pathlib import Path
import json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'))
from contacts import ContactBook,card,fingerprint,parse_card
from profile_store import ProfileStore
from endpoints import Endpoint,saved_endpoint
from discovery_codec import pack,unpack

class BinaryStoreTests(unittest.TestCase):
    def legacy(self,path,value):
        raw=json.dumps(value,ensure_ascii=False).encode();path.write_bytes(raw);path.chmod(0o600);return raw
    def test_contacts_preserve_verification_and_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);key=bytes(range(64));public=card(key,'café station')
            record=dict(card=public,state='verified',fingerprint=fingerprint(key),verified_at=123.)
            path=root/'contacts.json';raw=self.legacy(path,dict(version=1,contacts={public['identity']:record}))
            book=ContactBook(root);self.assertEqual(book.contacts[public['identity']],record)
            self.assertEqual(path.read_bytes(),raw)
            self.assertEqual(book.path.name,'contacts.msgpack');self.assertEqual(book.path.stat().st_mode&0o777,0o600)
            self.assertEqual(unpack(book.path.read_bytes())['contacts'],{public['identity']:record})
            self.assertEqual(ContactBook(root).contacts,book.contacts)
            self.assertEqual(parse_card(public),parse_card(pack(public)))
            self.assertEqual(parse_card(json.dumps(public)),public)
    def test_invalid_legacy_trust_cannot_be_promoted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);public=card(bytes(range(64)));path=root/'contacts.json'
            raw=self.legacy(path,dict(version=1,contacts={public['identity']:dict(card=public,state='verified',fingerprint='0'*64)}))
            with self.assertRaises(ValueError):ContactBook(root)
            self.assertEqual(path.read_bytes(),raw);self.assertFalse((root/'contacts.msgpack').exists())
    def test_binary_contacts_still_reject_outside_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            book=ContactBook(tmp);public=card(bytes(range(64)));book.import_contact(public)
            book.path.write_bytes(pack(dict(version=1,contacts={})))
            with self.assertRaisesRegex(ValueError,'changed outside'):book.rename(public['identity'],'new')
    def test_profiles_and_device_selection_migrate_without_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);profile=dict(id='saved',label='Private LoRa',frequency=915000000,bandwidth=125000,txpower=5,spreadingfactor=7,codingrate=5)
            radio=dict(version=1,station='n810',radio='60f7',connection='bluetooth',port='/dev/rfcomm0')
            original={name:self.legacy(root/name,value) for name,value in [('radio-profiles.json',dict(version=1,selected='saved',profiles=[profile])),('radio-device.json',radio)]}
            store=ProfileStore(root,'n810','60f7','usb','/dev/test',0,18)
            self.assertEqual(store.selected,'saved');self.assertEqual(store.profiles,{'saved':profile})
            self.assertEqual(store.endpoint.connection,'bluetooth');self.assertEqual(store.endpoint.port,'/dev/rfcomm0')
            self.assertEqual(store.path.name,'radio-profiles.msgpack')
            for name,raw in original.items():self.assertEqual((root/name).read_bytes(),raw)
            self.assertEqual(unpack((root/'radio-device.msgpack').read_bytes()),radio)
            self.assertEqual(ProfileStore(root,'n810','60f7','usb','/dev/test',0,18).profiles,store.profiles)
    def test_unsafe_binary_file_never_falls_back_to_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);old=root/'contacts.json';self.legacy(old,dict(version=1,contacts={}))
            (root/'contacts.msgpack').symlink_to(old)
            with self.assertRaises(ValueError):ContactBook(root)

if __name__=='__main__':unittest.main()
