"""Bounds for data supplied by a selected MeshCore companion."""
import asyncio
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(importlib.util.find_spec('meshcore'),'requires optional MeshCore client')
class MeshCoreInputTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('mesh_owner_input_test',ROOT/'shell/vendor/apps/domains/meshcore/owner.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.root=tempfile.TemporaryDirectory();self.owner=self.module.MeshOwner(self.root.name,'test','/dev/test')

    def tearDown(self):
        self.owner.close();self.root.cleanup()

    def test_untrusted_event_fields_are_bounded_and_normalized(self):
        from meshcore import EventType
        peer='AB'*32
        self.owner.peers=[dict(identity=peer.lower(),label='peer')]
        event=SimpleNamespace(type=EventType.CONTACT_MSG_RECV,payload=dict(
            pubkey_prefix=peer[:12],text='hello\x1b[2J'+('x'*700),sender_timestamp=2**40))
        self.owner.receive(event);row=self.owner.history.latest()[0]
        self.assertEqual(row['peer'],peer.lower())
        self.assertNotIn('\x1b',row['text'])
        self.assertLessEqual(len(row['text'].encode()),self.module.MAX_MESSAGE_BYTES)
        self.assertIsNone(row['timestamp'])
        self.owner.receive(SimpleNamespace(type=EventType.CONTACT_MSG_RECV,payload='not a mapping'))
        self.assertEqual(len(self.owner.history.latest()),1)

    def test_contact_refresh_rejects_unbounded_payloads(self):
        from meshcore import EventType
        result=SimpleNamespace(type=EventType.CONTACTS,payload={f'{i:064x}':{} for i in range(self.module.MAX_CONTACTS+1)})
        async def get_contacts(**kwargs):return result
        self.owner.client=SimpleNamespace(commands=SimpleNamespace(get_contacts=get_contacts))
        with self.assertRaisesRegex(ValueError,'Invalid contact list'):asyncio.run(self.owner.refresh())


if __name__=='__main__':unittest.main()
