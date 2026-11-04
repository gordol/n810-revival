"""Durability and paging checks without a radio or message transmission."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import json
from contextlib import closing
from unittest.mock import patch
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('meshcore_history_test',ROOT/'shell/vendor/apps/domains/meshcore/history.py')
history=importlib.util.module_from_spec(spec);spec.loader.exec_module(history)

class HistoryTests(unittest.TestCase):
    def test_archive_survives_recent_window_and_legacy_migration(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'messages.sqlite3';store=history.History(path)
            for i in range(80):store.put(dict(id=str(i),text='message '+str(i),state='received'))
            store.put(dict(id='79',state='acknowledged'))
            store.put(dict(id='79',state='stale'),replace=False)
            self.assertEqual(history.History(path).latest()[-1]['state'],'acknowledged')
            self.assertEqual(len(store.latest()),32)
            db=sqlite3.connect(path)
            try:self.assertEqual(db.execute('SELECT COUNT(*) FROM messages').fetchone()[0],80)
            finally:db.close()
            self.assertEqual(path.stat().st_mode&0o777,0o600)

    def legacy(self,path):
        rows=[dict(id='a',text='café \"quote\"\n日本語',state='received',timestamp=123),
              dict(id='b',text='pending',state='queued',channel_idx=2),
              dict(id='c',text='ack',state='acknowledged',metadata=dict(rssi=-84,snr=3.25))]
        with closing(sqlite3.connect(path)) as db, db:
            db.execute('CREATE TABLE messages (id TEXT PRIMARY KEY, body TEXT NOT NULL)')
            for rowid,row in zip((10,20,33),rows):db.execute('INSERT INTO messages(rowid,id,body) VALUES (?,?,?)',(rowid,row['id'],json.dumps(row,ensure_ascii=False)))
        path.chmod(0o600);return rows

    def test_one_time_transactional_conversion_preserves_order_and_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'messages.sqlite3';expected=self.legacy(path)
            with closing(sqlite3.connect(path)) as db, db:original=db.execute('SELECT rowid,id,body FROM messages ORDER BY rowid').fetchall()
            store=history.History(path);self.assertEqual(store.latest(),expected)
            with closing(sqlite3.connect(path)) as db, db:
                self.assertEqual(db.execute('SELECT rowid,typeof(body) FROM messages ORDER BY rowid').fetchall(),[(10,'blob'),(20,'blob'),(33,'blob')])
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],2)
            backups=list(Path(tmp).glob('*.before-msgpack-*'));self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].stat().st_mode&0o777,0o600)
            with closing(sqlite3.connect(backups[0])) as db:self.assertEqual(db.execute('SELECT rowid,id,body FROM messages ORDER BY rowid').fetchall(),original)
            self.assertEqual(history.History(path).latest(),expected)
            self.assertEqual(list(Path(tmp).glob('*.before-msgpack-*')),backups)
            store.put(dict(id='d',text='new binary message'))
            with closing(sqlite3.connect(path)) as db, db:self.assertEqual(db.execute("SELECT typeof(body) FROM messages WHERE id='d'").fetchone()[0],'blob')

    def test_malformed_legacy_message_leaves_archive_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'messages.sqlite3';self.legacy(path)
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("UPDATE messages SET body='broken' WHERE id='b'")
                original=db.execute('SELECT rowid,id,body FROM messages ORDER BY rowid').fetchall()
            with self.assertRaises(ValueError):history.History(path)
            with closing(sqlite3.connect(path)) as db, db:self.assertEqual(db.execute('SELECT rowid,id,body FROM messages ORDER BY rowid').fetchall(),original)
            self.assertFalse(list(Path(tmp).glob('*.before-msgpack-*')))

    def test_mid_conversion_failure_rolls_back_and_retry_reuses_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'messages.sqlite3';expected=self.legacy(path);encode=history.pack;calls=[0]
            def fail(value):
                calls[0]+=1
                if calls[0]==5:raise OSError('interrupted migration')
                return encode(value)
            with patch.object(history,'pack',side_effect=fail),self.assertRaises(OSError):history.History(path)
            with closing(sqlite3.connect(path)) as db, db:self.assertEqual(db.execute('SELECT DISTINCT typeof(body) FROM messages').fetchall(),[('text',)])
            backups=list(Path(tmp).glob('*.before-msgpack-*'));self.assertEqual(len(backups),1)
            self.assertEqual(history.History(path).latest(),expected)
            self.assertEqual(list(Path(tmp).glob('*.before-msgpack-*')),backups)

    def test_rejects_symlink_and_public_store(self):
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/'target';target.touch();target.chmod(0o644)
            with self.assertRaises(ValueError):history.History(target)
            link=Path(root)/'link';link.symlink_to(target)
            with self.assertRaises(OSError):history.History(link)

@unittest.skipUnless(importlib.util.find_spec('meshcore'),'requires optional MeshCore client')
class OwnerDurabilityTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('mesh_owner_history_test',ROOT/'shell/vendor/apps/domains/meshcore/owner.py')
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        self.root=tempfile.TemporaryDirectory();self.owner=self.module.MeshOwner(self.root.name,'test','/dev/test')
    def tearDown(self):
        self.owner.close();self.root.cleanup()
    def event(self):
        from meshcore import EventType
        return SimpleNamespace(type=EventType.CHANNEL_MSG_RECV,payload=dict(channel_idx=0,text='durable fixture',sender_timestamp=123))
    def test_idle_control_owner_needs_no_async_worker(self):
        self.assertIsNone(self.owner.worker)
        self.assertEqual(self.owner.snapshot()['connection_state'],'idle')
        self.assertIn('connect',self.owner.snapshot()['capabilities'])

    def test_received_message_is_durable_before_ui_drain(self):
        self.owner.receive(self.event())
        self.assertEqual(self.owner.messages,[])
        self.assertEqual(history.History(Path(self.root.name)/'messages.sqlite3').latest()[0]['text'],'durable fixture')
        self.owner.drain();self.assertEqual(len(self.owner.messages),1)
    def test_storage_failure_halts_fetch_and_retains_unsaved_message(self):
        def fail(row):raise OSError('disk full fixture')
        self.owner.history.put=fail;self.owner.fetch_pending=True
        self.owner.receive(self.event())
        self.assertFalse(self.owner.fetch_pending)
        self.assertIn('retrieval stopped',self.owner.receive_error)
        self.assertEqual(self.owner.unsaved_receive['text'],'durable fixture')
        self.assertTrue(self.owner.events.empty())
    def start_fetch(self,client):
        import time
        self.owner.client=client;self.owner.fetch_pending=True
        self.owner._start_worker()
        deadline=time.monotonic()+3
        while self.owner.loop is None or self.owner.kick is None:
            if time.monotonic()>deadline:self.fail('worker did not start')
            time.sleep(.01)
        self.owner.loop.call_soon_threadsafe(self.owner.kick.set)
        while self.owner.fetch_pending:
            if time.monotonic()>deadline:self.fail('fetch did not stop')
            time.sleep(.01)
        time.sleep(.05)

    def test_worker_does_not_dequeue_another_message_after_storage_failure(self):
        calls=[];closed=[]
        def fail(row):raise OSError('disk full fixture')
        self.owner.history.put=fail
        async def get_msg():
            calls.append('fetch');self.owner.receive(self.event());return self.event()
        async def disconnect():closed.append(True)
        client=SimpleNamespace(commands=SimpleNamespace(get_msg=get_msg),disconnect=disconnect)
        self.start_fetch(client)
        self.assertEqual(calls,['fetch']);self.assertTrue(closed)
        self.assertEqual(self.owner.phase,'error')

    def test_worker_does_not_repeat_fetch_after_transport_exception(self):
        calls=[]
        async def get_msg():calls.append('fetch');raise OSError('transport fixture')
        async def disconnect():pass
        client=SimpleNamespace(commands=SimpleNamespace(get_msg=get_msg),disconnect=disconnect)
        self.start_fetch(client)
        self.assertEqual(calls,['fetch'])

    def test_all_contacts_are_reachable_in_bounded_pages(self):
        self.owner.online=True
        self.owner.peers=[dict(identity=f'{i:064x}',label='Contact '+str(i)) for i in range(350)]
        seen=set()
        for offset in range(0,350,32):
            self.owner.dispatch(dict(version=1,action='contacts_page',payload=dict(offset=offset)))
            state=self.owner.snapshot();seen.update(p['identity'] for p in state['peers'])
            self.assertEqual(state['peers_total'],350)
            self.module.encode(state)
        self.assertEqual(len(seen),350)

if __name__=='__main__':unittest.main()
