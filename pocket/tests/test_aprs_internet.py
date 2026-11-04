import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import unittest
from aprs_internet import InternetEvidence,login

class Tests(unittest.TestCase):
    def test_delivery_is_separate_and_scoped(self):
        db=InternetEvidence(':memory:')
        try:
            db.ingest('N7ABC-1>APRS,TCPIP*::W7XYZ-2  :hello{42','2026-11-02T12:00:00Z')
            args=('N7ABC-1','W7XYZ-2','hello','42','2026-11-02T11:00:00Z')
            self.assertTrue(db.message_evidence(*args)['internet_seen'])
            self.assertFalse(db.message_evidence(*args)['recipient_ack'])
            db.ingest('W7XYZ-3>APRS::N7ABC-1  :ack42','2026-11-02T12:01:00Z')
            self.assertFalse(db.message_evidence(*args)['recipient_ack'])
            db.ingest('W7XYZ-2>APRS::N7ABC-1  :ack42','2026-11-02T12:02:00Z')
            self.assertTrue(db.message_evidence(*args)['recipient_ack'])
            self.assertFalse(db.message_evidence(*args[:-1],'2026-11-02T13:00:00Z')['recipient_ack'])
        finally:db.close()
    def test_read_only_login(self):
        self.assertIn('pass -1',login('N7ABC-1','r/47/-122/50'))
        with self.assertRaises(ValueError):login('N7ABC','r/47/-122/50\r\npacket')

class RetentionTests(unittest.TestCase):
    def test_only_message_evidence_retained_and_expires(self):
        import datetime
        db=InternetEvidence(':memory:')
        try:
            self.assertFalse(db.ingest('N7ABC>APRS:!4711.00N/12231.00W>'))
            db.ingest('N7ABC>APRS::W7XYZ    :hello{1','2026-11-01T12:00:00Z')
            db.expire(datetime.datetime(2026,11,2,12,1,tzinfo=datetime.timezone.utc))
            self.assertEqual(db.db.execute('SELECT COUNT(*) FROM internet_packets').fetchone()[0],0)
        finally:db.close()
