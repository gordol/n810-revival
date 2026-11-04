from pathlib import Path
import importlib.util
import socket
import sys
import threading
import unittest
from unittest.mock import patch

path=Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum/service_transport.py'
sys.path.insert(0,str(path.parent))
spec=importlib.util.spec_from_file_location('service_transport_test',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class TransportTests(unittest.TestCase):
    def test_backend_replacement_ends_subscription_for_existing_provider_recovery(self):
        transport=module.ReticulumTransport('/unused','ab'*16)
        stopped=threading.Event();seen=[]
        def events(update,stop):
            update(dict(owner_online=True,data_bridge=dict(services=[])))
        with patch.object(transport,'exchange',return_value=dict(version=1,owner_online=True)),patch.object(transport.events,'subscribe',side_effect=events):
            with self.assertRaisesRegex(ValueError,'subscription ended'):
                transport.subscribe(seen.append,stopped)
        self.assertEqual(len(seen),1)

    def test_explicit_grant_allows_bounded_catalogue_startup(self):
        self.assertEqual(module.request_timeout(dict(action='service_share')),120)
        self.assertEqual(module.request_timeout(dict(action='snapshot')),25)

    def test_stream_fragmentation_large_reply_and_subscription_cancellation(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();self.addCleanup(listener.close)
        ready=threading.Event();released=threading.Event()
        def server():
            with listener.accept()[0] as client:
                client.recv(4096)
                raw=module.encode(dict(version=1,value='x'*6000))
                for offset in range(0,len(raw),37):client.sendall(raw[offset:offset+37])
            with listener.accept()[0] as client:
                client.recv(4096)
                client.sendall(module.encode(dict(version=1,revision=1))+module.encode(dict(version=1,revision=2)))
                ready.set();client.recv(1);released.set()
        thread=threading.Thread(target=server,daemon=True);thread.start()
        transport=module.SocketTransport(listener.getsockname(),socket.AF_INET)
        self.assertEqual(len(transport.exchange(dict(version=1,action='snapshot'))['value']),6000)
        stopped=threading.Event();seen=[]
        def consume():
            try:transport.subscribe(seen.append,stopped)
            except OSError:pass
        worker=threading.Thread(target=consume,daemon=True);worker.start();self.assertTrue(ready.wait(2))
        import time
        deadline=time.monotonic()+2
        while len(seen)<2 and time.monotonic()<deadline:time.sleep(.005)
        self.assertEqual([x['revision'] for x in seen],[1,2])
        stopped.set();transport.close();worker.join(2);self.assertFalse(worker.is_alive());self.assertTrue(released.wait(2))
    def test_cleartext_network_connections_rejected_before_opening_socket(self):
        for address,family in [(('192.0.2.1',123),socket.AF_INET),(('localhost',123),socket.AF_INET),
                               (('::ffff:192.0.2.1',123),socket.AF_INET6),(('::',123),socket.AF_INET6)]:
            with self.subTest(address=address),self.assertRaises(ValueError):module.SocketTransport(address,family)
        module.SocketTransport(('::1',123),socket.AF_INET6)
        module.SocketTransport(('::ffff:127.0.0.1',123),socket.AF_INET6)

    def test_binary_unicode_bytes_and_invalid_length(self):
        import wire
        value=dict(version=1,text='héllo',data=b'\x00\xff')
        raw=module.encode(value);self.assertEqual(module.decode(raw),value)
        self.assertTrue(raw.startswith(b'PS\x02'))
        for bad in (raw+b'x',raw[:-1],b'PS\x02'+b'\xff'*4,b'{"version":1}\n'):
            with self.assertRaises(ValueError):module.decode(bad)
        with self.assertRaises(ValueError):module.encode(dict(version=1,n=float('nan')))

    def test_oversize_and_unterminated_frames_are_rejected(self):
        for raw in (b'{}',b'x'*(module.LIMIT+1)):
            with self.assertRaises(ValueError):module.decode(raw)
        with self.assertRaises(ValueError):module.encode(dict(version=1,value='x'*module.LIMIT))
    def test_failed_command_is_not_retried(self):
        listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();self.addCleanup(listener.close)
        received=[]
        def server():
            with listener.accept()[0] as client:received.append(client.recv(4096))
        thread=threading.Thread(target=server);thread.start()
        transport=module.SocketTransport(listener.getsockname(),socket.AF_INET)
        with self.assertRaises((ValueError,ConnectionError)):transport.exchange(dict(version=1,action='write',request_id='one'))
        thread.join(2);self.assertEqual(len(received),1)

if __name__=='__main__':unittest.main()
