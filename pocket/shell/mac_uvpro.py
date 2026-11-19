"""Direct macOS Serial Port Profile transport for the paired UV-PRO."""
import contextlib
import fcntl
import json
import hashlib
import importlib.util
import os
from pathlib import Path
import select
import struct
import subprocess
import sys
import time
import threading
import uuid

HERE = Path(__file__).resolve().parent
HELPER = HERE.parent / 'bluetooth-macos/uvpro'
OWNER = HERE / 'owner-service'


def enabled():
    from mac_tray import enabled as local_mac
    return local_mac() and bool(os.environ.get('POCKET_FIELD_PACK'))


class Link:
    def __init__(self, process):
        self.process = process
        self.buffer = bytearray()

    def receive(self, until):
        fd = self.process.stdout.fileno()
        if not select.select([fd], [], [], max(0, until-time.monotonic()))[0]:
            raise TimeoutError('UV-PRO Bluetooth reply timed out')
        data = os.read(fd, 8192)
        if not data:
            message = self.process.stderr.read(1024).decode(errors='replace').strip()
            raise ConnectionError(message or 'UV-PRO Bluetooth connection closed')
        self.buffer.extend(data)

    def ready(self):
        until = time.monotonic()+25
        while b'\n' not in self.buffer:
            self.receive(until)
        line, _, rest = self.buffer.partition(b'\n')
        self.buffer = bytearray(rest)
        if not line.startswith(b'READY '):
            raise ConnectionError('Unexpected Bluetooth adapter response')
        return line[6:].decode('ascii')

    def request(self, command, payload):
        self.process.stdin.write(b'\xff\x01\x00'+bytes([len(payload)])+struct.pack('>HH',2,command)+payload)
        self.process.stdin.flush()
        until = time.monotonic()+5
        while time.monotonic()<until:
            while len(self.buffer)>=8:
                if self.buffer[:2]!=b'\xff\x01':
                    del self.buffer[0]
                    continue
                size = self.buffer[3]
                length = 8+size+(self.buffer[2]&1)
                if len(self.buffer)<length:break
                frame = bytes(self.buffer[:length])
                del self.buffer[:length]
                if struct.unpack('>HH',frame[4:8])!=(2,command|0x8000):continue
                if not size or frame[8]:raise ValueError('Radio rejected command %d' % command)
                return frame[9:8+size]
            self.receive(until)
        raise TimeoutError('UV-PRO reply timed out')


@contextlib.contextmanager
def connection():
    if not enabled():
        raise ValueError("Select This device in Connections to use Mac Bluetooth")
    directory = Path.home()/'.local/state/pocket/mac-uvpro'
    directory.mkdir(parents=True,mode=0o700,exist_ok=True)
    with (directory/'control.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('Another Pocket action is using the radio') from None
        for attempt in range(3):
            with subprocess.Popen([str(HELPER)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, bufsize=0) as process:
                try:
                    link = Link(process)
                    try:
                        address = link.ready()
                    except ConnectionError as error:
                        if attempt == 2 or 'serial service unavailable' not in str(error):
                            raise
                    else:
                        device = directory / hashlib.sha256(address.encode()).hexdigest()[:16]
                        device.mkdir(mode=0o700, exist_ok=True)
                        yield link, device, address
                        return
                finally:
                    process.stdin.close()
                    try:
                        process.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
            time.sleep(2)


def owner_module():
    if str(OWNER) not in sys.path:sys.path.insert(0,str(OWNER))
    spec=importlib.util.spec_from_file_location('mac_uvpro_transaction',OWNER/'n810-radio-bandwidth.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def upload(index, rows):
    transaction=owner_module()
    from uvpro_bank import upload as bank_upload
    with connection() as (link,device,address):
        job=bank_upload({'bank':index,'channels':rows},address,device/'backups',transaction.atomic)
        reply=None
        while True:
            try:command,payload,*_=job.send(reply)
            except StopIteration as done:return done.value
            reply=link.request(command,payload)


_status_lock = threading.Lock()
_status_lines = ('Ready for a Bluetooth status check',)
_status_worker = None


def status_lines():
    with _status_lock:
        return _status_lines


_last_observation = {}


def last_observation():
    with _status_lock:
        return _last_observation.copy()


def check():
    with connection() as (link, device, address):
        raw = link.request(20, b'')
        if len(raw) != 4:
            raise ValueError('Unexpected UV-PRO status length')
        bank = (int.from_bytes(raw, 'big') >> 6) & 63
        reply = link.request(73, bytes([bank]))
        if not reply or reply[0] != bank:
            raise ValueError('Unexpected UV-PRO bank reply')
        name = reply[1:].split(b'\0')[0].decode('gbk', errors='replace') or '(unnamed)'
        settings = link.request(10, b'')
        beacon = link.request(33, b'\x02')
        files = HERE / 'vendor/packet-console'
        layouts = json.loads((files / 'radio-read-layouts.json').read_text())
        spec = importlib.util.spec_from_file_location('radio_wire', files / 'n810-radio-backup.py')
        wire = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wire)
        if len(settings) * 8 != sum(width for _, width, _ in layouts['Settings']):
            raise ValueError('Unexpected UV-PRO settings length')
        from radio_state import adapter
        observed = time.time()
        status = wire.decode(raw, layouts['StatusExt'])
        telemetry = dict(status=status, settings=wire.decode(settings, layouts['Settings']))
        beacon_layout = {50: 'BSSSettings', 52: 'BSSSettingsV2'}.get(len(beacon))
        if beacon_layout:
            telemetry['beacon'] = wire.decode(beacon, layouts[beacon_layout])
        active = adapter.model.normalize_radio({}, telemetry, observed)['live']['active']
        backups = sorted((device / 'backups').glob('*/backup.json'))
        try:
            _, cached = load_catalog(device)
        except (OSError, KeyError, ValueError, TypeError):
            cached = None
        observation = dict(device=device, telemetry=telemetry, active=active, signal=status['rssi'], bank_name=name,
                           backup=backups[-1].parent.name if backups else None, observed=observed)
    stamp = time.strftime('%H:%M:%S %Z')
    message = f'UV-PRO replied at {stamp} · bank {bank} {name}'
    global _status_lines, _last_reply, _last_observation, _downloaded
    with _status_lock:
        _downloaded = cached
        _last_observation = observation
        _last_reply = time.monotonic()
        _status_lines = (message, 'Transport: Mac Bluetooth Classic · opens on demand')
    return message


def refresh_status(wake):
    global _status_worker, _status_lines
    def run():
        global _status_lines
        try:
            check()
        except (OSError, ValueError, RuntimeError) as error:
            with _status_lock:
                _status_lines = ('Bluetooth check failed: ' + str(error),)
        finally:
            if wake:
                wake()
    with _status_lock:
        if _status_worker and _status_worker.is_alive():
            return
        _status_lines = ('Reading the UV-PRO over Mac Bluetooth…',)
        _status_worker = threading.Thread(target=run, daemon=True)
        _status_worker.start()


def tune(repeater):
    module=owner_module()
    with connection() as (link,device,address):
        def active_bank():
            status=link.request(20,b'')
            if len(status)!=4 or not module.bits(status,0,1) or module.bits(status,1,1):
                raise ValueError('Radio must be powered on and idle')
            return module.bits(status,20,6)
        bank=active_bank()
        device=device/('bank-%d'%bank)
        device.mkdir(mode=0o700,exist_ok=True)
        commands=[]
        transaction=module.Transaction(lambda cmd,payload,original:commands.append((cmd,payload,original)),
                                       device/'request.json',device/'result.json')
        request=dict(id=uuid.uuid4().hex,action='tune_repeater',created_at=time.time(),repeater=repeater)
        module.atomic(transaction.request_path,request)
        transaction.tick()
        while transaction.active:
            if commands:
                cmd,payload,original=commands.pop(0)
                if cmd in (11,14):
                    if active_bank()!=bank:raise ValueError('Active bank changed before tuning')
                    before=link.request(10,b'') if cmd==11 else link.request(13,payload[:1])
                    if before!=original:raise ValueError('Radio changed before tuning write')
                raw=link.request(cmd,payload)
                transaction.consume(cmd|0x8000,b'\0'+raw)
            else:
                time.sleep(.025)
                transaction.tick()
        if not transaction.result.get('completed'):
            raise ValueError(transaction.result.get('error','Tune not verified'))
        return transaction.result

_last_reply = None


def radio_panel():
    with _status_lock:
        message = _status_lines[0]
        recent = _last_reply is not None and time.monotonic() - _last_reply < 60
    if message.startswith('Bluetooth check failed'):
        return 'UV-PRO error', 'bad'
    if recent:
        return 'UV-PRO seen', 'good'
    return ('UV-PRO last seen', 'warning') if _last_reply is not None else ('UV-PRO ?', 'unknown')

def download_bank(index=None):
    transaction = owner_module()
    from uvpro_bank import download
    with connection() as (link, device, address):
        root = device / 'backups'
        job = download(index, address, root, transaction.atomic)
        response = None
        while True:
            try:
                command, payload = job.send(response)
            except StopIteration as done:
                result = done.value
                break
            response = link.request(command, payload)
        path = max(root.glob('*/backup.json'))
        capture = json.loads(path.read_bytes())
        transaction.atomic(device / 'catalog.json', {'capture': path.parent.name})
        with _status_lock:
            global _downloaded
            _downloaded = capture
        return result


_downloaded = None


def downloaded():
    with _status_lock:
        return _downloaded

def edit_setting(edit):
    owner_module()
    from uvpro_settings import transaction
    read, selector = (10, b'') if edit['group'] == 'settings' else (33, b'\x02')
    with connection() as (link, device, address):
        job = transaction(edit)
        reply = None
        while True:
            try:
                command, payload, original = job.send(reply)
            except StopIteration as done:
                return done.value
            if original is not None and link.request(read, selector) != original:
                raise ValueError('Radio settings changed before write')
            reply = link.request(command, payload)


def download_all(progress):
    """Read each region on one link, then restore and verify the original selection."""
    from datetime import datetime, timezone
    owner = owner_module()
    from uvpro_bank import read_bank

    with connection() as (link, device, address):
        def active():
            raw = link.request(20, b'')
            if len(raw) != 4 or not raw[0] & 128 or raw[0] & 64:
                raise ValueError('UV-PRO must be powered on and idle')
            return (int.from_bytes(raw, 'big') >> 6) & 63

        def select(index):
            link.request(60, bytes([index]))
            time.sleep(.2)
            if active() != index:
                raise ValueError('Bank selection readback mismatch')

        recovery = device / 'restore-pending.json'

        def restore(index, saved_settings, saved_beacon):
            select(index)
            if link.request(10, b'') != saved_settings:
                link.request(11, saved_settings)
            if link.request(33, b'\x02') != saved_beacon:
                link.request(34, saved_beacon)
            if (active() != index or link.request(10, b'') != saved_settings
                    or link.request(33, b'\x02') != saved_beacon):
                raise ValueError('Original radio configuration restoration pending; reconnect to retry')

        if recovery.exists():
            progress('Recovering the radio configuration saved before an interrupted download…')
            saved = json.loads(recovery.read_bytes())
            restore(saved['bank'], bytes.fromhex(saved['settings']), bytes.fromhex(saved['beacon']))
            recovery.unlink()

        original = active()
        settings = link.request(10, b'')
        beacon = link.request(33, b'\x02')
        if len(settings) != 22 or len(beacon) not in (50, 52):
            raise ValueError('Unsupported radio settings layout')
        paused = beacon[:1] + bytes([beacon[1] & ~0x10]) + beacon[2:]
        banks = []
        directory = None
        switched = pause_attempted = False
        stamp = datetime.now(timezone.utc)
        root = device / 'backups'
        # Keep the original configuration on disk until restoration is verified.
        owner.atomic(recovery, {'bank': original, 'settings': settings.hex(), 'beacon': beacon.hex()})
        try:
            # Inhibit automatic location reports while other regions are selected.
            if beacon != paused:
                pause_attempted = True
                link.request(34, paused)
                if link.request(33, b'\x02') != paused:
                    raise ValueError('Beacon pause readback mismatch')
            queue = [original]
            for index in queue:
                if not enabled():
                    raise ValueError('Device selection changed during download')
                if index != original:
                    switched = True
                    select(index)
                progress('Reading bank %d · restoring bank %d when finished' % (index, original))
                job = read_bank(index, address)
                reply = None
                while True:
                    try:
                        cmd, payload = job.send(reply)
                    except StopIteration as done:
                        part = done.value
                        break
                    reply = link.request(cmd, payload)
                if directory is None:
                    directory = part['bank_names']
                    queue.extend(i for i in range(len(directory)) if i != original)
                if part['bank_names'] != directory:
                    raise ValueError('Bank directory changed during download')
                banks.extend(part['banks'])
        finally:
            if switched:
                progress('Restoring original bank %d and settings…' % original)
                select(original)
                if link.request(10, b'') != settings:
                    link.request(11, settings)
            if active() != original or link.request(10, b'') != settings:
                raise ValueError('Original bank or settings restoration pending; reconnect to retry')
            if pause_attempted:
                current = link.request(33, b'\x02')
                if current == paused:
                    link.request(34, beacon)
                if link.request(33, b'\x02') != beacon:
                    raise ValueError('Original beacon settings restoration pending; reconnect to retry')
            recovery.unlink()
        capture = dict(part, banks=sorted(banks, key=lambda b: b['index']),
                       status=dict(curr_region=original), restored=True, restore_bank=original,
                       started=stamp.isoformat(), finished=datetime.now(timezone.utc).isoformat())
        folder = root / stamp.strftime('%Y%m%dT%H%M%S.%fZ')
        folder.mkdir(mode=0o700, parents=True)
        owner.atomic(folder / 'backup.json', capture)
        owner.atomic(device / 'catalog.json', {'capture': folder.name})
        with _status_lock:
            global _downloaded
            _downloaded = capture
        return f'Saved {len(banks)} banks · restored bank {original}'

def load_catalog(device):
    metadata = json.loads((device / 'catalog.json').read_bytes())
    capture = json.loads((device / 'backups' / Path(metadata['capture']).name / 'backup.json').read_bytes())
    for key, name in metadata.get('verified_names', {}).items():
        index = int(key)
        capture['bank_names'][index] = name
        for bank in capture['banks']:
            if bank['index'] == index:
                bank['name'] = name
    return metadata, capture


def rename_bank(index, expected, name):
    if not name.strip() or not name.isascii() or not name.isprintable() or len(name) > 10:
        raise ValueError('Use 1–10 printable ASCII characters')
    with connection() as (link, device, address):
        metadata, capture = load_catalog(device)
        if not 0 <= index < len(capture['bank_names']):
            raise ValueError('Download the bank directory first')
        selector = bytes([index])
        def read_name():
            reply = link.request(73, selector)
            if reply[:1] != selector:
                raise ValueError('Bank name reply has the wrong index')
            return reply[1:].split(b'\0', 1)[0].decode('gbk', errors='replace')
        before = read_name()
        if before != name:
            if before != expected:
                raise ValueError('Bank name changed on the UV-PRO. Refresh before renaming.')
            link.request(59, selector + name.encode('ascii'))
        if read_name() != name:
            raise ValueError('Bank name readback mismatch')
        metadata.setdefault('verified_names', {})[str(index)] = name
        owner_module().atomic(device / 'catalog.json', metadata)
        _, capture = load_catalog(device)
        with _status_lock:
            global _downloaded
            _downloaded = capture
        return f'Bank {index}: {name} · verified on UV-PRO'
