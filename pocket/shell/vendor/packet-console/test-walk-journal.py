#!/usr/bin/env python3
"""Synthetic walk journal persistence checks; no radio or device access."""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock


spec=importlib.util.spec_from_file_location('walk_journal',Path(__file__).with_name('n810-walk-journal.py'))
journal=importlib.util.module_from_spec(spec)
spec.loader.exec_module(journal)


class JournalTests(unittest.TestCase):
    def test_private_buffered_jsonl_checkpoint_and_close_preserve_order(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'walks'
            with mock.patch.object(journal.time,'monotonic',return_value=100):
                log=journal.Journal(folder)
            self.assertEqual(log.due,130)
            self.assertEqual(stat.S_IMODE(folder.stat().st_mode),0o700)
            self.assertEqual(stat.S_IMODE(log.path.stat().st_mode),0o600)
            log.add('session',callsign='TEST',tag='fixture')
            log.add('position',position={'lat':47.0,'lon':-122.0})
            self.assertEqual(log.path.read_bytes(),b'')
            expected=list(log.rows)
            with mock.patch.object(journal.os,'fsync',wraps=os.fsync) as sync:
                with mock.patch.object(journal.time,'monotonic',return_value=125):
                    log.flush()
                sync.assert_called_once_with(log.fd)
            self.assertEqual(log.rows,[])
            self.assertEqual(log.due,155)
            checkpoint=log.path.read_bytes()
            self.assertEqual(checkpoint,(''.join(json.dumps(row,separators=(',',':'))+'\n' for row in expected)).encode())
            for row in expected:
                self.assertIsNotNone(datetime.datetime.fromisoformat(row['time']).tzinfo)
            log.add('stopped',reason='fixture complete')
            log.close()
            self.assertTrue(log.path.read_bytes().startswith(checkpoint))
            records=[json.loads(line) for line in log.path.read_bytes().splitlines()]
            self.assertEqual([row['type'] for row in records],['session','position','stopped'])
            with self.assertRaises(OSError):
                os.fstat(log.fd)

    def test_256th_record_checkpoints_without_reordering(self):
        with tempfile.TemporaryDirectory() as root:
            log=journal.Journal(Path(root)/'walks')
            try:
                for number in range(255):
                    log.add('received',number=number)
                self.assertEqual(log.path.read_bytes(),b'')
                with mock.patch.object(journal.os,'fsync',wraps=os.fsync) as sync:
                    log.add('received',number=255)
                    sync.assert_called_once_with(log.fd)
                self.assertEqual(log.rows,[])
                rows=[json.loads(line) for line in log.path.read_bytes().splitlines()]
                self.assertEqual([row['number'] for row in rows],list(range(256)))
            finally:
                log.close()

    def test_partial_writes_complete_before_fsync(self):
        with tempfile.TemporaryDirectory() as root:
            log=journal.Journal(Path(root)/'walks')
            log.add('note',text='creek crossing')
            expected=(json.dumps(log.rows[0],separators=(',',':'))+'\n').encode()
            write=os.write
            calls=[]
            def partial(fd,data):
                calls.append('write')
                return write(fd,data[:7])
            def sync(fd):
                calls.append('fsync')
                self.assertEqual(log.path.read_bytes(),expected)
            try:
                with mock.patch.object(journal.os,'write',side_effect=partial):
                    with mock.patch.object(journal.os,'fsync',side_effect=sync):
                        log.flush()
                self.assertGreater(calls.count('write'),1)
                self.assertEqual(calls[-1],'fsync')
                self.assertEqual(log.rows,[])
            finally:
                log.close()

    def test_close_closes_fd_when_checkpoint_fails(self):
        with tempfile.TemporaryDirectory() as root:
            log=journal.Journal(Path(root)/'walks')
            log.add('note',text='unsaved')
            with mock.patch.object(journal.os,'write',return_value=0):
                with self.assertRaisesRegex(OSError,'Walk log write failed'):
                    log.close()
            self.assertEqual(len(log.rows),1)
            with self.assertRaises(OSError):
                os.fstat(log.fd)


if __name__=='__main__':
    unittest.main()
