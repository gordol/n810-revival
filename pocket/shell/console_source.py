"""One receive-only console source over existing Unix/SSH-forwarded sockets."""
import json
from collections import namedtuple
from pathlib import Path
import re
import select
import socket
import threading
import time
from device_retained import owner,decode_records
from device_radio_source import read as read_file


def _read_snapshot(path,client,stopped=None):
    history=owner('n810-frame-history.py').History()
    if stopped is not None and stopped.is_set():raise ConnectionAbortedError('Receive source closed')
    client.settimeout(8);client.connect(str(path))
    deadline=time.monotonic()+12
    with client.makefile('rb') as stream:
        line=stream.readline(4097)
        if len(line)>4096 or not line.endswith(b'\n'):raise ValueError('Invalid receive snapshot header framing')
        header=json.loads(line)
        if not isinstance(header,dict):raise ValueError('Invalid receive snapshot header')
        count=header.get('records')
        if header.get('type')!='snapshot' or type(header.get('version')) is not int or header['version']!=1 or type(count) is not int or not 0<=count<=10000:
            raise ValueError('Invalid receive snapshot header')
        total=len(line)
        for _ in range(count):
            if stopped is not None and stopped.is_set():raise ConnectionAbortedError('Receive source closed')
            remaining=deadline-time.monotonic()
            if remaining<=0:raise TimeoutError('Receive snapshot timed out')
            client.settimeout(min(8,remaining))
            line=stream.readline(150001);total+=len(line)
            if len(line)>150000 or total>64*1024*1024:raise ValueError('Receive snapshot exceeds bounds')
            if not line.endswith(b'\n'):raise ValueError('Incomplete receive snapshot record')
            history.add(json.loads(line))
    return list(history.records)


def snapshot(path):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        return _read_snapshot(path,client)


def data(value):
    value=value or {}
    result=value.get('data',value) if isinstance(value,dict) else {}
    return result if isinstance(result,dict) else {}


ActivityPublication=namedtuple('ActivityPublication','events revision attached')


class Source:
    remote=True
    event_driven=True
    def __init__(self,feed,snapshots,retained=None,directory=None,sources=None,bridge=None):
        self.history_limit=owner('n810-frame-history.py').limits()[0]
        self.feed=Path(feed);self.snapshots=Path(snapshots);self.retained=Path(retained) if retained else None
        self.directory=Path(directory) if directory else None;self.sources=Path(sources) if sources else None
        self.stopped=threading.Event();self._refresh_requested=threading.Event();self.client=None;self.snapshot_client=None;self.records=[];self.packets=[];self.starting=True
        self.state=dict(online=False,captured=None,error='Receive socket connecting',revision=0,packets=self.packets,raw_records=self.records)
        self.base={};self.signature=None;self._retained_dirty=True;self._wakeup=None;self.revision=0
        self.directory_module=None;self.activity=ActivityPublication((),0,False);self.activity_capable=False
        self.projection_error=None;self.gap_possible=False;self.activity_gap_possible=False
        self.last_directory_ingest=None
        self.bridge=Path(bridge) if bridge else None;self.metadata={};self.status_due=0;self.status_retry=15;self.status_pending=bool(bridge)
        from feed_control_client import FeedControl
        self.control=FeedControl()
        self.worker=threading.Thread(target=self._work,name='console-rx',daemon=True);self.worker.start()

    def bind_wakeup(self,callback):
        """Bind the owning consumer's existing selector wake; no new transport."""
        if callback is not None and not callable(callback):raise TypeError('wakeup must be callable')
        self._wakeup=callback
    def _notify(self):
        self.revision+=1
        callback=self._wakeup
        if callback is not None and not self.stopped.is_set():callback()
    def refresh(self):
        """Explicit refresh uses the existing worker wake, never an idle timer."""
        if self.stopped.is_set():return
        self._retained_dirty=True;self._refresh_requested.set()
        self.control._wake(self.control.readable)
    @property
    def feed_control(self):return self.control.snapshot
    @property
    def feed_control_online(self):return self.control.online
    @property
    def owner_context(self):
        return self.control.owner_context
    def request_feed_control(self,action):return self.control.request(action)

    def _publish(self,online,error=None,rows=None):
        if self.stopped.is_set():return
        state=self.state
        packets=self.packets
        if rows is not None:
            changed=rows!=self.records
            if changed:packets=decode_records(rows)
            if changed or self.projection_error:
                try:self._ingest(rows);self.projection_error=None
                # Optional projection bugs must not terminate the receive owner.
                except Exception as projection_error:
                    self.projection_error=('Station projection unavailable: '+type(projection_error).__name__+': '+str(projection_error))[:1000]
                    self.activity_gap_possible=True
            self.records=rows;self.packets=packets
            captured=time.time()
        else:captured=state['captured']
        if self.stopped.is_set():return
        if rows is None and online==state['online'] and error==state['error']:return
        self.state=dict(online=online,captured=captured,error=error,revision=state['revision']+1,packets=packets,raw_records=self.records)
        self.starting=False
        self._notify()

    def _snapshot(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            self.snapshot_client=client
            try:return _read_snapshot(self.snapshots,client,self.stopped)
            finally:self.snapshot_client=None

    def _ingest(self,rows):
        if not self.directory or not self.sources:return
        import importlib.util
        if self.directory_module is None:
            spec=importlib.util.spec_from_file_location('console_rx_directory',self.sources/'n810-aprs-directory.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);self.directory_module=module
        module=self.directory_module
        db=module.database(str(self.directory))
        added=[];code=getattr(module.ingest,'__code__',None)
        self.activity_capable=bool(code and 'activity' in code.co_varnames[:code.co_argcount+code.co_kwonlyargcount])
        try:
            if self.activity_capable:module.ingest(db,rows,module.load_monitor(),'N0CALL',activity=added)
            else:module.ingest(db,rows,module.load_monitor(),'N0CALL')
        finally:db.close()
        previous=self.activity
        self.activity=ActivityPublication((previous.events+tuple(added))[-self.history_limit:],previous.revision+bool(added),self.activity_capable)
        self.last_directory_ingest=time.time()

    def _work(self):
        retry=1
        while not self.stopped.is_set():
            try:
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                    self.client=client;client.settimeout(8);client.connect(str(self.feed));client.setblocking(False)
                    self.control.connected()
                    self._refresh_requested.clear() # Initial snapshot consumes prior explicit refresh.
                    self._publish(True,rows=self._snapshot());retry=1
                    pulled=time.monotonic();due=None;pending=b'';outgoing=b''
                    self.status_pending=bool(self.bridge)
                    while not self.stopped.is_set():
                        now=time.monotonic()
                        if not outgoing:outgoing=self.control.take()
                        if self.status_pending and now>=self.status_due:self._status(now)
                        now=time.monotonic() # Status RPCs may have blocked.
                        timeout=max(0,due-now) if due is not None else None
                        if self.status_pending:timeout=max(0,self.status_due-now) if timeout is None else min(timeout,max(0,self.status_due-now))
                        if self.control.deadline is not None:timeout=max(0,self.control.deadline-now) if timeout is None else min(timeout,max(0,self.control.deadline-now))
                        readable,writable,_=select.select([client,self.control.worker_readable],[client] if outgoing else [],[],timeout)
                        # This is the one armed request deadline, not an idle poll.
                        if self.control.deadline is not None and time.monotonic()>=self.control.deadline:self.control.expire()
                        if self.control.worker_readable in readable:
                            self.control.worker_ready()
                            if self._refresh_requested.is_set():
                                self._refresh_requested.clear();due=time.monotonic()
                                self.status_pending=bool(self.bridge)
                        if client in writable:
                            try:written=client.send(outgoing)
                            except BlockingIOError:written=None
                            if written==0:raise ConnectionError('Receive control stream disconnected')
                            if written:outgoing=outgoing[written:]
                        if client in readable:
                            chunk=client.recv(32768)
                            if not chunk:raise ConnectionError('Receive stream disconnected')
                            pending+=chunk
                            if len(pending)>262144:raise ValueError('Receive stream line exceeds bounds')
                            while b'\n' in pending:
                                line,pending=pending.split(b'\n',1)
                                if self.control.line(line):
                                    self.status_pending=bool(self.bridge)
                                    self._notify();continue
                                # Status lines also cover raw records without a
                                # decoded APRS line. Coalesce these to <=1/15s.
                                if not line:continue
                                packet=bool(re.match(rb'^\d\d:\d\d:\d\d ',line))
                                when=max(time.monotonic()+.2,pulled+(.5 if packet else 15))
                                due=when if due is None else min(due,when)
                        if due is not None and time.monotonic()>=due:
                            self._publish(True,rows=self._snapshot());pulled=time.monotonic();due=None
            except Exception as error:
                if not self.stopped.is_set():
                    if self.state['captured'] is not None:self.gap_possible=True
                    self._publish(False,('Receive socket offline: '+type(error).__name__+': '+str(error))[:1000])
            self.client=None
            self.control.disconnected()
            if self.stopped.wait(retry):break
            retry=min(30,retry*2)

    def _status(self,now):
        from receive_bridge import radio_status
        try:
            radio=radio_status(self.bridge)
            self.metadata=dict(radio_live=radio,connector=dict(ssh=dict(success=True,observed_at=time.time())))
            self.status_retry=15
        except Exception as error:
            self.metadata=dict(self.metadata,radio_transport_error=(type(error).__name__+': '+str(error))[:1000])
            self.status_retry=min(60,self.status_retry*2)
        self.status_pending=False
        self.status_due=now+self.status_retry
        self._notify()

    def read(self,now):
        if self.retained and self._retained_dirty:
            self._retained_dirty=False
            try:
                info=self.retained.stat();signature=(info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
            except OSError:signature=None
            if signature!=self.signature:
                self.base=read_file(self.retained) or {};self.signature=signature
        state=self.state
        live=dict(data(self.base.get('live')))
        live.update(packets=state.get('packets',[]),captured=state['captured'],
                    raw_records=state['raw_records'],
                    history_source='feed socket · retained initial history + receive updates',
                    receive_subscription=True,receive_connected=state['online'],
                    retained_error=state['error'],retained_rx_available=state['captured'] is not None,
                    receive_gap_possible=self.gap_possible,station_projection_error=self.projection_error)
        activity=self.activity
        live['directory_activity']=dict(events=activity.events,revision=activity.revision,attached=activity.attached,
                                        connected=bool(activity.attached and state['online'] and not self.projection_error),
                                        scope='client-directory',source='Existing client Directory ingest',
                                        error=self.projection_error,gap_possible=self.gap_possible or self.activity_gap_possible,
                                        unavailable_reason='Directory activity API unavailable' if self.directory_module and not self.activity_capable else 'Client Directory writer unavailable' if not activity.attached else None)
        if self.bridge:
            live['radio_live']=self.metadata.get('radio_live')
            live['radio_transport_error']=self.metadata.get('radio_transport_error')
        envelope=dict(data=live)
        if state['error']:envelope['error']=state['error']
        # RX freshness cannot establish Bluetooth, radio telemetry or system health.
        return dict(catalog=self.base.get('catalog',{}),live=envelope,connector=self.metadata.get('connector',{}) if self.bridge else self.base.get('connector',{}))

    def close(self):
        if self.stopped.is_set():return not self.worker.is_alive()
        self.stopped.set();self._wakeup=None
        for client in (self.client,self.snapshot_client):
            if client is not None:
                try:client.shutdown(socket.SHUT_RDWR)
                except OSError:pass
                client.close()
        if threading.current_thread() is not self.worker:self.worker.join(timeout=1)
        self.control.close()
        self.state=dict(self.state,online=False,error='Receive source closed',revision=self.state['revision']+1)
        return not self.worker.is_alive()
