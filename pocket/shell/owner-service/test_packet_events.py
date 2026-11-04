from pathlib import Path
import socket
import tempfile
import time
import unittest
from unittest import mock
from packet_events import PacketEvents


class PacketEventTests(unittest.TestCase):
    def test_initial_capture_then_only_packet_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path=str(Path(directory)/'feed.sock')
            server=socket.socket(socket.AF_UNIX)
            server.bind(path);server.listen()
            captures=[]
            events=PacketEvents(path,lambda:captures.append('snapshot'))
            peer=None
            try:
                events.connect();peer,_=server.accept()
                self.assertEqual(captures,['snapshot'])
                peer.sendall(b'Listening\n@FEED {"version":1}\n')
                events.ready()
                self.assertEqual(len(captures),1)
                peer.sendall(b'12:00:00 CALL>APRS ctl=03 pid=f0 ')
                events.ready()
                self.assertEqual(len(captures),1)
                peer.sendall(b'position\n12:00:01 OTHER>APRS ctl=03 pid=f0 position\n')
                events.ready()
                self.assertEqual(len(captures),2)
                with mock.patch.object(events.selector,'select',side_effect=KeyboardInterrupt) as select:
                    with self.assertRaises(KeyboardInterrupt):events.run()
                    select.assert_called_once_with(None)
                self.assertEqual(len(captures),2)
                peer.close();peer=None;before=time.monotonic();events.ready()
                self.assertIsNone(events.stream)
                self.assertGreaterEqual(events.retry_at,before+10)
            finally:
                events.close()
                if peer:peer.close()
                server.close()

    def test_unavailable_feed_arms_one_reconnect_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            captures=[]
            events=PacketEvents(str(Path(directory)/'absent'),lambda:captures.append(1),lambda _:None)
            try:
                before=time.monotonic();events.connect()
                self.assertIsNone(events.stream)
                self.assertGreaterEqual(events.retry_at,before+10)
                self.assertEqual(captures,[])
            finally:events.close()


if __name__=='__main__':unittest.main()
