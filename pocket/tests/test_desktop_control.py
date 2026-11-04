"""Desktop actions must not wait through an extra model/render iteration."""
from pathlib import Path
import selectors
import socket
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from desktop_control import Control
from runtime_codec import frame,unpack,HEADER


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='pocket-ctl-',dir='/tmp')
        self.addCleanup(self.temporary.cleanup)
        self.selector=selectors.DefaultSelector();self.addCleanup(self.selector.close)
        self.opened=[]
        self.control=Control(Path(self.temporary.name)/'ui.sock',self.selector,self.opened.append)
        self.addCleanup(self.control.close)

    def client(self):
        client=socket.socket(socket.AF_UNIX);client.settimeout(1)
        client.connect(str(self.control.path));self.addCleanup(client.close)
        return client

    def turn(self):
        events=self.selector.select(1)
        self.assertTrue(events)
        for key,mask in events:key.data.ready(mask)

    def test_queued_action_completes_before_another_model_iteration(self):
        client=self.client();client.sendall(frame({'activate':'System'}))
        self.turn()
        self.assertEqual(self.opened,['System'])
        self.assertTrue(unpack(client.recv(8192)[HEADER:])['ok'])

    def test_slow_partial_client_does_not_block_other_actions(self):
        slow=self.client();self.turn()
        self.assertEqual(len(self.control.clients),1)
        payload=frame({'activate':'System'});slow.sendall(payload[:9]);self.turn()
        fast=self.client();fast.sendall(frame({'activate':'Connections'}));self.turn()
        self.assertEqual(self.opened,['Connections'])
        self.assertTrue(unpack(fast.recv(8192)[HEADER:])['ok'])
        slow.sendall(payload[9:]);self.turn()
        self.assertEqual(self.opened,['Connections','System'])
        self.assertTrue(unpack(slow.recv(8192)[HEADER:])['ok'])


if __name__=='__main__':unittest.main()
