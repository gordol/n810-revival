"""MeshCore SDK connection through Android's bonded-device GATT adapter."""
import asyncio
from contextlib import suppress
from hmac import compare_digest
import secrets
import socket


class AndroidBLE:
    def __init__(self):
        self.writer = None
        self.task = None

    def set_reader(self, reader):
        self.reader = reader

    def set_disconnect_callback(self, callback):
        self.disconnected = callback

    async def connect(self):
        loop = asyncio.get_running_loop()
        token = secrets.token_hex(24)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(2)
            listener.setblocking(False)
            launch = await asyncio.create_subprocess_exec(
                'am', 'start', '-n', 'org.pocketrevival.uvpro/.SelectRadio',
                '--ei', 'port', str(listener.getsockname()[1]), '--es', 'token', token,
                '--ez', 'meshcore', 'true', stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT)
            try:
                result, _ = await asyncio.wait_for(launch.communicate(), 8)
            finally:
                if launch.returncode is None:
                    launch.kill()
                    await launch.wait()
            if launch.returncode or b'Error' in result:
                raise OSError('Install the Pocket radio adapter APK and retry')
            async with asyncio.timeout(120):
                while True:
                    peer, _ = await loop.sock_accept(listener)
                    incoming, outgoing = await asyncio.open_connection(sock=peer, limit=1024)
                    try:
                        try:
                            header = await asyncio.wait_for(incoming.readline(), 3)
                        except (TimeoutError, ValueError, OSError):
                            continue
                        if not compare_digest(header, token.encode() + b'\n'):
                            continue
                        if await asyncio.wait_for(incoming.readline(), 40) != b'READY\n':
                            raise ConnectionError('Android could not open the MeshCore BLE service')
                        self.writer = outgoing
                        self.task = asyncio.create_task(self.receive(incoming))
                        return 'Android MeshCore BLE'
                    finally:
                        if self.writer is not outgoing:
                            outgoing.close()

    async def receive(self, incoming):
        try:
            while True:
                length = int.from_bytes(await incoming.readexactly(2), 'big')
                if not 1 <= length <= 512:
                    raise ValueError('Invalid MeshCore notification size')
                await self.reader.handle_rx(await incoming.readexactly(length))
        except (EOFError, OSError, ValueError) as error:
            await self.disconnect()
            await self.disconnected(str(error) or 'Android BLE disconnected')
        finally:
            if self.writer:
                self.writer.close()

    async def send(self, data):
        if not self.writer or not 1 <= len(data) <= 512:
            raise ConnectionError('MeshCore BLE is disconnected or packet exceeds 512 bytes')
        self.writer.write(len(data).to_bytes(2, 'big') + data)
        await self.writer.drain()

    async def disconnect(self):
        task, self.task = self.task, None
        writer, self.writer = self.writer, None
        if writer:
            writer.close()
        if task and task is not asyncio.current_task():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
