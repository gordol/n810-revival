"""Host-side Android bridge protocol checks using a synthetic paired adapter."""
import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shell'))
from meshcore_service import validate_selection
from vendor.apps.domains.meshcore.android_ble import AndroidBLE


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_paired_selection_authentication_and_packet_boundaries(self):
        config = dict(port='android-ble://paired', interpreter='/bin/python',
                      station='fixture', state='/tmp/fixture', trusted_peripheral=True)
        self.assertEqual(validate_selection(config)['mode'], 'local')
        connection = AndroidBLE()
        received = asyncio.Queue()
        disconnected = asyncio.Event()

        class Reader:
            async def handle_rx(self, data):
                await received.put(data)

        async def dropped(reason):
            disconnected.set()

        async def launch(*args, **options):
            port = int(args[args.index('port') + 1])
            token = args[args.index('token') + 1].encode()
            _, wrong = await asyncio.open_connection('127.0.0.1', port)
            wrong.write(b'wrong\n')
            wrong.close()
            self.input, self.output = await asyncio.open_connection('127.0.0.1', port)
            self.output.write(token + b'\nREADY\n')

            class Launched:
                returncode = 0
                async def communicate(self):
                    return b'created', None
            return Launched()

        connection.set_reader(Reader())
        connection.set_disconnect_callback(dropped)
        with patch('asyncio.create_subprocess_exec', launch):
            await asyncio.wait_for(connection.connect(), 2)
        try:
            await connection.send(b'abc')
            self.assertEqual(await self.input.readexactly(5), b'\x00\x03abc')
            self.output.write(b'\x00')
            await self.output.drain()
            self.output.write(b'\x03xyz\x00\x01z')
            self.assertEqual(await asyncio.wait_for(received.get(), 2), b'xyz')
            self.assertEqual(await asyncio.wait_for(received.get(), 2), b'z')
            self.output.close()
            await asyncio.wait_for(disconnected.wait(), 2)
            self.assertIsNone(connection.writer)
        finally:
            self.output.close()
            await connection.disconnect()
