from pathlib import Path
import importlib
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SHELL=Path(__file__).resolve().parents[1]/'shell'
sys.path.insert(0,str(SHELL))
from app_registry import Registry
from device_connection import from_peer
from device_feed import ServiceReceive,bounded_receive
from service_selection import Selection
from connections import Connections

class Provider:
    def __init__(self,state):self.state=state;self.callback=None;self.closed=False;self.path='/tmp/gateway.sock'
    def snapshot(self):return self.state
    def bind_wakeup(self,callback):self.callback=callback
    def drain(self):pass
    def close(self):self.closed=True
    def publish(self,state):
        self.state=state
        if self.callback:self.callback()

class PeerTests(unittest.TestCase):
    def wait(self,fn):
        end=time.monotonic()+3
        while not fn():
            if time.monotonic()>end:self.fail('publication timeout')
            time.sleep(.005)
    def test_bounded_records_preserve_order_and_original_values(self):
        from device_services import encode
        rows=[dict(frame='ab'*400,direction='radio_to_host',time=i) for i in range(200)]
        result=bounded_receive(dict(online=True,raw_records=rows,revision=7),encode)
        self.assertLess(len(encode(result)),17000)
        self.assertEqual(result['raw_records'],rows[-len(result['raw_records']):])
        self.assertEqual(result['omitted_records']+len(result['raw_records']),200)
    def test_subscription_reuses_receive_decoder_and_ignores_telemetry_only_updates(self):
        record=dict(direction='radio_to_host',frame='0102',time='original')
        p=Provider(dict(owner_online=True,receive=dict(online=True,revision=1,raw_records=[record])))
        with patch('console_source.decode_records',side_effect=lambda rows:rows) as decode:
            source=ServiceReceive(p);self.addCleanup(source.close)
            self.wait(lambda:source.state['online'])
            self.assertEqual(source.read(0)['live']['data']['raw_records'],[record])
            source.refresh();time.sleep(.03);self.assertEqual(decode.call_count,1)
            p.state=dict(owner_online=False,error='Peer lost');source.refresh()
            self.wait(lambda:not source.state['online'])
            self.assertEqual(source.state['error'],'Peer lost')
    def test_group_grants_and_gateway_lifetime(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry=Registry(SHELL);registry.configure_reticulum(register=False)
            package='_pocket_reticulum_'+str(abs(hash(str((registry.root/'vendor/apps/domains/reticulum').resolve()))))
            module=importlib.import_module(package+'.service_transport')
            gateway=Provider({});remote={}
            def factory(peer,name):
                remote[name]=Provider(dict(version=1,owner_online=True,device='peer-host',services=[],telemetry=dict(system=dict(source='peer-host')),receive=dict(online=True,revision=1,raw_records=[])))
                return remote[name]
            gateway.remote=factory
            granted=dict(services=[dict(id=n,operations=['snapshot','subscribe']) for n in ('device','reticulum')])
            with patch.object(module,'ReticulumTransport') as transport:
                transport.return_value.exchange.return_value=granted
                source=from_peer(gateway,'a'*32,registry)
            connection=Connections(Path(tmp)/'db',SHELL/'vendor/packet-console',Path(tmp),lambda *_:(source,'peer-host'))
            selection=Selection(registry,tmp,initial=gateway);connection.reticulum=selection
            self.addCleanup(selection.close);self.addCleanup(connection.close)
            connection.connect('peer','a'*32);self.wait(lambda:not connection.busy)
            self.assertEqual(connection.error,'');self.assertIs(selection.carrier,gateway)
            self.assertEqual(connection.read(0)['live']['data']['system']['source'],'peer-host')
            connection.disconnect();selection.drain()
            self.assertIs(selection.provider,gateway);self.assertFalse(gateway.closed)
            self.wait(lambda:remote['device'].closed)
    def test_no_grant_fails_before_starting_remote_providers(self):
        registry=Registry(SHELL);registry.configure_reticulum(register=False)
        package='_pocket_reticulum_'+str(abs(hash(str((registry.root/'vendor/apps/domains/reticulum').resolve()))))
        module=importlib.import_module(package+'.service_transport')
        carrier=SimpleNamespace(path='/tmp/gateway.sock',remote=lambda *_:self.fail('Started ungranted provider'))
        with patch.object(module,'ReticulumTransport') as transport:
            transport.return_value.exchange.return_value=dict(services=[])
            with self.assertRaisesRegex(ValueError,'not shared device'):from_peer(carrier,'a'*32,registry)

    def test_switch_to_peer_keeps_gateway_adopted_by_previous_device(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry=Registry(SHELL);gateway=Provider({});remote=Provider({})
            selection=Selection(registry,tmp,initial=gateway)
            old=SimpleNamespace(adopted={'reticulum':gateway},bind_wakeup=lambda cb:None,close=lambda:None)
            peer=SimpleNamespace(gateway=gateway,bindings={'reticulum':remote},bind_wakeup=lambda cb:None,close=lambda:None)
            connection=Connections(Path(tmp)/'db',SHELL/'vendor/packet-console',Path(tmp),lambda *_:(peer,'peer'))
            connection.reticulum=selection;connection.source=old
            self.addCleanup(selection.close);self.addCleanup(connection.close)
            connection.connect('peer','a'*32);self.wait(lambda:not connection.busy)
            self.assertEqual(connection.error,'')
            self.assertIs(selection.provider,remote);self.assertIs(selection.carrier,gateway)
            self.assertNotIn(gateway,selection.retired)
            selection.drain();self.assertFalse(gateway.closed)
            connection.disconnect();selection.drain()
            self.assertIs(selection.provider,gateway);self.assertFalse(gateway.closed)

    def test_revocation_retains_records_and_capture_time_until_valid_recovery(self):
        record=dict(direction='radio_to_host',frame='0102',time='original')
        receive=dict(online=True,revision=1,raw_records=[record])
        provider=Provider(dict(owner_online=True,pid=100,receive=receive))
        with patch('console_source.decode_records',side_effect=lambda rows:rows):
            source=ServiceReceive(provider);self.addCleanup(source.close)
            self.wait(lambda:source.state['online'])
            captured=source.state['captured']
            provider.state=dict(owner_online=False,error='Grant revoked',receive=receive);source.refresh()
            self.wait(lambda:not source.state['online'])
            self.assertEqual(source.state['raw_records'],[record])
            self.assertEqual(source.state['captured'],captured)
            self.assertEqual(source.state['error'],'Grant revoked')
            provider.state=dict(owner_online=True,pid=100,receive=None);source.refresh()
            self.wait(lambda:'unavailable' in (source.state.get('error') or ''))
            self.assertTrue(source.worker.is_alive())
            provider.state=dict(owner_online=True,pid=101,receive=receive);source.refresh()
            self.wait(lambda:source.state['online'])

    def test_source_restart_with_reused_revision_decodes_new_records(self):
        first=dict(direction='radio_to_host',frame='0102',time='first')
        second=dict(direction='radio_to_host',frame='0304',time='second')
        provider=Provider(dict(owner_online=True,pid=100,receive=dict(online=True,revision=1,raw_records=[first])))
        with patch('console_source.decode_records',side_effect=lambda rows:rows):
            source=ServiceReceive(provider);self.addCleanup(source.close)
            self.wait(lambda:source.state['raw_records']==[first])
            provider.state=dict(owner_online=True,pid=101,receive=dict(online=True,revision=1,raw_records=[second]))
            source.refresh();self.wait(lambda:source.state['raw_records']==[second])

    def test_cancelled_pending_device_never_adopts_or_closes_gateway(self):
        with tempfile.TemporaryDirectory() as tmp:
            entered=threading.Event();release=threading.Event();discarded=threading.Event()
            gateway=Provider({});remote=Provider({})
            candidate=SimpleNamespace(gateway=gateway,bindings={'reticulum':remote},
                bind_wakeup=lambda cb:None,close=lambda:(remote.close(),discarded.set()))
            def build(*args):
                entered.set();release.wait();return candidate,'late peer'
            registry=Registry(SHELL);selection=Selection(registry,tmp,initial=gateway)
            connection=Connections(Path(tmp)/'db',SHELL/'vendor/packet-console',Path(tmp),build)
            connection.reticulum=selection
            self.addCleanup(selection.close);self.addCleanup(connection.close);self.addCleanup(release.set)
            connection.connect('peer','a'*32);self.assertTrue(entered.wait(3))
            connection.disconnect();release.set();self.assertTrue(discarded.wait(3))
            selection.drain()
            self.assertIsNone(connection.source);self.assertTrue(remote.closed)
            self.assertIs(selection.provider,gateway);self.assertFalse(gateway.closed)

    def test_socket_and_device_service_paths_preserve_same_decoded_packet(self):
        from console_source import snapshot
        from device_retained import decode_records
        from device_services import encode
        from wire import decode
        def address(call,last):return bytes(ord(c)<<1 for c in call.ljust(6))+bytes([0x60|last])
        frame=b'\0'+address('APRS',0)+address('N0DEM',1)+b'\x03\xf0>Peer transport check'
        record=dict(time='2026-10-26T08:00:00+00:00',direction='radio_to_host',frame=frame.hex())
        with tempfile.TemporaryDirectory(dir='/tmp') as tmp:
            endpoint=Path(tmp)/'replay.sock'
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(endpoint));listener.listen(1)
                def serve():
                    client,_=listener.accept()
                    with client:
                        client.sendall((json.dumps(dict(type='snapshot',version=1,records=1))+'\n'+json.dumps(record)+'\n').encode())
                server=threading.Thread(target=serve,daemon=True);server.start()
                socket_rows=snapshot(endpoint);server.join(3)
            received=bounded_receive(dict(online=True,revision=1,raw_records=socket_rows),encode)
            provider=Provider(decode(encode(dict(version=1,owner_online=True,pid=100,receive=received))))
            source=ServiceReceive(provider);self.addCleanup(source.close)
            self.wait(lambda:bool(source.state['packets']))
            live=source.read(0)['live']['data']
            self.assertEqual(live['raw_records'],socket_rows)
            self.assertEqual(live['packets'],decode_records(socket_rows))
            self.assertEqual(live['packets'][0]['time'],record['time'])
            self.assertIn('N0DEM>APRS',live['packets'][0]['raw'])

if __name__=='__main__':unittest.main()
