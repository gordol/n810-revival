"""Receive UV-PRO serial bytes from the user-selected Android Bluetooth device."""
from datetime import datetime, timezone
from hmac import compare_digest
import secrets
import socket
import subprocess
import time

from console_source import Source
from device_retained import owner


class PhoneFeed(Source):
    def _work(self):
        try:
            with socket.socket() as server:
                server.bind(('127.0.0.1', 0))
                server.listen(2)
                server.settimeout(.4)
                token = secrets.token_hex(24)
                launch = subprocess.run(
                    ['am', 'start', '-n', 'org.pocketrevival.uvpro/.SelectRadio',
                     '--ei', 'port', str(server.getsockname()[1]), '--es', 'token', token],
                    capture_output=True, timeout=6, text=True)
                if launch.returncode or 'Error' in launch.stdout + launch.stderr:
                    raise OSError('Install the Pocket UV-PRO receiver APK and retry')
                self._publish(False, 'Choose the paired UV-PRO in the Android receiver')
                deadline = time.monotonic() + 120
                while not self.stopped.is_set() and time.monotonic() < deadline:
                    try:
                        peer, _ = server.accept()
                    except TimeoutError:
                        continue
                    with peer:
                        peer.settimeout(3)
                        stream = peer.makefile('rb')
                        with stream:
                            try:
                                header = stream.readline(64)
                            except OSError:
                                continue
                            if not compare_digest(header, token.encode() + b'\n'):
                                continue
                            self.client = peer
                            peer.settimeout(30)
                            if stream.readline(16) != b'READY\n':
                                raise ConnectionError('Bluetooth serial connection failed; check the radio and any other active client')
                            peer.settimeout(None)
                            self._receive(stream)
                            return
                raise TimeoutError('Radio selection timed out; reconnect This device to retry')
        except (OSError, ValueError, subprocess.SubprocessError) as error:
            self._publish(False, str(error))
        finally:
            self.client = None

    def read(self, now):
        result = super().read(now)
        live = result['live']['data']
        live['history_source'] = 'Fairphone Bluetooth serial · local receive history'
        return result

    @property
    def feed_control(self):
        online = self.state['online']
        return dict(version=1, type='state', revision=self.state['revision'],
                    controller=dict(available=online, powered=True if online else None, devices=[]),
                    reception=dict(enabled=True, suspended_reason=self.state.get('error')),
                    radio=dict(connected=online), capabilities=[])

    @property
    def feed_control_online(self):
        return not self.stopped.is_set()

    def _receive(self, stream):
        history = owner('n810-frame-history.py').History()
        records = history.records

        def capture(frame, origin, wire):
            if not frame or frame[0] != 0:
                return
            row = dict(time=datetime.now(timezone.utc).isoformat(timespec='milliseconds'),
                       direction='radio_to_host', frame=frame.hex())
            if origin == 'vendor_reassembled':
                row.update(origin=origin, wire_frames=[part.hex() for part in wire])
            history.add(row)

        observer = owner('uvpro-stream.py').Observer(frame=capture)
        self._publish(True, rows=[])
        while not self.stopped.is_set():
            chunk = stream.read1(8192)
            if not chunk:
                raise ConnectionError('Phone radio disconnected; reconnect This device to retry')
            before = records[-1] if records else None
            observer.feed(chunk)
            if records and records[-1] is not before:
                self._publish(True, rows=list(records))
