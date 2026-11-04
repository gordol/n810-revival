"""Event-driven Bleak UART transport for an explicitly selected RNode."""
import asyncio
import queue

UART = '6e400001-b5a3-f393-e0a9-e50e24dcca9e'
RX = '6e400002-b5a3-f393-e0a9-e50e24dcca9e'
TX = '6e400003-b5a3-f393-e0a9-e50e24dcca9e'


class BLESerial:
    def __init__(self, owner, target):
        if not target:
            raise ValueError('Select an explicit RNode BLE name or identifier')
        self.owner, self.target = owner, target
        self.incoming = bytearray()
        self.pending = queue.Queue(maxsize=128)
        self.changed = asyncio.Event()
        self.client = self.open_task = self.sender = None
        self.is_open = self.closing = False

    @property
    def in_waiting(self):
        return len(self.incoming)

    def read(self, count):
        data = bytes(self.incoming[:count])
        del self.incoming[:count]
        return data

    def write(self, data):
        if not self.is_open or self.closing or self.owner.detached:
            raise OSError('BLE interface is closed')
        if len(data) > 65536:
            raise ValueError('BLE write exceeds queue limit')
        self.pending.put_nowait(bytes(data))
        self.owner.loop.call_soon_threadsafe(self.changed.set)
        return len(data)

    def start(self):
        self.open_task = self.owner.loop.create_task(self.open())

    async def open(self):
        try:
            from bleak import BleakClient, BleakScanner
            selected = self.owner.loop.create_future()

            def discovered(device, advertisement):
                name = advertisement.local_name or device.name
                if not selected.done() and (name == self.target or device.address.lower() == self.target.lower()):
                    selected.set_result(device)

            self.owner._status('discovering', None)
            async with BleakScanner(detection_callback=discovered, service_uuids=[UART]):
                device = await selected
            self.owner._status('pairing', None)
            self.client = BleakClient(device, disconnected_callback=self.disconnected, pair=True)
            await self.client.connect()
            self.rx = self.client.services.get_characteristic(RX)
            if self.rx is None or self.client.services.get_characteristic(TX) is None:
                raise ValueError('Selected device has no RNode UART characteristics')
            self.response = 'write-without-response' not in self.rx.properties
            self.is_open = True
            await self.client.start_notify(TX, self.received)
            self.sender = self.owner.loop.create_task(self.send())
            self.owner.connection.start()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.owner._transport_error('BLE: ' + str(error))

    def received(self, characteristic, data):
        if not self.closing:
            self.owner._consume(bytes(data))

    def disconnected(self, client):
        self.is_open = False
        if not self.closing:
            self.owner._transport_error('BLE device disconnected; select Connect to reconnect')

    async def send(self):
        try:
            while True:
                await self.changed.wait()
                self.changed.clear()
                while not self.pending.empty():
                    data = self.pending.get_nowait()
                    # Notifications can arrive while a GATT write is awaiting completion.
                    self.owner._command_written(data)
                    size = max(1, min(512, self.rx.max_write_without_response_size))
                    for offset in range(0, len(data), size):
                        await self.client.write_gatt_char(self.rx, data[offset:offset + size], response=self.response)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.owner._transport_error('BLE write: ' + str(error))

    def close(self):
        self.owner.loop.call_soon_threadsafe(self.owner._shutdown)

    def shutdown(self):
        if not self.closing:
            self.closing = True
            self.owner.loop.create_task(self.aclose())

    async def aclose(self):
        current = asyncio.current_task()
        tasks = [task for task in (self.open_task, self.sender) if task is not None and task is not current]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            if self.client is not None and self.client.is_connected:
                if self.is_open:
                    from driver import KISS
                    data = bytes([KISS.FEND, KISS.CMD_RADIO_STATE, KISS.RADIO_STATE_OFF,
                                  KISS.FEND, KISS.CMD_LEAVE, 0xFF, KISS.FEND])
                    try:
                        await self.client.write_gatt_char(self.rx, data, response=self.response)
                    except Exception:
                        pass
                await self.client.disconnect()
        finally:
            self.is_open = False
            self.owner._serial_closed = True
            self.owner.online = self.owner.interface_ready = False
            self.owner.loop.stop()
