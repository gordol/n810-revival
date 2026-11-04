"""Explicit BLE discovery and authenticated pairing without enabling LoRa."""
import asyncio
import threading
import sys
from ble_transport import UART, RX, TX


class BLESetup:
    def __init__(self, target, publish, port=None):
        self.target, self.publish = target, publish
        self.port = port
        self.loop = asyncio.new_event_loop()
        self.task = None
        self.devices = {}
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()
        self.loop.close()

    def state(self, phase, error=None, authenticated=False):
        self.publish(dict(phase=phase, target=self.target, error=error,
                          authenticated=authenticated, devices=list(self.devices.values())))

    def submit(self, action):
        return asyncio.run_coroutine_threadsafe(self.replace(action), self.loop)

    async def replace(self, action):
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
        self.task = None
        if action == 'ble_stop':
            self.state('idle')
        else:
            self.task = asyncio.create_task(self.work(action))

    async def work(self, action):
        try:
            if action.startswith('rnode_'):
                self.state('configuring_usb')
                option = '--bluetooth-on' if action == 'rnode_bluetooth_on' else '--bluetooth-pair'
                process = await asyncio.create_subprocess_exec(sys.executable, '-B', '-m',
                    'RNS.Utilities.rnodeconf', self.port, option,
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT)
                try:
                    output, _ = await process.communicate(input=b'\n')
                    marker = b'Enabling Bluetooth...' if action == 'rnode_bluetooth_on' else b'Putting device into Bluetooth pairing mode.'
                    rejected = any(text in output for text in (b'Could not open', b'EEPROM is invalid', b'Invalid EEPROM data', b'Cannot continue.'))
                    if process.returncode or rejected or len(output) > 16384 or b'Device connected' not in output or marker not in output:
                        raise OSError('RNode did not confirm the Bluetooth setup command. Check the USB cable and port ownership.')
                finally:
                    if process.returncode is None:
                        process.terminate()
                        await process.wait()
                self.state('pairing_window' if action == 'rnode_pairing_mode' else 'bluetooth_enabled')
                return
            from bleak import BleakClient, BleakScanner
            selected = self.loop.create_future()
            self.devices.clear()
            self.state('scanning')

            def discovered(device, advertisement):
                name = advertisement.local_name or device.name or 'Unnamed UART device'
                match = name == self.target or device.address.lower() == self.target.lower()
                row = dict(name=name[:80], id=device.address[:80], rssi=advertisement.rssi, selected=match)
                if len(self.devices) < 32 or device.address in self.devices:
                    if self.devices.get(device.address) != row:
                        self.devices[device.address] = row
                        self.state('scanning')
                if match and not selected.done():
                    selected.set_result(device)

            async with BleakScanner(detection_callback=discovered, service_uuids=[UART]):
                if action == 'ble_scan':
                    await self.loop.create_future()
                device = await selected
            self.state('pairing')
            response = self.loop.create_future()
            received = bytearray()

            def notified(characteristic, data):
                received.extend(data)
                if len(received) > 4096:
                    del received[:-4096]
                if b'\xc0\x08\x46\xc0' in received and not response.done():
                    response.set_result(True)

            def disconnected(client):
                if not response.done():
                    response.set_exception(OSError('Pairing connection closed. If macOS accepted the code, select Pair again.'))
            response.add_done_callback(lambda future: None if future.cancelled() else future.exception())

            async with BleakClient(device, pair=True, disconnected_callback=disconnected) as client:
                # macOS ignores pair=True. Accessing the protected UART asks the
                # OS to authenticate; CoreBluetooth has no passkey-entry API.
                self.state('authenticating')
                await client.start_notify(TX, notified)
                await client.write_gatt_char(RX, bytes.fromhex('c00873c0'), response=True)
                await response
            self.state('paired', authenticated=True)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            detail = str(error).strip() or type(error).__name__
            if sys.platform == 'darwin' and action == 'ble_pair':
                detail = ('macOS BLE authentication did not complete. Enter the display code only in the macOS prompt. '
                          'If no prompt appears, Stop setup and choose USB port to use the cable. ' + detail)
            self.state('error', detail[:480])

    def stop(self):
        return self.submit('ble_stop')

    def close(self):
        if not self.loop.is_closed():
            future = self.stop()
            future.add_done_callback(lambda _: self.loop.call_soon_threadsafe(self.loop.stop))
