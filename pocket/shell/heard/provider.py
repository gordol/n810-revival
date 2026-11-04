"""One managed read-only catalog reader; no device or radio transport."""
from collections import namedtuple
import json
from datetime import datetime
from pathlib import Path
import socket
import sqlite3
import threading
import time

Contact = namedtuple('Contact', 'call name buddy notes first last packets evidence via')
Snapshot = namedtuple('Snapshot', 'rows source fetched captured error')
MAX_ROWS = 128
MAX_BYTES = 2_000_000


def text(value, limit=512):
    value=str(value or '')[:limit]
    return value if value.isprintable() else ''.join(c if c.isprintable() else ' ' for c in value)


def observation_key(row):
    try:
        stamp=datetime.fromisoformat(row.last.replace('Z','+00:00'))
        if stamp.tzinfo is not None: return (1,stamp.timestamp(),row.call)
    except (ValueError,OverflowError): pass
    return (0,0,row.call)


def normalize(data, limit=MAX_ROWS):
    """Existing web catalog fields; capture/fetch metadata never becomes RX time."""
    if not isinstance(data, dict) or not isinstance(data.get('stations'), list):
        raise ValueError('expected catalog stations')
    evidence, via = {}, {}
    for row in data.get('evidence', [])[:2000]:
        call = text(row.get('call'), 32)
        entries = evidence.setdefault(call, [])
        if len(entries) < 12:
            entries.append(tuple(text(row.get(k)) for k in ('kind', 'stamp', 'detail')))
    for row in data.get('via', [])[:1000]:
        call = text(row.get('call'), 32)
        entries = via.setdefault(call, [])
        if len(entries) < 12:
            entries.append((text(row.get('relay'), 32), text(row.get('last')), max(0, int(row.get('packets') or 0))))
    rows = {}
    for row in data['stations'][:500]:
        call = text(row.get('call'), 32)
        if not call: continue
        rows[call] = Contact(call, text(row.get('name'), 80), bool(row.get('buddy')), text(row.get('notes')),
                             text(row.get('first')), text(row.get('last')), max(0, int(row.get('packets') or 0)),
                             tuple(sorted(evidence.get(call, ()))), tuple(sorted(via.get(call, ()))))
    return tuple(sorted(rows.values(), key=observation_key, reverse=True)[:limit])


class CatalogFile:
    """Frozen export of existing catalog JSON, explicitly offline."""
    def __init__(self, path): self.path = Path(path).expanduser()
    def read(self):
        with self.path.open('rb') as stream: raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES: raise ValueError('catalog exceeds 2 MB')
        data = json.loads(raw)
        transport_error = data.get('error')
        if 'data' in data: data = data['data']
        errors = [e for e in data.get('errors', []) if 'heard directory' in str(e)]
        if transport_error: errors.append(transport_error)
        return Snapshot(normalize(data), 'offline catalog capture', time.time(), text(data.get('captured')),
                        '; '.join(text(e, 80) for e in errors[:4]) or None)


class DirectoryDB:
    """Same stations/people/evidence/via schema used by web read-state.py."""
    def __init__(self, path, profile=False, managed=False):
        self.path=Path(path).expanduser().resolve();self.profile=profile;self.phases=None;self.managed=managed
        raw=str(self.path).encode('utf-8')
        self.uri='file:'+''.join(chr(b) if chr(b).isalnum() and b<128 or b in b'/-._~' else '%%%02X'%b for b in raw)+'?mode=ro'
        self.db=None;self.identity=None;self.version=None;self.rows=None
    def close(self):
        if self.db is not None:self.db.close()
        self.db=None;self.identity=None;self.version=None;self.rows=None
    def read(self):
        # mode=ro never creates the database. Short transaction gives one coherent catalog.
        started=time.perf_counter() if self.profile else 0
        stat=self.path.stat();identity=(stat.st_dev,stat.st_ino)
        if self.db is not None and identity!=self.identity:self.close()
        db=self.db or sqlite3.connect(self.uri,uri=True,timeout=.2)
        if self.managed:self.db,self.identity=db,identity
        try:
            version=db.execute('PRAGMA data_version').fetchone()[0]
            if self.managed and self.rows is not None and version==self.version:
                if self.profile:self.phases={'query_ms':(time.perf_counter()-started)*1000,'normalization_ms':0,'unchanged':True}
                return Snapshot(self.rows,'local heard directory / read-only',time.time(),'',None)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.execute('BEGIN')
            stations = [dict(r) for r in db.execute("SELECT s.call,s.first,s.last,s.packets,substr(p.name,1,80) AS name,p.buddy,substr(p.notes,1,512) AS notes FROM stations s LEFT JOIN people p ON p.call=s.call ORDER BY CASE WHEN s.last LIKE 'legacy %' THEN 1 ELSE 0 END,s.last DESC,s.call DESC LIMIT 128")]
            calls = tuple(row['call'] for row in stations)
            data = dict(stations=stations, evidence=[], via=[])
            if calls:
                marks = ','.join('?' for _ in calls)
                data['evidence'] = [dict(r) for r in db.execute('SELECT call,kind,stamp,substr(detail,1,512) AS detail FROM evidence WHERE call IN ('+marks+') ORDER BY call,kind LIMIT 2000', calls)]
                data['via'] = [dict(r) for r in db.execute('SELECT * FROM via WHERE call IN ('+marks+') ORDER BY call,last DESC LIMIT 1000', calls)]
            queried=time.perf_counter() if self.profile else 0
            rows=normalize(data)
            if self.profile:self.phases={'query_ms':(queried-started)*1000,'normalization_ms':(time.perf_counter()-queried)*1000}
            if self.managed:self.rows,self.version=rows,version
            return Snapshot(rows, 'local heard directory / read-only', time.time(), '', None)
        finally:
            db.rollback()
            if not self.managed:db.close()


class Reader:
    """Single worker and coalesced latest result. Views never perform I/O."""
    def __init__(self, source, interval=5, profile=False):
        self.source, self.interval = source, max(.1, interval)
        self.readable, self._write = socket.socketpair()
        self.readable.setblocking(False); self._write.setblocking(False)
        self._lock = threading.Lock(); self._latest = None
        self._wake = threading.Event(); self._stop = threading.Event()
        self.reads = 0; self.read_seconds = 0;self.cpu_seconds=0;self.profile=profile
        self.thread = threading.Thread(target=self._owned_run, name='heard-reader', daemon=True)
        self.thread.start()
    def _owned_run(self):
        try:self._run()
        finally:
            close=getattr(self.source,'close',None)
            if close is not None:close()
    def _run(self):
        while not self._stop.is_set():
            self._wake.clear(); started = time.monotonic();cpu=time.thread_time() if self.profile else 0
            try: result = self.source.read()
            except (OSError, ValueError, TypeError, KeyError, sqlite3.Error) as exc:
                result = Snapshot(None, 'source unavailable', time.time(), '', text(type(exc).__name__ + ': ' + str(exc), 160))
            if self.profile:self.cpu_seconds+=time.thread_time()-cpu
            self.reads += 1; self.read_seconds += time.monotonic() - started
            with self._lock: self._latest = result
            try: self._write.send(b'x')
            except BlockingIOError: pass
            self._wake.wait(self.interval)
    def refresh(self): self._wake.set()
    def drain(self):
        try:
            while self.readable.recv(4096): pass
        except BlockingIOError: pass
        with self._lock:
            result, self._latest = self._latest, None
        return result
    def close(self):
        self._stop.set(); self._wake.set(); self.thread.join(timeout=3)
        if self.thread.is_alive(): raise RuntimeError('reader did not stop')
        self.readable.close(); self._write.close()
