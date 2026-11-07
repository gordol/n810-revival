import importlib.util
import json
import os
from pathlib import Path
import socket
import stat
import struct
import tempfile
import time
import unittest


def load(name, filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

endpoint=load('read_endpoint','n810-radio-read-owner.py')
live=load('read_live','n810-radio-live.py')
bridge_module=load('read_bridge','n810-kiss-bridge.py')


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.sent=[];self.owner=live.Telemetry(self.sent.append,self.root/'live.json',self.root/'control.json')
        self.server=endpoint.Endpoint(submit=self.owner.start_read,status=self.owner.read_progress,cancel=self.owner.cancel_read,
            path=self.root/'endpoint/control.sock',authenticate=lambda client:os.getuid())
        self.clients=[]

    def tearDown(self):
        self.server.close();self.owner.close()
        for c in self.clients:c.close()
        self.tmp.cleanup()

    def client(self):
        c=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);c.connect(str(self.server.path));c.settimeout(.1);self.clients.append(c);self.server.poll();return c

    def request(self,value):
        c=self.client();c.sendall(json.dumps(value).encode()+b'\n')
        for _ in range(4):self.server.poll()
        return json.loads(c.recv(endpoint.RESPONSE_LIMIT+1))

    def submit(self,ident='one'):
        now=time.time();return dict(version=1,operation='read_current',request_id=ident,requested_at=now,expires_at=now+20)

    def reply(self,cmd,raw):
        body=b'\0'+raw;return b'\xff\1\0'+bytes([len(body)])+struct.pack('>HH',2,0x8000|cmd)+body

    def test_paused_request_progress_three_reads_and_dedup(self):
        value=self.submit();result=self.request(value);self.assertTrue(result['ok']);self.assertEqual(result['result']['state'],'pending');self.assertFalse(self.owner.state['enabled'])
        for index,cmd in enumerate((20,10,33)):
            self.owner.tick(index);self.assertEqual(int.from_bytes(self.sent[-1][6:8],'big'),cmd)
            layout=self.owner.layouts[{20:'StatusExt',10:'Settings',33:'BSSSettings'}[cmd]]
            raw=bytes((sum(row[1] for row in layout)+7)//8)
            self.owner.feed(self.reply(cmd,raw))
        status=self.request(dict(version=1,operation='status',request_id='one'))['result']
        self.assertEqual(status['state'],'complete');self.assertEqual(status['completed'],3)
        self.assertTrue(all(r['observed_at']>0 for r in status['results'].values()))
        count=len(self.sent);self.assertEqual(self.request(value)['result']['state'],'complete');self.owner.tick(4);self.assertEqual(len(self.sent),count)
        self.assertFalse(self.owner.state['enabled']);self.assertFalse((self.root/'control.json').exists())

    def test_actual_owner_state_after_reply_no_heartbeat_fabrication(self):
        self.server.radio_live=self.owner.read_state
        initial=self.request(self.submit());self.assertFalse(initial['radio_live']['enabled'])
        self.owner.tick(0);self.owner.feed(self.reply(20,bytes(4)))
        heartbeat=self.owner.state['published_at']
        result=self.request(dict(version=1,operation='status',request_id='one'))
        self.assertEqual(result['radio_live'],self.owner.state)
        self.assertEqual(result['radio_live']['fields']['status'],result['result']['results']['20']['observed_at'])
        self.assertEqual(result['radio_live']['published_at'],heartbeat);self.assertEqual(self.owner.state['published_at'],heartbeat)
        self.assertFalse(result['radio_live']['enabled'])
        result['radio_live']['fields'].clear();self.assertIn('status',self.owner.state['fields'])
        self.server.radio_live=lambda:{'large':'x'*endpoint.RESPONSE_LIMIT}
        self.assertFalse(self.request(dict(version=1,operation='status',request_id='one'))['ok'])

    def test_cancel_and_late_reply_drains_without_freshening(self):
        self.request(self.submit());self.owner.tick(0)
        self.assertEqual(self.request(dict(version=1,operation='cancel',request_id='one'))['result']['state'],'cancelled')
        self.assertFalse(self.request(self.submit('two'))['ok'])
        self.owner.feed(self.reply(20,bytes(4)));self.assertNotIn('status',self.owner.state)
        self.assertTrue(self.request(self.submit('two'))['ok'])

    def test_bad_requests_do_not_call_owner(self):
        for value in (dict(version=True,operation='status',request_id='one'),dict(version=1,operation='tune',request_id='one'),dict(version=1,operation='status',request_id='one',extra=True)):
            self.assertFalse(self.request(value)['ok'])
        self.assertEqual(self.sent,[])
        c=self.client();c.sendall(b'{}\n{}\n')
        for _ in range(3):self.server.poll()
        self.assertFalse(json.loads(c.recv(1000))['ok']);self.assertEqual(self.owner.read_history,{})

    def test_private_directory_and_symlink_rejected(self):
        kwargs=dict(submit=lambda _:None,status=lambda _:None,cancel=lambda _:None,authenticate=lambda _:os.getuid())
        folder=self.root/'public';folder.mkdir(mode=0o755)
        with self.assertRaises(ValueError):endpoint.Endpoint(path=folder/'control.sock',**kwargs)
        link=self.root/'link';link.symlink_to(self.server.path.parent,target_is_directory=True)
        with self.assertRaises(ValueError):endpoint.Endpoint(path=link/'control.sock',**kwargs)
        self.assertTrue(self.server.path.exists())

    def test_client_cap_and_deep_json_rejected(self):
        for _ in range(endpoint.CLIENT_LIMIT):self.client()
        c=self.client();self.assertEqual(c.recv(1),b'');self.assertEqual(len(self.server.clients),endpoint.CLIENT_LIMIT)
        self.server.poll(time.monotonic()+3)
        c=self.client();c.sendall(b'['*1500+b'0'+b']'*1500+b'\n')
        for _ in range(3):self.server.poll()
        self.assertFalse(json.loads(c.recv(1000))['ok']);self.assertEqual(self.owner.read_history,{})

    def test_bounds_slow_client_and_response(self):
        c=self.client();c.sendall(b'x'*(endpoint.REQUEST_LIMIT+1))
        for _ in range(3):self.server.poll()
        self.assertFalse(json.loads(c.recv(1000))['ok'])
        c=self.client();self.server.poll(time.monotonic()+3);self.assertEqual(c.recv(1),b'')
        self.server.status=lambda ident:{'large':'x'*endpoint.RESPONSE_LIMIT}
        self.assertFalse(self.request(dict(version=1,operation='status',request_id='x'))['ok'])
        self.server.status=lambda ident:{'bad':float('nan')}
        self.assertFalse(self.request(dict(version=1,operation='status',request_id='x'))['ok'])

    def test_same_uid_and_permissions_and_no_stale_unlink(self):
        self.assertEqual(stat.S_IMODE(self.server.path.parent.stat().st_mode),0o700)
        self.assertEqual(stat.S_IMODE(self.server.path.stat().st_mode),0o600)
        self.server.authenticate=lambda client:os.getuid()+1
        c=self.client();self.assertEqual(c.recv(1),b'');self.assertFalse(self.server.clients)
        with self.assertRaises(OSError):endpoint.Endpoint(submit=lambda _:None,status=lambda _:None,cancel=lambda _:None,path=self.server.path,authenticate=lambda _:os.getuid())
        self.assertTrue(self.server.path.exists())

    def test_kiss_receive_continues_with_one_shot_reads(self):
        radio,peer=socket.socketpair();bridge=bridge_module.Bridge(radio,str(self.root/'kiss.sock'),str(self.root/'rx.sock'),status=lambda _:None)
        self.owner.send=bridge.telemetry_request
        try:
            c=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.clients.append(c);c.connect(str(self.root/'rx.sock'));c.settimeout(.1);bridge.poll(0)
            self.request(self.submit());self.owner.tick(0);bridge.poll(.01)
            peer.settimeout(.1);self.assertEqual(peer.recv(100),live.request(20))
            frame=bridge_module.encode(b'\0APRS receive bytes');peer.sendall(frame+self.reply(20,bytes(4)))
            incoming=bridge.poll(.01);self.owner.feed(incoming);bridge.poll(.01)
            self.assertEqual(c.recv(1000),frame);self.assertEqual(self.owner.read_progress('one')['completed'],1)
            self.assertIsNone(bridge.writer)
        finally:bridge.close();radio.close();peer.close()

    def test_kiss_writer_disconnect_preserves_owner_read_queue(self):
        radio,peer=socket.socketpair();bridge=bridge_module.Bridge(radio,str(self.root/'kiss.sock'),str(self.root/'rx.sock'),status=lambda _:None)
        self.owner.send=bridge.telemetry_request
        try:
            writer=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.clients.append(writer);writer.connect(str(self.root/'kiss.sock'));bridge.poll(0)
            self.request(self.submit());self.owner.tick(0)
            bridge.drop(bridge.writer);bridge.poll(.01)
            peer.settimeout(.1);self.assertEqual(peer.recv(100),live.request(20))
        finally:bridge.close();radio.close();peer.close()

    def test_unsent_bandwidth_write_is_not_preserved_on_writer_drop(self):
        radio,peer=socket.socketpair();bridge=bridge_module.Bridge(radio,str(self.root/'kiss.sock'),str(self.root/'rx.sock'),status=lambda _:None)
        try:
            writer=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.clients.append(writer);writer.connect(str(self.root/'kiss.sock'));bridge.poll(0)
            write=b'\xff\1\0\1\0\2\0\x0e'+b'x'
            bridge.tx.append((write,0,None));bridge.tx_size+=len(write)
            bridge.telemetry_request(live.request(20));bridge.drop(bridge.writer);bridge.poll(.01)
            peer.settimeout(.1);self.assertEqual(peer.recv(100),live.request(20))
            self.assertEqual(bridge.tx_size,0)
        finally:bridge.close();radio.close();peer.close()

    @unittest.skipUnless(hasattr(socket,'SO_PEERCRED'),'Linux peer credentials')
    def test_real_same_uid_credentials(self):
        self.server.authenticate=endpoint.peer_uid
        self.assertFalse(self.request(dict(version=1,operation='status',request_id='missing'))['ok'])


if __name__=='__main__':unittest.main()
