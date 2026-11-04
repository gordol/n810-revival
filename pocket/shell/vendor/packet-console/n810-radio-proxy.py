#!/usr/bin/env python3
"""Transparent phone <-> UV-PRO RFCOMM relay. Phone commands pass through unchanged."""
import collections
import datetime
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import select
import signal
import socket
import subprocess
import tempfile
import threading
import time
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

RADIO = '38:D2:00:00:E3:32'
SPP = '00001101-0000-1000-8000-00805f9b34fb'
VENDOR = '39144315-32fa-40db-85ed-fbfeba2d86e6'
SERVICE_RECORD = '''<record>
<attribute id="0x0001"><sequence><uuid value="0x1101"/></sequence></attribute>
<attribute id="0x0004"><sequence><sequence><uuid value="0x0100"/></sequence><sequence><uuid value="0x0003"/><uint8 value="1"/></sequence></sequence></attribute>
<attribute id="0x0005"><sequence><uuid value="0x1002"/></sequence></attribute>
<attribute id="0x0009"><sequence><sequence><uuid value="0x1101"/><uint16 value="0x0102"/></sequence></sequence></attribute>
<attribute id="0x0100"><text value="UV-PRO N810 Proxy"/></attribute>
</record>'''
PROFILE = '/org/n810/RadioProxy'
AUDIO_PROFILE = PROFILE + '/Audio'
AGENT = '/org/n810/RadioProxyAgent'
TRACE = Path.home() / '.local/state/n810-aprs/proxy-traffic.jsonl'
spec = importlib.util.spec_from_file_location('stream', Path(__file__).with_name('uvpro-stream.py'))
stream = importlib.util.module_from_spec(spec); spec.loader.exec_module(stream)


def stamp():
    return datetime.datetime.now().astimezone().isoformat(timespec='milliseconds')


class Capture:
    def __init__(self):
        self.items = collections.deque(); self.size = 0; self.seq = 0
        self.lock = threading.Lock()

    def add(self, direction, data):
        with self.lock:
            self.seq += 1
            row = dict(seq=self.seq, time=stamp(), monotonic_ns=time.monotonic_ns(), direction=direction, hex=data.hex())
            self.items.append((row, len(data))); self.size += len(data)
            while len(self.items) > 4000 or self.size > 2 * 1024 * 1024:
                _, size = self.items.popleft(); self.size -= size

    def save(self):
        TRACE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.proxy-', dir=TRACE.parent)
        try:
            with os.fdopen(fd, 'w') as f:
                with self.lock:
                    for row, _ in self.items: f.write(json.dumps(row) + '\n')
                f.flush(); os.fsync(f.fileno())
            os.replace(name, TRACE)
        finally:
            if os.path.exists(name): os.unlink(name)
        print('Proxy traffic saved: '+str(TRACE), flush=True)


class Relay:
    def __init__(self, audio=False, capture=None):
        self.audio = audio
        self.stop = threading.Event(); self.phones = queue.Queue(maxsize=1)
        self.capture = capture if capture is not None else Capture()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def accept(self, phone, device):
        phone.setblocking(False)
        try: self.phones.put_nowait((phone, device))
        except queue.Full:
            phone.close(); raise RuntimeError('Proxy already has a phone waiting')
        print('Phone connected to '+('audio' if self.audio else 'control')+' proxy: '+str(device), flush=True)

    def connect_radio(self):
        if self.audio:
            # This unit's BS AOC service was observed on RFCOMM channel 2.
            channel = 2
        else:
            result = subprocess.run(['sdptool','search','--bdaddr',RADIO,'SP'], capture_output=True, text=True, timeout=25)
            match = re.search(r'Channel: (\d+)', result.stdout)
            if not match: raise ConnectionError('radio serial service unavailable')
            channel = int(match.group(1))
        radio = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
        try:
            radio.settimeout(10); radio.connect((RADIO, channel))
            radio.setblocking(False)
            return radio
        except BaseException:
            radio.close(); raise

    def session(self, radio):
        phone = None; outgoing = {radio: bytearray()}
        def packet(text): print(time.strftime('%H:%M:%S'), text, flush=True)
        observers = {
            'radio_to_phone': stream.Observer(packet, lambda text: print('RADIO '+text, flush=True)),
            'phone_to_radio': stream.Observer(command=lambda text: print('PHONE '+text, flush=True))}
        checked = time.monotonic()
        try:
            while not self.stop.is_set():
                try:
                    candidate, device = self.phones.get_nowait()
                    if phone is not None:
                        candidate.close(); print('Extra phone connection refused', flush=True)
                    else:
                        phone = candidate; outgoing[phone] = bytearray()
                        observers['phone_to_radio'] = stream.Observer(command=lambda text: print('PHONE '+text, flush=True))
                except queue.Empty: pass
                reads, writes, _ = select.select(list(outgoing), [s for s,b in outgoing.items() if b], [], .5)
                for source in reads:
                    try: data = source.recv(4096)
                    except BlockingIOError: continue
                    if not data:
                        if source is radio: raise ConnectionError('radio closed serial connection')
                        del outgoing[phone]; phone.close(); phone = None
                        print('Phone disconnected; radio feed continues', flush=True)
                        continue
                    direction = 'radio_to_phone' if source is radio else 'phone_to_radio'
                    self.capture.add(('audio_' if self.audio else '') + direction, data)
                    # Relay unchanged bytes first; observation never injects commands.
                    target = phone if source is radio else radio
                    if target is not None:
                        outgoing[target].extend(data)
                        if len(outgoing[target]) > 262144: raise ConnectionError('relay backpressure limit reached')
                    if not self.audio: observers[direction].feed(data)
                for target in writes:
                    if target not in outgoing: continue
                    try: n = target.send(outgoing[target])
                    except BlockingIOError: continue
                    if n == 0: raise ConnectionError('serial send closed')
                    del outgoing[target][:n]
                if time.monotonic() - checked >= 10:
                    info = subprocess.run(['bluetoothctl','info',RADIO], capture_output=True, text=True, timeout=8)
                    if info.returncode or 'Connected: yes' not in info.stdout: raise ConnectionError('Bluetooth disconnected')
                    print('Radio connected | phone '+('connected' if phone else 'waiting')+' | proxy receive monitor active', flush=True)
                    checked = time.monotonic()
        finally:
            if phone: phone.close()

    def run(self):
        while not self.stop.is_set():
            if self.audio and self.phones.empty():
                self.stop.wait(.5); continue
            radio = None
            try:
                print(('Audio' if self.audio else 'Control')+' proxy connecting to UV-PRO...', flush=True)
                radio = self.connect_radio()
                print('UV-PRO connected | phone proxy ready | unchanged bidirectional relay', flush=True)
                self.session(radio)
            except (OSError, subprocess.SubprocessError) as exc:
                print('Radio disconnected: '+str(exc)+' | retry in 10s', flush=True)
            except Exception as exc:
                print('Proxy session failed: '+repr(exc)+' | retry in 10s', flush=True)
            finally:
                if radio: radio.close()
            self.stop.wait(10)


class Profile(dbus.service.Object):
    def __init__(self, bus, path, relay):
        super().__init__(bus, path); self.relay = relay

    @dbus.service.method('org.bluez.Profile1', in_signature='', out_signature='')
    def Release(self): pass

    @dbus.service.method('org.bluez.Profile1', in_signature='oha{sv}', out_signature='')
    def NewConnection(self, device, fd, properties):
        self.relay.accept(socket.socket(fileno=fd.take()), device)

    @dbus.service.method('org.bluez.Profile1', in_signature='o', out_signature='')
    def RequestDisconnection(self, device):
        # BlueZ closes its transport; relay detects EOF.
        pass


class Agent(dbus.service.Object):
    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='s')
    def RequestPinCode(self, device):
        print('Legacy phone pairing: enter PIN 0000 on Android for '+str(device), flush=True)
        return '0000'
    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Release(self): pass
    @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
    def Cancel(self): pass
    @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='')
    def RequestConfirmation(self, device, passkey):
        print('Phone pairing: %s passkey %06d' % (device, passkey), flush=True)
    @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='')
    def RequestAuthorization(self, device):
        print('Phone pairing authorized: '+str(device), flush=True)
    @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
    def AuthorizeService(self, device, uuid):
        if str(uuid).lower() not in (SPP, VENDOR):
            raise dbus.exceptions.DBusException('Unsupported proxy service', name='org.bluez.Error.Rejected')


def main():
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    adapter = dbus.Interface(bus.get_object('org.bluez','/org/bluez/hci0'), 'org.freedesktop.DBus.Properties')
    previous = {name: adapter.Get('org.bluez.Adapter1', name) for name in ('Alias','Discoverable','Pairable','DiscoverableTimeout','PairableTimeout')}
    manager = dbus.Interface(bus.get_object('org.bluez','/org/bluez'), 'org.bluez.ProfileManager1')
    agent_manager = dbus.Interface(bus.get_object('org.bluez','/org/bluez'), 'org.bluez.AgentManager1')
    relay = Relay(); audio = Relay(audio=True, capture=relay.capture)
    profile = Profile(bus, PROFILE, relay); audio_profile = Profile(bus, AUDIO_PROFILE, audio); agent = Agent(bus, AGENT)
    registered = audio_registered = agent_registered = False
    loop = GLib.MainLoop()
    def stop(signum, frame): loop.quit()
    signal.signal(signal.SIGTERM, stop); signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGHUP, stop)
    try:
        manager.RegisterProfile(PROFILE, SPP, dict(Name='UV-PRO N810 Proxy', Role='server', ServiceRecord=SERVICE_RECORD, Channel=dbus.UInt16(1), RequireAuthentication=dbus.Boolean(True), RequireAuthorization=dbus.Boolean(True)))
        registered = True
        manager.RegisterProfile(AUDIO_PROFILE, VENDOR, dict(Name='BS AOC', Role='server', Channel=dbus.UInt16(2), RequireAuthentication=dbus.Boolean(True), RequireAuthorization=dbus.Boolean(True)))
        audio_registered = True
        agent_manager.RegisterAgent(AGENT, 'NoInputNoOutput'); agent_registered = True
        agent_manager.RequestDefaultAgent(AGENT)
        for name, value in [('Alias',dbus.String('UV-PRO N810 Proxy')),('DiscoverableTimeout',dbus.UInt32(600)),('PairableTimeout',dbus.UInt32(600)),('Pairable',dbus.Boolean(True)),('Discoverable',dbus.Boolean(True))]:
            adapter.Set('org.bluez.Adapter1', name, value)
        print('Phone: pair with UV-PRO N810 Proxy (pairing window 10 minutes; legacy PIN 0000).', flush=True)
        print('Phone commands, including settings changes and transmit requests, are forwarded unchanged.', flush=True)
        print('Traffic capture stays in RAM; last 2 MiB / 4000 chunks saved on shutdown.', flush=True)
        relay.thread.start(); audio.thread.start(); GLib.timeout_add(500, lambda: True); loop.run()
    finally:
        relay.stop.set(); audio.stop.set()
        if audio_registered: manager.UnregisterProfile(AUDIO_PROFILE)
        if registered: manager.UnregisterProfile(PROFILE)
        if agent_registered: agent_manager.UnregisterAgent(AGENT)
        # Worker may be in a bounded SDP/connect call. Let it release sockets before saving.
        if relay.thread.is_alive(): relay.thread.join(timeout=38)
        if audio.thread.is_alive(): audio.thread.join(timeout=12)
        for worker in (relay, audio):
            while not worker.phones.empty(): worker.phones.get_nowait()[0].close()
        relay.capture.save()
        for name, value in previous.items():
            try: adapter.Set('org.bluez.Adapter1', name, value)
            except dbus.DBusException: pass


if __name__ == '__main__': main()
