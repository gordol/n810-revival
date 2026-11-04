#!/usr/bin/env python3
"""Local KISS access to one radio: many RX monitors and one duplex owner."""
import collections
import json
import importlib.util
from pathlib import Path
import os
import selectors
import socket
import stat

LIMIT = 262144
MAX_FRAME = 65536


def encode(frame):
    return b'\xc0' + frame.replace(b'\xdb', b'\xdb\xdd').replace(b'\xc0', b'\xdb\xdc') + b'\xc0'


class Frames:
    def __init__(self):
        self.buffer = bytearray()
        self.active = self.escaped = False

    def feed(self, data):
        result = []
        for byte in data:
            if byte == 0xc0:
                if self.escaped:
                    self.buffer.clear(); self.active = False; self.escaped = False
                    raise ValueError('invalid KISS escape')
                if self.active and self.buffer: result.append(bytes(self.buffer))
                self.buffer.clear(); self.active = True
            elif self.active:
                if self.escaped:
                    if byte not in (0xdc, 0xdd):
                        self.buffer.clear(); self.active = False; self.escaped = False
                        raise ValueError('invalid KISS escape')
                    self.buffer.append(0xc0 if byte == 0xdc else 0xdb)
                    self.escaped = False
                elif byte == 0xdb: self.escaped = True
                else: self.buffer.append(byte)
                if len(self.buffer) > MAX_FRAME:
                    self.buffer.clear(); self.active = False
                    raise ValueError('KISS frame too large')
        return result


def listen(path):
    if os.path.lexists(path):
        info = os.lstat(path)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
            raise RuntimeError('Refusing to replace non-owned socket: '+path)
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(1)
        try:
            probe.connect(path)
        except ConnectionRefusedError: os.unlink(path)
        else: raise RuntimeError('Socket already active: '+path)
        finally: probe.close()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(path); os.chmod(path, 0o600); server.listen(8); server.setblocking(False)
        return server
    except BaseException:
        server.close(); raise


class Bridge:
    def __init__(self, radio, raw_path='/dev/shm/n810-kiss.sock', rx_path='/dev/shm/n810-kiss-rx.sock', status=print, capture=lambda direction, frame, **metadata: None, packet=lambda text:None):
        self.radio = radio; self.status = status; self.capture = capture
        self.selector = selectors.DefaultSelector()
        self.clients = {}; self.writer = None
        spec=importlib.util.spec_from_file_location('bridge_stream',Path(__file__).with_name('uvpro-stream.py'))
        stream=importlib.util.module_from_spec(spec);spec.loader.exec_module(stream)
        self.radio_frames=stream.Observer(packet=packet,frame=self.receive_frame)
        self.tx = collections.deque(); self.tx_size = 0
        self.radio.setblocking(False)
        self.paths = {}; self.servers = {}
        self.selector.register(radio, selectors.EVENT_READ, 'radio')
        try:
            for path, mode in ((raw_path,'duplex'), (rx_path,'monitor')):
                server = listen(path)
                self.paths[path] = os.lstat(path).st_ino
                self.servers[server] = mode
                self.selector.register(server, selectors.EVENT_READ, mode)
        except BaseException:
            self.close(); raise
        self.status('Raw KISS ready: '+raw_path+' (one duplex owner); '+rx_path+' (RX monitors)')

    def receive_frame(self,frame,origin,wire):
        if (frame[0]&15)>6:return
        if origin=='vendor_reassembled':
            self.capture('radio_to_host',frame,origin=origin,wire_frames=[part.hex() for part in wire])
        else:self.capture('radio_to_host',frame)
        self.broadcast(encode(frame))

    def telemetry_request(self, frame):
        allowed={b'\xff\x01\0'+bytes([len(payload)])+b'\0\2'+command.to_bytes(2,'big')+payload
                 for command,payload in ((6,b'\1'),(6,b'\5'),(6,b'\6'),(20,b''),(10,b''),(33,b'\2'),(76,b''))}
        if frame not in allowed:raise ValueError('Unsupported telemetry request')
        if self.tx_size+len(frame)>LIMIT:raise RuntimeError('Radio output queue full')
        self.tx.append((frame,0,None));self.tx_size+=len(frame);self.modify_radio()

    def bandwidth_request(self, command, payload, original=None):
        if command in (11,14,34,35):
            if self.writer is not None or self.tx:raise RuntimeError('KISS writer/queue must be idle before radio control')
            spec=importlib.util.spec_from_file_location('radio_bandwidth',Path(__file__).with_name('n810-radio-bandwidth.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            backup=module.private_read(Path('/dev/shm/n810-radio-tune-backup.json'))
            restoring=(command==11 and original.hex()==backup.get('desired_settings') and payload.hex()==backup.get('original_settings') or
                       command==14 and original.hex()==backup.get('desired_channel') and payload.hex()==backup.get('original_channel')) if original else False
            if restoring:pass
            elif command==11:
                spec=importlib.util.spec_from_file_location('uvpro_secondary',Path(__file__).with_name('uvpro_secondary.py'))
                secondary=importlib.util.module_from_spec(spec);spec.loader.exec_module(secondary)
                layout=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_text())['Settings']
                index=secondary.bits(payload,*secondary.field(layout,'channel_b_upper'))*16+secondary.bits(payload,*secondary.field(layout,'channel_b_lower'))
                if secondary.settings(original,index,layout)!=payload:raise ValueError('Settings write exceeds B selection')
            elif command==14 and original and len(original) in (25,27) and (module.bits(original,42,30)==0 or original.hex()==backup.get('original_channel') and (backup.get('managed_slot') is True or original[15:25]==b'PocketTune')):
                spec=importlib.util.spec_from_file_location('uvpro_secondary',Path(__file__).with_name('uvpro_secondary.py'))
                secondary=importlib.util.module_from_spec(spec);spec.loader.exec_module(secondary)
                row=dict(rx_mhz=module.bits(payload,42,30)/1e6,tx_mhz=module.bits(payload,10,30)/1e6,
                    rx_ctcss=module.bits(payload,88,16)/100 or None,tx_ctcss=module.bits(payload,72,16)/100 or None,
                    modes=['FM wide' if module.bits(payload,107,1) else 'FM narrow'],name=payload[15:25].split(b'\0',1)[0].decode('ascii'))
                if payload!=secondary.channel(original,original[0],row):raise ValueError('Write exceeds empty repeater memory')
            elif command==14:module.wide_only(original,payload)
            elif command==34:module.disable_beacon_only(original,payload)
            else:raise ValueError('Free VFO tuning disabled while preserving APRS')
        elif (command,payload) not in ((20,b''),(10,b''),(33,b'\2'),(4,b'\3')) and not (command==13 and len(payload)==1):
            raise ValueError('Unsupported radio control request')
        frame=b'\xff\1\0'+bytes([len(payload)])+b'\0\2'+command.to_bytes(2,'big')+payload
        if self.tx_size+len(frame)>LIMIT:raise RuntimeError('Radio output queue full')
        self.tx.append((frame,0,None));self.tx_size+=len(frame);self.modify_radio()

    def modify_client(self, client):
        self.selector.modify(client, selectors.EVENT_READ | (selectors.EVENT_WRITE if self.clients[client]['output'] else 0), 'client')

    def modify_radio(self):
        self.selector.modify(self.radio, selectors.EVENT_READ | (selectors.EVENT_WRITE if self.tx else 0), 'radio')

    def drop(self, client):
        if client not in self.clients: return
        self.selector.unregister(client); del self.clients[client]; client.close()
        if client is self.writer:
            self.writer = None
            # Preserve owner reads, but discard unsent client/write frames.
            reads = {b'\xff\x01\0'+bytes([len(payload)])+b'\0\2'+cmd.to_bytes(2,'big')+payload
                     for cmd, payload in ((20,b''),(10,b''),(33,b'\2'),(76,b''))}
            keep = [item for index, item in enumerate(self.tx)
                    if (index == 0 and item[1]) or (item[2] is None and item[0] in reads)]
            self.tx = collections.deque(keep)
            self.tx_size = sum(len(frame) - offset for frame, offset, _ in keep)
            self.modify_radio()
            self.status('KISS duplex owner disconnected; unsent frames discarded')

    def broadcast(self, data):
        for client in list(self.clients):
            output = self.clients[client]['output']
            if len(output) + len(data) > LIMIT:
                self.status('Slow KISS client disconnected (receive buffer full)'); self.drop(client)
            else:
                output.extend(data); self.modify_client(client)

    def poll(self, timeout=1):
        received = bytearray()
        for key, events in self.selector.select(timeout):
            obj = key.fileobj
            if obj in self.servers:
                client, _ = obj.accept(); client.setblocking(False)
                mode = self.servers[obj]
                if mode == 'duplex' and self.writer is not None:
                    client.close(); self.status('KISS duplex connection refused: another client owns TX'); continue
                self.clients[client] = dict(mode=mode, output=bytearray(), frames=Frames())
                if mode == 'duplex':
                    self.writer = client; self.status('KISS duplex owner attached (transmit capable)')
                self.selector.register(client, selectors.EVENT_READ, 'client')
            elif obj is self.radio:
                if events & selectors.EVENT_READ:
                    try: data = obj.recv(8192)
                    except BlockingIOError: data = None
                    if data == b'': raise ConnectionError('radio serial connection closed')
                    if data:
                        received.extend(data)
                        self.radio_frames.feed(data)
                if events & selectors.EVENT_WRITE and self.tx:
                    frame, offset, original = self.tx[0]
                    try: n = obj.send(frame[offset:])
                    except BlockingIOError: n = None
                    if n == 0: raise ConnectionError('radio serial write closed')
                    if n:
                        self.tx_size -= n; offset += n
                        if offset == len(frame):
                            self.tx.popleft()
                            if original is not None:self.capture('host_to_radio_written', original)
                        else: self.tx[0] = (frame, offset, original)
                        self.modify_radio()
            elif obj in self.clients:
                try:
                    if events & selectors.EVENT_READ:
                        try: data = obj.recv(8192)
                        except BlockingIOError: data = None
                        if data == b'': self.drop(obj); continue
                        if data:
                            client = self.clients[obj]
                            if client['mode'] != 'duplex':
                                raise ValueError('receive-only KISS monitor attempted a write')
                            frames = client['frames'].feed(data)
                            # Validate the whole received batch before enqueueing anything.
                            for frame in frames:
                                if (frame[0] >> 4) or (frame[0] & 15) > 6:
                                    raise ValueError('only KISS port 0, commands 0..6 are supported')
                                if (frame[0] & 15) == 0 and len(frame) == 1:
                                    raise ValueError('empty KISS data frame')
                                if (frame[0] & 15) in (1,2,3,4,5) and len(frame) != 2:
                                    raise ValueError('KISS parameter requires one byte')
                            encoded = [encode(frame) for frame in frames]
                            if self.tx_size + sum(map(len, encoded)) > LIMIT:
                                raise ValueError('KISS transmit queue full')
                            for frame, original in zip(encoded, frames):
                                self.tx.append((frame, 0, original)); self.tx_size += len(frame)
                            self.modify_radio()
                    if events & selectors.EVENT_WRITE and obj in self.clients:
                        output = self.clients[obj]['output']
                        if output:
                            try: n = obj.send(output)
                            except BlockingIOError: n = None
                            if n == 0: self.drop(obj); continue
                            if n: del output[:n]
                            self.modify_client(obj)
                except (OSError, ValueError) as exc:
                    self.status('KISS client disconnected: '+str(exc)); self.drop(obj)
        return bytes(received)

    def close(self):
        for client in list(self.clients):
            self.selector.unregister(client); client.close()
        self.clients.clear(); self.writer = None
        self.tx.clear(); self.tx_size = 0
        for server in self.servers:
            self.selector.unregister(server); server.close()
        self.servers.clear()
        self.selector.close()
        for path, inode in self.paths.items():
            try:
                if os.lstat(path).st_ino == inode: os.unlink(path)
            except FileNotFoundError: pass
        self.paths.clear()
