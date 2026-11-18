"""Explicit tuning through the shared owner socket; never opens Bluetooth."""
import json
import socket
import threading
import time
import uuid
from pathlib import Path


class Tune:
    def __init__(self,path,wakeup=None):
        self.path=path;self.wakeup=wakeup;self.status='';self.worker=None
    def publish(self,text):
        self.status=text
        if self.wakeup:self.wakeup()
    def start(self,repeater):
        if self.worker and self.worker.is_alive():return
        self.publish('Tuning request submitted…')
        self.worker=threading.Thread(target=self.run,args=(dict(repeater),),daemon=True);self.worker.start()
    def rpc(self,value):
        if not self.path:raise ValueError('No radio owner control socket configured')
        if Path(self.path).name=='radio-control.sock' and not Path(self.path).exists():
            from receive_bridge import forward_radio_control
            self.path=forward_radio_control(Path(self.path).parent)
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(3)
            try:client.connect(str(self.path))
            except (FileNotFoundError,ConnectionRefusedError):
                raise ValueError('Receiver offline. Open Bluetooth and connect the UV-PRO.') from None
            client.sendall(json.dumps(value).encode()+b'\n')
            raw=bytearray()
            while b'\n' not in raw:
                block=client.recv(4096)
                if not block:raise ValueError('Radio owner disconnected')
                raw.extend(block)
                if len(raw)>32768:raise ValueError('Invalid owner response')
        response=json.loads(raw.split(b'\n')[0])
        if not response.get('ok'):raise ValueError(response.get('error','Radio rejected tuning'))
        return response['result']
    def run(self,repeater):
        ident=uuid.uuid4().hex
        try:
            self.rpc(dict(version=1,operation='tune_repeater',request_id=ident,repeater=repeater))
            until=time.monotonic()+90
            while time.monotonic()<until:
                result=self.rpc(dict(version=1,operation='tune_status',request_id=ident))
                if result.get('state')=='failed':raise ValueError(result.get('error','Tuning failed'))
                if result.get('completed'):
                    self.publish('Previous B selection and memory restored · readback verified' if result.get('state')=='secondary_restored' else 'B channel tuned · readback verified · APRS A/digital settings preserved' if result.get('aprs_configuration_preserved') and result.get('readback_verified') else 'Radio command accepted · readback unverified');return
                time.sleep(.25)
            raise ValueError('Tuning outcome unknown; no automatic retry')
        except (OSError,ValueError,RuntimeError) as error:self.publish('Tune: '+str(error))


class BankDownload(Tune):
    def start_all(self):
        if self.worker and self.worker.is_alive():return
        if str(self.path)!='/dev/shm/n810-radio-read/control.sock':
            self.publish('Download all banks on the paired tablet');return
        self.publish('Downloading all banks… Reception resumes when finished.')
        self.worker=threading.Thread(target=self._all_banks,daemon=True);self.worker.start()

    def _all_banks(self):
        import subprocess,sys
        try:
            result=subprocess.run([sys.executable,__file__, '--all-banks'],
                                  capture_output=True,text=True,start_new_session=True)
            self.publish((result.stderr if result.returncode else result.stdout).strip())
        except OSError as error:self.publish(str(error))

    def start(self, index=None, edit=None):
        if self.worker and self.worker.is_alive():return
        self.publish('Updating radio setting…' if edit else 'Reading radio banks…')
        self.worker=threading.Thread(target=self.download,args=(index,edit),daemon=True)
        self.worker.start()

    def download(self,index,edit):
        identity=uuid.uuid4().hex
        try:
            request=dict(operation='edit_setting',edit=edit) if edit else dict(operation='download_bank',bank=index)
            result=self.rpc(dict(version=1,request_id=identity,**request))
            until=time.monotonic()+600
            while not result.get('completed'):
                if result.get('state')=='failed':raise ValueError(result.get('error','Read failed'))
                if time.monotonic()>=until:raise ValueError('Download outcome unknown')
                time.sleep(1)
                result=self.rpc(dict(version=1,operation='setting_status' if edit else 'bank_status',request_id=identity))
            if edit:
                self.publish('Verified '+edit['field'].replace('_',' ')+' on the radio. Refresh for current values.')
                return
            self.publish('Saved bank %d · %d channels · %d bank names' %
                         (result['bank'],result['channels'],len(result['banks'])))
        except (KeyError,OSError,ValueError,RuntimeError) as error:self.publish(str(error))


def receive_action(action, ready):
    import os
    from feed_control_client import FeedControl
    ident = os.urandom(16).hex()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(45)
        client.connect('/dev/shm/n810-aprs.sock')
        client.sendall(FeedControl.frame('subscribe', ident))
        if action != 'subscribe':
            ident = os.urandom(16).hex()
            client.sendall(FeedControl.frame(action, ident))
        deadline = time.monotonic() + 45
        acknowledged = False
        with client.makefile('rb') as stream:
            while time.monotonic() < deadline:
                line = stream.readline(65536)
                if not line:
                    raise ConnectionError('Radio receive service disconnected')
                if not line.startswith(b'@FEED '):
                    continue
                state = json.loads(line[6:])
                if state.get('type') == 'reply' and state.get('request_id') == ident:
                    if not state.get('ok'):
                        raise ValueError(state.get('error', 'Receive service rejected action'))
                    acknowledged = True
                if acknowledged and state.get('type') == 'state' and ready(state):
                    return state
    raise TimeoutError('Timed out waiting for the radio receive service')


def download_all_banks():
    import datetime,fcntl,subprocess,sys
    from peripheral_setup import receive_profile
    address = receive_profile()['address']
    root = Path.home() / '.local/state/n810-radio'
    backups = root / 'backups'
    backups.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (root / 'download-all.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another all-bank download is running') from None
        state = receive_action('subscribe', lambda s: True)
        if not state['reception']['enabled'] or not state['radio']['connected']:
            raise ValueError('Connect the UV-PRO in Bluetooth first')
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        folder = backups / stamp
        try:
            receive_action('receive_stop', lambda s: not s['reception']['enabled'] and not s['reception']['stopping'])
            tool = '/usr/local/lib/n810-radio/n810-radio-backup.py'
            result = subprocess.run([sys.executable, tool, '--address', address,
                                     '--output', str(folder), '--all-banks'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            if result.returncode:
                raise ValueError(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'Bank backup failed')
            saved = json.loads((folder / 'backup.json').read_bytes())
            banks = saved['banks']
            if not saved['complete'] or (len(banks)>1 and not saved.get('restored')):
                raise ValueError('Bank or settings restoration unverified')
        finally:
            receive_action('receive_start', lambda s: s['reception']['enabled'] and s['radio']['connected'])
        return f"Saved {len(banks)} banks · receiving on bank {saved['status']['curr_region']}"


if __name__ == '__main__':
    import sys
    if sys.argv[1:] != ['--all-banks']:sys.exit('Expected --all-banks')
    try:
        print(download_all_banks())
    except (ValueError, OSError, RuntimeError) as error:
        sys.exit(str(error))
