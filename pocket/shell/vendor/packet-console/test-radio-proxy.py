"""Isolated protocol observation and relay tests. No Bluetooth radio access."""
import importlib.util
from pathlib import Path
import socket
import threading
import tempfile
import json
import stat
import time

spec = importlib.util.spec_from_file_location('proxy', Path(__file__).with_name('n810-radio-proxy.py'))
proxy = importlib.util.module_from_spec(spec); spec.loader.exec_module(proxy)

def frame(group, command, body=b''):
    return b'\xff\x01\0' + bytes([len(body)]) + group.to_bytes(2,'big') + command.to_bytes(2,'big') + body

def address(call, last=False):
    return bytes(ord(c) << 1 for c in call.ljust(6)) + bytes([0x60 | last])

packet = address('APRS') + address('TEST', True) + b'\x03\xf0!4713.13N/12150.61W_test'
packets = []; commands = []
obs = proxy.stream.Observer(packets.append, commands.append)
wire = frame(2,14,b'\x01\x02') + frame(2,57,b'\x80'+packet)
for byte in wire: obs.feed(bytes([byte]))
assert 'WRITE_RF_CH' in commands[0]
assert len(packets)==1 and packets[0].startswith('TEST>APRS')
obs = proxy.stream.Observer(packets.append)
kiss = b'\xc0\0' + packet.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc') + b'\xc0'
obs.feed(kiss); assert len(packets)==2
obs.feed(frame(2,0x8039,b'\x80'+packet)); assert len(packets)==2

relay = proxy.Relay()
radio, radio_peer = socket.socketpair(); phone, phone_peer = socket.socketpair()
radio.setblocking(False); errors=[]
relay.accept(phone, 'test-phone')
def session():
    try: relay.session(radio)
    except Exception as exc: errors.append(exc)
t = threading.Thread(target=session); t.start()
def receive(sock, expected):
    sock.settimeout(5); result=b''
    while len(result)<len(expected): result+=sock.recv(65536)
    assert result==expected
try:
    # Larger than one read; includes all byte values and packet delimiters.
    payload = bytes(range(256))*80
    phone_peer.sendall(payload); receive(radio_peer,payload)
    radio_peer.sendall(wire); receive(phone_peer,wire)
    phone_peer.close()
    time.sleep(.1)
    radio_peer.sendall(frame(2,57,b'\x80'+packet))
    time.sleep(.1)
    assert t.is_alive(), errors
finally:
    relay.stop.set(); t.join(3);radio.close();radio_peer.close();phone_peer.close()
assert not t.is_alive() and not errors, errors
assert b''.join(bytes.fromhex(row['hex']) for row,_ in relay.capture.items if row['direction']=='phone_to_radio')==payload
print('PASS: fragmented command decoding, packet extraction, reply rejection, exact bidirectional relay, phone disconnect preserves receiver, raw traffic capture')

with tempfile.TemporaryDirectory() as directory:
    proxy.TRACE = Path(directory) / 'capture.jsonl'
    capture = proxy.Capture()
    for i in range(4100): capture.add('phone_to_radio', b'x' * 1024)
    assert len(capture.items) <= 4000 and capture.size <= 2 * 1024 * 1024
    capture.save()
    rows = [json.loads(line) for line in proxy.TRACE.read_text().splitlines()]
    assert rows[-1]['seq'] == 4100 and rows[0]['seq'] > 1
    assert stat.S_IMODE(proxy.TRACE.stat().st_mode) == 0o600
print('PASS: bounded RAM capture, ordered snapshot, private file permissions')

relay = proxy.Relay(audio=True)
radio, radio_peer = socket.socketpair(); phone, phone_peer = socket.socketpair()
radio.setblocking(False); relay.accept(phone, 'test-audio-phone')
t = threading.Thread(target=lambda: relay.session(radio)); t.start()
try:
    payload = bytes(range(256)) * 3
    phone_peer.sendall(payload); receive(radio_peer, payload)
    radio_peer.sendall(payload[::-1]); receive(phone_peer, payload[::-1])
finally:
    relay.stop.set(); t.join(3)
    for endpoint in (radio,radio_peer,phone_peer): endpoint.close()
assert not t.is_alive()
assert {row['direction'] for row,_ in relay.capture.items} == {'audio_phone_to_radio','audio_radio_to_phone'}
print('PASS: independent vendor/audio relay preserves all bytes and labels capture separately')
