#!/usr/bin/env python3
"""HTIT hub host adapter. No automatic MeshCore commands or radio transmissions."""
import argparse
import binascii
from collections import deque
import getpass
import os
import pty
import re
import select
import socket
import struct
import sys
import termios
import time
import tty
from dataclasses import dataclass

MAX_PAYLOAD = 512


class PhysicalLinkError(OSError):
    """The shared byte stream failed; every service must drop its endpoint."""


def crc16(data):
    return binascii.crc_hqx(data, 0xffff)


@dataclass(frozen=True)
class Frame:
    service: int
    op: int
    id: int = 0
    data: bytes = b''

    def encode(self):
        if len(self.data) > MAX_PAYLOAD:
            raise ValueError('hub payload exceeds 512 bytes')
        raw = struct.pack('<BBBHH', 1, self.service, self.op, self.id, len(self.data)) + self.data
        raw += struct.pack('<H', crc16(raw))
        return b'~' + raw.replace(b'}', b'}]').replace(b'~', b'}^') + b'~'


class Decoder:
    def __init__(self):
        self.buf = bytearray()
        self.active = self.escape = self.bad = False

    def feed(self, data):
        frames = []
        for byte in data:
            if byte == 0x7e:
                if self.active and not self.bad and not self.escape and len(self.buf) >= 9:
                    version, service, op, ident, length = struct.unpack('<BBBHH', self.buf[:7])
                    if version == 1 and length <= MAX_PAYLOAD and len(self.buf) == length + 9 and crc16(self.buf[:-2]) == int.from_bytes(self.buf[-2:], 'little'):
                        frames.append(Frame(service, op, ident, bytes(self.buf[7:-2])))
                self.buf.clear()
                self.active, self.escape, self.bad = True, False, False
                continue
            if not self.active or self.bad:
                continue
            if self.escape:
                byte ^= 0x20
                self.escape = False
            elif byte == 0x7d:
                self.escape = True
                continue
            if len(self.buf) == MAX_PAYLOAD + 9:
                self.bad = True
            else:
                self.buf.append(byte)
        return frames


class CompanionDecoder:
    """MeshCore serial packets are '<' + uint16 LE length + BLE payload."""
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        self.buf.extend(data)
        packets = []
        while len(self.buf) >= 3:
            if self.buf[0] != 60:
                raise ValueError('invalid MeshCore serial marker')
            n = int.from_bytes(self.buf[1:3], 'little')
            if not 1 <= n <= MAX_PAYLOAD:
                raise ValueError('invalid MeshCore companion packet size')
            if len(self.buf) < n + 3:
                break
            packets.append(bytes(self.buf[3:n+3]))
            del self.buf[:n+3]
        return packets


ERRORS = {1: 'invalid request/peer unavailable', 2: 'busy/not ready', 3: 'ownership/permission required',
          4: 'transport failed', 5: 'unsupported service/operation', 6: 'packet exceeds negotiated BLE MTU'}


class RfcommPort:
    """Linux RFCOMM stream without a privileged /dev/rfcomm binding."""
    def __init__(self, address, channel):
        self.sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        self.sock.settimeout(10)
        try:
            self.sock.connect((address, channel))
            self.sock.settimeout(2)
        except BaseException:
            self.sock.close()
            raise

    def fileno(self):
        return self.sock.fileno()

    def read(self, count):
        return self.sock.recv(count)

    def write(self, data):
        self.sock.sendall(data)
        return len(data)

    def close(self):
        self.sock.close()


class Link:
    def __init__(self, port):
        match = re.fullmatch(r'rfcomm://([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})/([0-9]+)', port)
        if match:
            channel = int(match[2])
            if not 1 <= channel <= 30:
                raise ValueError('RFCOMM channel must be 1–30')
            self.serial = RfcommPort(match[1], channel)
        else:
            import serial
            self.serial = serial.Serial(port=None, baudrate=115200, timeout=0, write_timeout=2,
                                        exclusive=True if sys.platform != 'win32' else None)
            # Do not assert the CP2102 boot/reset control lines when opening.
            self.serial.dtr = False
            self.serial.rts = False
            self.serial.port = port
            self.serial.open()
        self.decoder = Decoder()
        self.inbox = deque()
        self.ident = 0

    def send(self, service, op, data=b''):
        self.ident = self.ident % 65535 + 1
        frame = Frame(service, op, self.ident, data)
        wire = frame.encode()
        try:
            written = self.serial.write(wire)
        except OSError as error:
            raise PhysicalLinkError('Hub write failed: '+str(error)) from error
        if written != len(wire):
            raise PhysicalLinkError('short hub write; reconnect explicitly')
        return frame.id

    def read(self, timeout=0):
        if select.select([self.serial.fileno()], [], [], timeout)[0]:
            try:data = self.serial.read(4096)
            except OSError as error:raise PhysicalLinkError('Hub read failed: '+str(error)) from error
            if not data:
                raise PhysicalLinkError('hub transport closed')
            self.inbox.extend(self.decoder.feed(data))

    def request(self, op, data=b'', timeout=3):
        ident = self.send(0, op, data)
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            for frame in tuple(self.inbox):
                if frame.service == 0 and frame.op == op | 0x80 and frame.id == ident:
                    self.inbox.remove(frame)
                    check_reply(frame)
                    return frame.data[1:]
            self.read(min(.1, max(0, until-time.monotonic())))
        raise TimeoutError('hub did not acknowledge request; no automatic replay')

    def close(self):
        self.serial.close()

    def hello(self):
        # Some USB drivers pulse control lines during open despite preconfigured
        # DTR/RTS. Retry only this idempotent query while the ESP32 boots.
        until = time.monotonic() + 6
        while time.monotonic() < until:
            try:
                result = self.request(1, timeout=1)
                self.inbox = deque(f for f in self.inbox if not (f.service == 0 and f.op == 0x81))
                return result
            except TimeoutError:
                pass
        raise TimeoutError('hub did not answer startup handshake')


def check_reply(frame):
    if not frame.data:
        raise ValueError('empty hub reply')
    if frame.data[0]:
        raise RuntimeError(ERRORS.get(frame.data[0], 'hub error ' + str(frame.data[0])))


def address(text):
    raw = bytes.fromhex(text.replace(':', ''))
    if len(raw) != 6:
        raise argparse.ArgumentTypeError('BLE address must contain six bytes')
    return raw


def show_event(frame):
    if frame.service == 0 and frame.op == 0x90 and len(frame.data) >= 8:
        mac = ':'.join('%02X' % b for b in frame.data[1:7])
        rssi = int.from_bytes(frame.data[7:8], 'little', signed=True)
        name = frame.data[8:].decode('utf8', 'replace')
        print(f'{mac} type={frame.data[0]} RSSI={rssi} name={name!r}', flush=True)
    elif frame.service == 0 and frame.op >= 0x91:
        print('hub: ' + frame.data.decode('utf8', 'replace'), file=sys.stderr, flush=True)


def wait_ready(link, interactive=True):
    until = time.monotonic() + 75
    renewed = time.monotonic()
    while time.monotonic() < until:
        link.read(.1)
        while link.inbox:
            frame = link.inbox.popleft()
            show_event(frame)
            if frame.service == 0 and frame.op == 0x93:
                return
            if frame.service == 0 and frame.op == 0x92:
                raise RuntimeError('BLE connection did not become ready')
            if frame.service == 0 and frame.op == 0x94:
                if not interactive:raise ValueError('BLE pairing required; pair the radio with the standalone hub helper first')
                pin = getpass.getpass('MeshCore BLE PIN (six digits): ')
                if len(pin) != 6 or not pin.isascii() or not pin.isdecimal():
                    raise ValueError('BLE PIN must be six ASCII digits')
                link.request(6, pin.encode())
        if time.monotonic() - renewed > 10:
            link.request(7)
            renewed = time.monotonic()
    raise TimeoutError('BLE readiness timeout')


class Endpoint:
    def __init__(self, name):
        self.master, self.slave = pty.openpty()
        tty.setraw(self.slave)
        os.set_blocking(self.master, False)
        self.output = bytearray()
        print(f'{name}={os.ttyname(self.slave)}', flush=True)

    def queue(self, data):
        if len(self.output) + len(data) > 32768:
            raise BufferError('host endpoint stalled; stopping rather than losing packets')
        self.output.extend(data)

    def flush(self):
        if self.output:
            try:
                n = os.write(self.master, self.output)
                del self.output[:n]
            except BlockingIOError:
                pass

    def close(self):
        os.close(self.master)
        os.close(self.slave)


def status_record(raw, lease_ack_at=None):
    if len(raw) != 8:
        raise ValueError('invalid hub status')
    return dict(kind='htit', phase='online', observed_at=time.time(),
                classic_connected=True, owner=raw[0], ble_ready=bool(raw[1]),
                ble_connected=bool(raw[2]), mtu=int.from_bytes(raw[4:6], 'little'),
                spp1=bool(raw[6]), spp2=bool(raw[7]), lease_ack_at=lease_ack_at)


def status_line(raw, lease_ack_at=None):
    row=status_record(raw, lease_ack_at)
    fields=['1', str(row['observed_at'])]
    fields.extend(str(int(row[k])) for k in ('classic_connected','ble_connected','ble_ready','mtu','owner','spp1','spp2'))
    fields.append('' if lease_ack_at is None else str(lease_ack_at))
    return 'HUB_STATUS=' + ','.join(fields)


def bridge(link, args):
    endpoints = {}
    radio = None
    claimed = False
    lease_ack_at = None
    def publish(raw):
        if getattr(args, "parent_watch", False):
            print(status_line(raw, lease_ack_at), flush=True)
    try:
        if getattr(args, 'rnode', False):
            # One physical Link owns all services. Merely opening this PTY
            # does not acquire the LoRa lease or enable the radio.
            from rnode_adapter import Adapter
            endpoints[3] = Endpoint('RNODE_PORT')
            radio = Adapter(link, endpoints[3])
        if args.ble:
            link.request(7)
            claimed = True
            lease_ack_at = time.time()
            link.request(4, bytes([args.address_type]) + args.ble)
            wait_ready(link,not getattr(args,'parent_watch',False))
            status = link.request(2)
            publish(status)
            print(f'BLE negotiated MTU={int.from_bytes(status[4:6], "little")}', file=sys.stderr, flush=True)
            endpoints[1] = Endpoint('MESHCORE_PORT')
        if args.peer is not None:
            endpoints[2] = Endpoint('PEER_PORT')
        if not endpoints:
            raise ValueError('bridge requires --ble, --peer, or --rnode')
        decoder = CompanionDecoder()
        queues = {1: deque(), 2: deque()}
        pending = {}
        renewed = time.monotonic()
        renewal = None
        status_query = None
        status_at = time.monotonic()
        while True:
            readers = [link.serial.fileno()] + [e.master for e in endpoints.values()]
            writers = [e.master for e in endpoints.values() if e.output]
            deadlines = [start + 12 for _, start in pending.values()]
            if claimed:deadlines.append(renewal[1]+20 if renewal else renewed+10)
            if getattr(args,'parent_watch',False):deadlines.append(status_query[1]+12 if status_query else status_at+5)
            if radio:
                if radio.claimed:deadlines.append(radio.last_renew+10)
                deadlines.extend(start+65 for _,_,start in radio.pending.values())
            timeout=max(.01,min(deadlines)-time.monotonic()) if deadlines else None
            readable, writable, _ = select.select(readers, writers, [], timeout)
            if link.serial.fileno() in readable:
                link.read()
            for service, endpoint in endpoints.items():
                if endpoint.master in writable:endpoint.flush()
                if endpoint.master in readable:
                    raw = os.read(endpoint.master, 511 if service == 2 else 1024)
                    if not raw:
                        raise OSError('PTY closed')
                    if service == 3:
                        for command, data in radio.decoder.feed(raw):radio.command(command, data)
                        continue
                    packets = decoder.feed(raw) if service == 1 else [bytes([args.peer]) + raw]
                    queues[service].extend(packets)
                    if len(queues[service]) > 64:
                        raise BufferError('outbound queue full; no silent dropping')
            while link.inbox:
                frame = link.inbox.popleft()
                if frame.service == 3:
                    if radio:
                        try:radio.frame(frame)
                        except (ConnectionError, TimeoutError, ValueError, BufferError) as error:
                            print('RNODE_ERROR=' + str(error), file=sys.stderr, flush=True)
                            link.send(3,6)
                            endpoints.pop(3).close();radio=None
                    continue
                if frame.service == 0:
                    if renewal and frame.op == 0x87 and frame.id == renewal[0]:
                        check_reply(frame)
                        renewal = None
                        lease_ack_at = time.time()
                    if status_query and frame.op == 0x82 and frame.id == status_query[0]:
                        check_reply(frame)
                        publish(frame.data[1:])
                        status_query = None
                    show_event(frame)
                    if claimed and frame.op == 0x92:
                        raise OSError('MeshCore connection ended; reconnect explicitly')
                elif frame.op == 0x81:
                    if frame.service not in pending or frame.id != pending[frame.service][0]:
                        raise ValueError('unexpected transport acknowledgement')
                    check_reply(frame)
                    del pending[frame.service]
                elif frame.op == 0x90 and frame.service in endpoints:
                    if frame.service == 1:
                        endpoints[1].queue(b'>' + struct.pack('<H', len(frame.data)) + frame.data)
                    elif frame.data and frame.data[0] == args.peer:
                        endpoints[2].queue(frame.data[1:])
            for service, queue in queues.items():
                if service not in pending and queue:
                    ident = link.send(service, 1, queue.popleft())
                    pending[service] = (ident, time.monotonic())
            if radio:
                try:radio.tick()
                except (ConnectionError, TimeoutError, ValueError) as error:
                    print('RNODE_ERROR=' + str(error), file=sys.stderr, flush=True)
                    link.send(3,6)
                    endpoints.pop(3).close();radio=None
            if any(time.monotonic() - start > 12 for _, start in pending.values()):
                raise TimeoutError('packet acknowledgement missing; no automatic replay')
            if renewal and time.monotonic() - renewal[1] > 20:
                raise TimeoutError("owner lease acknowledgement missing")
            if status_query and time.monotonic() - status_query[1] > 12:
                status_query = None  # Read-only telemetry may be retried; old sample stays stale.
            if getattr(args, 'parent_watch', False) and status_query is None and time.monotonic() - status_at > 5:
                status_at = time.monotonic()
                status_query = (link.send(0, 2), status_at)
            if claimed and renewal is None and time.monotonic() - renewed > 10:
                renewed = time.monotonic()
                renewal = (link.send(0, 7), renewed)
    finally:
        if radio and radio.claimed:
            try:link.send(3,6)
            except Exception:pass
        if claimed:
            try:
                link.request(8, timeout=1)
            except Exception:
                pass  # Firmware lease expires even if the host cable disappeared.
        for endpoint in endpoints.values():
            endpoint.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True, help='USB/RFCOMM device path or Linux rfcomm://MAC/CHANNEL')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('info')
    sub.add_parser('pair', help='USB-only, opens a two-minute Classic pairing window')
    sub.add_parser('scan', help='explicit five-second BLE scan; no automatic selection')
    b = sub.add_parser('bridge')
    b.add_argument('--ble', type=address)
    b.add_argument('--address-type', type=int, choices=(0, 1), default=0)
    b.add_argument('--peer', type=int, choices=(0, 1, 2))
    b.add_argument('--rnode', action='store_true', help='Expose onboard LoRa as a local RNode PTY on this same hub connection')
    b.add_argument('--parent-watch',action='store_true',help=argparse.SUPPRESS)
    args = parser.parse_args()
    if getattr(args,'parent_watch',False):
        import threading,signal
        def parent_closed():
            # A daemon must not hold BufferedReader's lock while the main
            # thread exits after a transport error.
            while os.read(0,4096):pass
            os.kill(os.getpid(),signal.SIGINT)
        threading.Thread(target=parent_closed,daemon=True).start()
    link = Link(args.port)
    try:
        hello = link.hello()
        if len(hello) != 3 or hello[0] != 1:
            raise ValueError('unsupported hub protocol')
        print(f'Hub protocol={hello[0]} host_id={hello[1]} capabilities=0x{hello[2]:02x}', file=sys.stderr)
        if args.command == 'info':
            status = link.request(2)
            if len(status) != 8:
                raise ValueError('invalid hub status')
            print(dict(owner=status[0], ble_ready=bool(status[1]), ble_connected=bool(status[2]),
                       scanning=bool(status[3]), mtu=int.from_bytes(status[4:6], 'little'),
                       spp1=bool(status[6]), spp2=bool(status[7])))
        elif args.command == 'pair':
            pin = getpass.getpass('New Classic Bluetooth pairing PIN (4–16 digits): ')
            if not 4 <= len(pin) <= 16 or not pin.isascii() or not pin.isdecimal():
                raise ValueError('PIN must contain 4–16 ASCII digits')
            link.request(9, pin.encode())
            print('Pair with Pocket-HTIT-Hub within two minutes using that PIN.')
        elif args.command == 'scan':
            link.request(7)
            try:
                link.request(3)
                until = time.monotonic() + 6
                while time.monotonic() < until:
                    link.read(.1)
                    while link.inbox:
                        show_event(link.inbox.popleft())
            finally:
                link.request(8)
        else:
            if args.peer == hello[1]:
                raise ValueError('peer cannot be this host')
            bridge(link, args)
    finally:
        link.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        print('hub: ' + str(exc), file=sys.stderr)
        sys.exit(1)
