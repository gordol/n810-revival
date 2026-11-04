import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('meshcore_adapter_test',ROOT/'shell/vendor/apps/domains/meshcore/serial_client.py')
adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)

class HubStatusTests(unittest.TestCase):
    def test_status_decoder_and_unknown_after_exit(self):
        import sys
        spec=importlib.util.spec_from_file_location('test_hub_status',ROOT/'shell/vendor/apps/domains/meshcore/hub_transport.py')
        hub=importlib.util.module_from_spec(spec);sys.modules[spec.name]=hub;spec.loader.exec_module(hub)
        row=hub.status_record(bytes([2,1,1,0,247,0,1,0]),123.0)
        parsed=adapter.parse_bridge_status(hub.status_line(bytes([2,1,1,0,247,0,1,0]),123.0).encode())
        self.assertEqual(parsed['mtu'],247);self.assertEqual(parsed['owner'],2)
        self.assertTrue(parsed['classic_connected']);self.assertTrue(parsed['ble_ready'])
        self.assertFalse(parsed['spp2']);self.assertEqual(parsed['lease_ack_at'],123)
        stopped=adapter.bridge_status('stopped',parsed)
        self.assertFalse(stopped['classic_connected']);self.assertIsNone(stopped['ble_connected'])
        self.assertIsNone(stopped['lease_ack_at']);self.assertEqual(stopped['observed_at'],parsed['observed_at'])
        for bad in (b'HUB_STATUS={',b'ordinary log',b'HUB_STATUS=[]'):
            self.assertIsNone(adapter.parse_bridge_status(bad))
        unknown=adapter.parse_bridge_status(hub.status_line(bytes([2,1,1,0,247,0,1,0])).encode())
        self.assertIsNone(unknown['lease_ack_at'])
        for bad in (b'2,123,1,1,1,247,1,1,0,122', b'1,nan,1,1,1,247,1,1,0,122',
                    b'1,123,2,1,1,247,1,1,0,122', b'1,123,1,1,1,999,1,1,0,122',
                    b'1,123,1,1,1,247,1,1,0,nan', b'1,123,1,1,1,247,1,1,0,122,extra'):
            self.assertIsNone(adapter.parse_bridge_status(b'HUB_STATUS='+bad))
        with self.assertRaises(ValueError):hub.status_record(b'bad')

class HubSelectionTests(unittest.TestCase):
    def test_explicit_hub_uri_and_invalid_targets(self):
        import sys,tempfile
        sys.path.insert(0,str(ROOT/'shell'))
        from meshcore_service import saved_selection
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'meshcore-owner.toml'
            def config(port):
                path.write_text('state="/tmp/private-state"\ninterpreter="/usr/bin/python3"\nstation="test"\ntrusted_peripheral=true\nport="'+port+'"\n')
                path.chmod(0o600)
            uri='htit://2C:BC:BB:9F:DF:72/1/FB:91:48:2D:AA:14/1'
            config(uri);self.assertEqual(saved_selection(root)['port'],uri)
            for bad in (uri.replace('/1/','/31/',1),uri+'?shell=bad','htit://unknown'):
                config(bad)
                with self.assertRaises(ValueError):saved_selection(root)

class SelectionCacheTests(unittest.TestCase):
    def test_cache_skips_toml_parser_and_source_edits_invalidate_it(self):
        import sys,tempfile,tomllib
        sys.path.insert(0,str(ROOT/'shell'))
        from meshcore_service import saved_selection
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'meshcore-owner.toml'
            path.write_text('socket="/tmp/owner.sock"\n');path.chmod(0o600)
            self.assertEqual(saved_selection(root)['socket'],'/tmp/owner.sock')
            cache=path.with_suffix('.cache')
            self.assertEqual(cache.stat().st_mode&0o777,0o600)
            with patch.object(tomllib,'loads',side_effect=AssertionError('Repeated TOML parse')):
                self.assertEqual(saved_selection(root)['socket'],'/tmp/owner.sock')
            path.write_text('socket="/tmp/new.sock"\n')
            self.assertEqual(saved_selection(root)['socket'],'/tmp/new.sock')
            path.write_text('socket="relative"\n')
            with self.assertRaises(ValueError):saved_selection(root)

    def test_corrupt_or_unsafe_cache_falls_back_and_original_permissions_are_required(self):
        import sys,tempfile
        sys.path.insert(0,str(ROOT/'shell'))
        from meshcore_service import saved_selection
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'meshcore-owner.toml'
            path.write_text('socket="/tmp/owner.sock"\n');path.chmod(0o600)
            saved_selection(root);cache=path.with_suffix('.cache')
            cache.write_bytes(b'broken')
            self.assertEqual(saved_selection(root)['socket'],'/tmp/owner.sock')
            cache.chmod(0o666)
            self.assertEqual(saved_selection(root)['socket'],'/tmp/owner.sock')
            self.assertEqual(cache.stat().st_mode&0o777,0o600)
            path.chmod(0o644)
            with self.assertRaises(ValueError):saved_selection(root)

@unittest.skipUnless(importlib.util.find_spec('meshcore'),'requires optional MeshCore client')
class ManagedBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_attach_uses_shared_owner_and_disconnect_releases_only_mesh(self):
        import sys
        sys.path.insert(0,str(ROOT/'shell'))
        class Attachment:
            port='/dev/pts/123';closed=False
            def __init__(self):self.provider=SimpleNamespace(bind_wakeup=lambda callback:None)
            def snapshot(self):return dict(bridge=dict(ble_ready=True,mtu=247),connection_state='online',hub_id='a'*24,generation=2,attachments=[])
            def close(self):self.closed=True
        attachment=Attachment();statuses=[]
        class Client:
            def __init__(self,cx,**kw):self.cx=cx
            async def connect(self):return True
            async def disconnect(self):await self.cx.disconnect()
        with patch('vendor.apps.domains.meshcore.hub_provider.attach_hub',return_value=attachment) as attach, patch('meshcore.MeshCore',Client), patch('asyncio.create_subprocess_exec') as spawn:
            client=await adapter.create_serial_client('htit://2C:BC:BB:9F:DF:72/1/FB:91:48:2D:AA:14/1',bridge_status_callback=statuses.append)
            self.assertEqual(client.cx.port,attachment.port)
            self.assertEqual(statuses[-1]['generation'],2)
            self.assertFalse(attachment.closed)
            self.assertEqual(attach.call_args.args,(1,))
            self.assertEqual(attach.call_args.kwargs['port'],'rfcomm://2C:BC:BB:9F:DF:72/1')
            spawn.assert_not_called()
            await client.disconnect()
            self.assertTrue(attachment.closed)
            self.assertEqual(statuses[-1]['service_state'],'detached')
            self.assertTrue(statuses[-1]['classic_connected'])

    async def test_failed_client_startup_releases_attachment(self):
        import sys
        sys.path.insert(0,str(ROOT/'shell'))
        attachment=SimpleNamespace(port='/dev/pts/123',closed=False,provider=SimpleNamespace(bind_wakeup=lambda callback:None))
        attachment.snapshot=lambda:dict(bridge={},connection_state='online',hub_id='a'*24,generation=1)
        attachment.close=lambda:setattr(attachment,'closed',True)
        class Client:
            def __init__(self,cx,**kw):self.cx=cx
            async def connect(self):raise ConnectionError('SDK failed')
            async def disconnect(self):await self.cx.disconnect()
        with patch('vendor.apps.domains.meshcore.hub_provider.attach_hub',return_value=attachment),patch('meshcore.MeshCore',Client):
            with self.assertRaisesRegex(ConnectionError,'SDK failed'):
                await adapter.create_serial_client('htit://2C:BC:BB:9F:DF:72/1/FB:91:48:2D:AA:14/1')
        self.assertTrue(attachment.closed)

    async def test_rejects_malformed_hub_address_before_spawn(self):
        with patch('asyncio.create_subprocess_exec') as spawn:
            with self.assertRaises(ValueError):await adapter.create_serial_client('htit://:::::::::::::::::/1/FB:91:48:2D:AA:14/1')
            spawn.assert_not_called()

if __name__=='__main__':unittest.main()
