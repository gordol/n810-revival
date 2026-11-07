"""Compose local radio facts with existing receive-only feed sockets."""
import json
import importlib.util
import sys
import time
from pathlib import Path


def read(path):
    try:
        path=Path(path)
        if path.stat().st_size>2*1024*1024:raise ValueError('snapshot too large')
        value=json.loads(path.read_text())
        return value if isinstance(value,dict) else None
    except (OSError,ValueError):return None


class DeviceSource:
    remote=False
    local_device=True
    # Live receive publishes changes. Retained files refresh initially or explicitly.
    event_driven=True
    def __init__(self,home=None,telemetry='/dev/shm/n810-radio-live.json',collector=None,feed='/dev/shm/n810-aprs.sock',snapshots='/dev/shm/n810-aprs-replay.sock',directory=None,sources=None,shared_telemetry=None):
        self.root=Path(home or Path.home())/'.local/state/n810-radio'
        self.aprs=self.root.parent/'n810-aprs'
        self.telemetry=Path(telemetry);self.catalog={};self.radio_live=None;self.messages={};self.nets_state=None
        self._files_dirty=True;self._collect_requested=True;self._wakeup=None;self.closed=False;self.publication_revision=0
        self.sample_due=None;self.system={};self.pending=None;self.worker=None;self.files_pending=None
        self.rx=[];self.raw_records=[];self.rx_available=False;self.rx_error='Saved RX snapshot unavailable'
        self.rx_signature=object();self.rx_pending=None;self._raw_refresh_pending=True;self.file_cache={};self.walk_pending=None;self.walk_rows=[]
        self.catalogue=dict(services=[])
        self.shared_telemetry=shared_telemetry
        self.collector=collector
        if self.collector is None:
            root=Path(__file__).resolve().parent
            path=root/'vendor/packet-console/web-console/read-state.py'
            spec=importlib.util.spec_from_file_location('device_local_status',path)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            self.collector=module.host_status
        from console_source import Source
        root=Path(__file__).resolve().parent
        sources=Path(sources) if sources else root/'vendor/packet-console'
        self.receive=Source(feed,snapshots,directory=directory or self.aprs/'directory.sqlite3',sources=sources)
        self.receive.bind_wakeup(self._receive_changed)

    def bind_wakeup(self,callback):
        if callback is not None and not callable(callback):raise TypeError('wakeup must be callable')
        self._wakeup=callback
    def _notify(self,*_):
        if self.closed:return
        self.publication_revision+=1
        callback=self._wakeup
        if callback is not None:callback()
    def _receive_changed(self):
        # A packet is not a revision of retained catalogs or owner telemetry.
        if getattr(self.receive,'state',{}).get('captured') is not None:self._raw_refresh_pending=False
        self._notify()
    def refresh(self):
        """Explicitly re-read retained facts and request one local observation."""
        if self.closed:return
        self._files_dirty=True;self._raw_refresh_pending=True;self._collect_requested=True
        self.receive.refresh()
    def _submit(self,fn,*args):
        future=self.pool().submit(fn,*args)
        future.add_done_callback(self._notify)
        return future
    def _collect(self):
        if self.shared_telemetry is not None:
            try:
                observation=self.shared_telemetry()
                if not isinstance(observation,dict):raise ValueError('Invalid local observation')
                system=observation.get('system') or {}
                if not isinstance(system,dict):raise ValueError('Invalid system observation')
                stamp=system.get('observed_at')
                import math
                if (system.get('source') and type(stamp) in (int,float)
                        and math.isfinite(stamp) and -1<=time.time()-stamp<=15):
                    return observation
            except (OSError,ValueError,EOFError):pass
        # Missing, starting, stale or failed directory: retain local operation.
        return self.collector()

    def read(self,now):
        if self.rx_pending is not None and self.rx_pending.done():
            try:self.raw_records,self.rx=self.rx_pending.result();self.rx_available=True;self.rx_error=None
            except (OSError,ValueError,KeyError,TypeError) as error:self.rx_available=False;self.rx_error='Saved RX snapshot unavailable: '+str(error)
            self.rx_pending=None
        if self.walk_pending is not None and self.walk_pending.done():
            try:self.walk_rows=self.walk_pending.result()
            except (OSError,ValueError,KeyError,TypeError):pass
            self.walk_pending=None
        if self.pending is not None and self.pending.done():
            try:self.system=self.pending.result()
            except (OSError,ValueError):pass
            self.pending=None
        if not self.closed and self.collector and self.pending is None and (self._collect_requested or self.sample_due is None or now>=self.sample_due):
            self._collect_requested=False;self.sample_due=now+5;self.pending=self._submit(self._collect)
        # Try live receive first; decoding the saved copy concurrently repeats
        # the same history work. A failed receive attempt wakes this fallback.
        # A refresh during a load waits for its existing Future.
        if not self.closed and self._raw_refresh_pending and self.rx_pending is None and not getattr(self.receive,'starting',False) and getattr(self.receive,'state',{}).get('error'):
            raw=self.aprs/'raw-frames.json';signature=self.revision(raw)
            if signature!=self.rx_signature:
                self.rx_signature=signature
                if signature is not None:
                    from device_retained import packet_bundle
                    self.rx_pending=self._submit(packet_bundle,raw)
                else:self.rx_available=False;self.rx_error='Saved RX snapshot unavailable'
            self._raw_refresh_pending=False
        if self.files_pending is not None and self.files_pending.done():
            try:
                self.catalog,self.messages,self.nets_state,self.radio_live=self.files_pending.result()
            except (OSError,ValueError):pass
            self.files_pending=None
        if not self.closed and self._files_dirty and self.files_pending is None:
            self._files_dirty=False
            self.files_pending=self._submit(self._load_files)
        # Cached read never changes observation timestamps or starts an idle scan.
        catalog=dict(self.catalog,outbox=self.messages.get('outbox',[]),nets_state=self.nets_state,walks=self.walk_rows)
        live=dict(self.system,radio_live=self.radio_live,packets=self.rx,raw_records=self.raw_records,
                  history_source='Saved shutdown RX snapshot; not live',retained_rx_available=self.rx_available,retained_error=self.rx_error)
        received=self.receive.read(now)['live']
        rx=received['data']
        # A valid socket snapshot replaces saved history; never append/re-date it.
        if rx['captured'] is not None:live.update(rx)
        else:
            live.update({key:value for key,value in rx.items() if key not in
                         ('packets','raw_records','history_source','retained_rx_available')})
        # RX state must not replace the local radio/system observation.
        envelope=dict(data=live)
        if received.get('error'):envelope['error']=received['error']
        ready=bool(self.system.get('system',{}).get('source'))
        self.catalogue=dict(services=[dict(id='system',available=ready,state='ready' if ready else 'starting' if self.pending is not None else 'unavailable'),
            dict(id='receive',available=bool(getattr(self.receive,'state',{}).get('online')),state='ready' if getattr(self.receive,'state',{}).get('online') else 'unavailable')])
        return dict(catalog=catalog,live=envelope,connector=dict(local=True,device=dict(connected=not self.closed)))
    def history_page(self,before=None,anchor=None):
        from device_retained import owner
        import os
        return owner('n810-frame-history.py').page(before,path=os.environ.get('POCKET_RX_ARCHIVE',str(self.aprs/'packets.sqlite3')),anchor=anchor)

    def _load_files(self):
        """Prepare retained files on the existing worker; read publishes the tuple."""
        from radio_catalog import load
        catalog=load(self.root,self.cached)
        return catalog,self.saved('messages.json') or {},self.saved('nets-state.json'),self.cached(self.telemetry)

    def pool(self):
        if self.worker is None:
            from concurrent.futures import ThreadPoolExecutor
            self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix='local-status')
        return self.worker
    @staticmethod
    def revision(path):
        try:
            stat=path.stat()
            return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        except OSError:return None
    def cached(self,path):return read_cached(path,self.file_cache)
    def delay(self,now=None):
        if self.closed or self.collector is None or self.pending is not None:return None
        now=time.time() if now is None else now
        return 0. if self._collect_requested or self.sample_due is None else max(0.,self.sample_due-now)
    def saved(self,name):return self.cached(self.aprs/name)
    def request_walks(self,now):
        if not self.closed and self.walk_pending is None:
            from device_retained import walks
            self.walk_pending=self._submit(walks,self.aprs/'walks')
    def close(self):
        self.closed=True;self._wakeup=None;self.receive.bind_wakeup(None)
        stopped=self.receive.close()
        if self.worker is not None:self.worker.shutdown(wait=False,cancel_futures=True)
        return stopped


def read_cached(path,cache):
    path=Path(path);signature=DeviceSource.revision(path)
    prior=cache.get(path)
    if prior is not None and prior[0]==signature:return prior[1]
    value=read(path) if signature is not None else None
    # A replacement during the read must be retried next time; never label
    # bytes with a revision they did not come from.
    if DeviceSource.revision(path)==signature:cache[path]=(signature,value)
    else:cache.pop(path,None)
    return value
