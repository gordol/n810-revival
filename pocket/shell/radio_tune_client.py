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
            client.settimeout(3);client.connect(str(self.path));client.sendall(json.dumps(value).encode()+b'\n')
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
