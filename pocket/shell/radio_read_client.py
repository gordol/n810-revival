"""Bounded explicit intents to the existing radio owner; no radio transport."""
import json
import math
import os
from pathlib import Path
import _socket as socket
from contextlib import closing
import stat
import threading
import time

TERMINAL={'complete','failed','cancelled'}


def read_endpoint(device_radio,explicit=None,remote=False):
    """Device-local default only; selecting an endpoint never connects to it."""
    if explicit is not None:return Path(explicit)
    return Path('/dev/shm/n810-radio-read/control.sock') if device_radio and not remote else None


class Rejected(RuntimeError):pass


def progress(value,request_id):
    if not isinstance(value,dict) or type(value.get('version')) is not int or value['version']!=1 or value.get('request_id')!=request_id or value.get('operation')!='read_current':raise ValueError('Invalid radio read identity/version')
    if not isinstance(value.get('state'),str) or value['state'] not in TERMINAL|{'pending','reading'}:raise ValueError('Invalid radio read state')
    completed=value.get('completed');results=value.get('results')
    if type(completed) is not int or not 0<=completed<=3 or type(value.get('total')) is not int or value['total']!=3 or not isinstance(results,dict) or len(results)!=completed or not set(results)<={'20','10','33'}:raise ValueError('Invalid radio read progress')
    if value.get('pending_command') is not None and (type(value['pending_command']) is not int or value['pending_command'] not in (20,10,33)):raise ValueError('Invalid pending radio read command')
    if type(value.get('started_at')) not in (int,float) or not math.isfinite(value['started_at']):raise ValueError('Invalid owner start time')
    for result in results.values():
        if not isinstance(result,dict) or not isinstance(result.get('decoded'),dict) or type(result.get('observed_at')) not in (int,float) or not math.isfinite(result['observed_at']):raise ValueError('Invalid owner observation')
    if value['state']=='complete' and completed!=3:raise ValueError('Incomplete radio read marked complete')
    if value.get('error') is not None and not isinstance(value['error'],str):raise ValueError('Invalid radio read error')
    return value


class RadioRead:
    """One lazy worker for one explicit job; no automatic submit or retry."""
    def __init__(self,path):
        self.path=Path(path);self.publication=dict(state='idle',request_id=None,progress=None,error=None,uncertain=False,radio_live=None)
        self.worker=None;self.socket=None;self.closed=False;self.stop=threading.Event();self.cancelled=threading.Event()
        self.request=None;self._wakeup=None
        self.endpoint_error=self.endpoint_problem()
    def endpoint_problem(self):
        try:
            info=self.path.parent.lstat();node=self.path.lstat()
            if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700 or not stat.S_ISSOCK(node.st_mode) or node.st_uid!=os.getuid():return 'Radio read socket must be in a private same-user directory'
        except FileNotFoundError as error:
            if self.path.name=='radio-control.sock':
                try:
                    info=self.path.parent.lstat()
                    if stat.S_ISDIR(info.st_mode) and info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700 and (self.path.parent/'owner.json').is_file():return None
                except OSError:pass
            return str(error)
        except OSError as error:return str(error)
        return None
    @property
    def active(self):return self.worker is not None and self.worker.is_alive()
    def bind_wakeup(self,callback):
        if callback is not None and not callable(callback):raise TypeError('wakeup must be callable')
        self._wakeup=callback
    def _publish(self,**values):
        if not self.closed:
            self.publication=dict(self.publication,**values)
            callback=self._wakeup
            if callback is not None:callback()
    def _launch(self,operation):
        if self.closed or self.active:return False
        self.cancelled.clear();self._publish(state='submitting' if operation=='read_current' else 'checking' if operation=='status' else 'cancelling',error=None)
        self.worker=threading.Thread(target=self._run,args=(operation,),name='radio-read',daemon=True);self.worker.start();return True
    def start(self):
        if self.closed or self.active:return False
        if self.publication['uncertain']:return False
        import uuid
        now=time.time();self.request=dict(version=1,operation='read_current',request_id=uuid.uuid4().hex,requested_at=now,expires_at=now+25)
        self.publication=dict(state='idle',request_id=self.request['request_id'],progress=None,error=None,uncertain=False,radio_live=None)
        return self._launch('read_current')
    def check(self):return bool(self.request) and self._launch('status')
    def cancel(self):
        if not self.request or self.closed:return False
        if self.active:self.cancelled.set();return True
        return self._launch('cancel')
    def _rpc(self,operation,job_deadline=None):
        if self.path.name=='radio-control.sock' and not self.path.exists():
            from receive_bridge import forward_radio_control
            self.path=forward_radio_control(self.path.parent)
        self.endpoint_error=self.endpoint_problem()
        if self.endpoint_error:raise ValueError(self.endpoint_error)
        value=self.request if operation=='read_current' else dict(version=1,operation=operation,request_id=self.request['request_id'])
        raw=json.dumps(value,separators=(',',':'),allow_nan=False).encode()+b'\n'
        if len(raw)>4096:raise ValueError('Radio read request exceeds limit')
        deadline=time.monotonic()+3
        if job_deadline is not None:deadline=min(deadline,job_deadline)
        with closing(socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)) as client:
            self.socket=client
            try:
                def remaining():
                    if self.stop.is_set():raise ConnectionAbortedError('Radio read client closed')
                    left=deadline-time.monotonic()
                    if left<=0:raise TimeoutError('Radio read response deadline exceeded')
                    client.settimeout(left)
                remaining();client.connect(str(self.path));remaining();client.sendall(raw);response=bytearray()
                while b'\n' not in response:
                    remaining();block=client.recv(min(4096,32769-len(response)))
                    if not block:raise ValueError('Truncated radio read response')
                    response.extend(block)
                    if len(response)>32768:raise ValueError('Radio read response exceeds limit')
                line,tail=response.split(b'\n',1)
                if tail.strip():raise ValueError('Multiple radio read responses')
                def constant(_):raise ValueError('Non-finite radio read response')
                envelope=json.loads(line,parse_constant=constant)
                if not isinstance(envelope,dict) or type(envelope.get('version')) is not int or envelope['version']!=1 or type(envelope.get('ok')) is not bool:raise ValueError('Invalid radio read response envelope')
                if not envelope['ok']:
                    if not isinstance(envelope.get('error'),str):raise ValueError('Invalid radio read rejection')
                    raise Rejected(envelope['error'][:512])
                result=progress(envelope.get('result'),self.request['request_id'])
                telemetry=envelope.get('radio_live')
                if telemetry is not None:
                    if not isinstance(telemetry,dict) or (telemetry.get('heartbeat') is not None and (type(telemetry['heartbeat']) not in (int,float) or not math.isfinite(telemetry['heartbeat']))) or type(telemetry.get('connected')) is not bool or type(telemetry.get('enabled')) is not bool or not isinstance(telemetry.get('fields'),dict):raise ValueError('Invalid owner telemetry snapshot')
                    for name in ('status','settings','beacon'):
                        stamp=telemetry['fields'].get(name)
                        if stamp is not None and (type(stamp) not in (int,float) or not math.isfinite(stamp)):raise ValueError('Invalid owner telemetry timestamp')
                        if name in telemetry and not isinstance(telemetry[name],dict):raise ValueError('Invalid owner telemetry section')
                return result,telemetry
            finally:self.socket=None
    def _run(self,operation):
        deadline=time.monotonic()+30
        try:
            while not self.stop.is_set():
                if time.monotonic()>=deadline:raise TimeoutError('Radio read progress deadline exceeded; outcome unknown')
                result,telemetry=self._rpc(operation,deadline)
                values=dict(state=result['state'],progress=result,error=result['error'][:512] if result.get('error') else None,uncertain=False)
                if telemetry is not None:values['radio_live']=telemetry
                self._publish(**values)
                if result['state'] in TERMINAL or operation=='cancel':return
                if time.monotonic()>=deadline:raise TimeoutError('Radio read progress deadline exceeded; outcome unknown')
                self.cancelled.wait(min(1,max(0,deadline-time.monotonic())))
                operation='cancel' if self.cancelled.is_set() else 'status'
        except Rejected as error:
            # A reply/serialization failure can occur after owner admission.
            missing=operation in ('status','cancel') and str(error)=='Unknown request ID'
            self._publish(state='unknown' if missing else 'uncertain',error='Owner has no record; prior outcome unconfirmed.' if missing else str(error)[:512],uncertain=not missing)
        except Exception as error:
            if not self.stop.is_set():self._publish(state='uncertain',error=(type(error).__name__+': '+str(error))[:512],uncertain=True)
    def close(self):
        self.closed=True;self._wakeup=None;self.stop.set();self.cancelled.set()
        client=self.socket
        if client is not None:
            try:client.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        if self.worker and threading.current_thread() is not self.worker:self.worker.join(timeout=1)
        # Closing the UI transport is not an implicit owner cancellation.
        return not self.active
