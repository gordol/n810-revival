"""Bounded raw KISS records and atomic snapshots. No Bluetooth access."""
import collections
import datetime
import json
import os
from pathlib import Path
import tempfile

MAX_RECORDS = 200
MAX_BYTES = 256 * 1024
SNAPSHOT = os.path.expanduser('~/.local/state/n810-aprs/raw-frames.json')


# Resource budgets are process settings, read once per History instance.
def setting(name,default,maximum):
    try:value=int(os.environ.get(name,default))
    except ValueError:raise ValueError(name+' must be an integer') from None
    if not 1<=value<=maximum:raise ValueError(name+' must be between 1 and '+str(maximum))
    return value


def limits():
    return tuple(setting(*item) for item in (
        ('POCKET_RX_HISTORY_RECORDS',200,10000),
        ('POCKET_RX_HISTORY_BYTES',256*1024,16*1024*1024),
        ('POCKET_RX_ARCHIVE_RECORDS',100000,10000000),
        ('POCKET_RX_PAGE_RECORDS',50,200)))


def private_archive(path):
    import stat
    info=path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
        raise ValueError('Packet archive must be a private user-owned regular file')


def archive_path():
    return Path(os.environ.get('POCKET_RX_ARCHIVE',str(Path(SNAPSHOT).with_name('packets.sqlite3')))).expanduser()


class Archive:
    """Append raw bytes; indexed keyset pages never decode or scan the archive."""
    def __init__(self,path=None):
        import sqlite3
        self.path=Path(path).expanduser() if path is not None else archive_path()
        self.path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        if self.path.is_symlink():raise ValueError('Archive must not be a symlink')
        fd=os.open(self.path,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600);os.close(fd)
        private_archive(self.path)
        self.db=sqlite3.connect(str(self.path));self.keep=limits()[2]
        self.byte_budget=setting('POCKET_RX_ARCHIVE_BYTES',32*1024*1024,1024*1024*1024)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=NORMAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS packets (id INTEGER PRIMARY KEY AUTOINCREMENT,time TEXT NOT NULL,direction TEXT NOT NULL,frame BLOB NOT NULL,origin TEXT,wire BLOB,start_bytes INTEGER NOT NULL,end_bytes INTEGER NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS packets_time ON packets(time)')
        self.db.execute('CREATE INDEX IF NOT EXISTS packets_bytes ON packets(start_bytes)')
        last=self.db.execute('SELECT end_bytes FROM packets ORDER BY id DESC LIMIT 1').fetchone()
        self.empty=last is None
        self.end_bytes=last[0] if last else 0
        self.db.commit()
    def add(self,row):
        with self.db:self._insert(row)
    def seed(self,rows):
        if self.empty:
            with self.db:
                for row in rows:self._insert(row)
        self.empty=False
    def _insert(self,row):
        import struct
        row=validate(row)
        parts=[bytes.fromhex(part) for part in row.get('wire_frames',[])]
        wire=b''.join(struct.pack('!H',len(part))+part for part in parts)
        end=self.end_bytes+len(row['frame'])//2+len(wire)+len(row['time'])+len(row['direction'])+128
        cursor=self.db.execute('INSERT INTO packets(time,direction,frame,origin,wire,start_bytes,end_bytes) VALUES(?,?,?,?,?,?,?)',(row['time'],row['direction'],bytes.fromhex(row['frame']),row.get('origin'),wire,self.end_bytes,end))
        # AUTOINCREMENT IDs make pruning bounded and cursors stable across restarts.
        self.db.execute('DELETE FROM packets WHERE id<=?',(cursor.lastrowid-self.keep,))
        self.db.execute('DELETE FROM packets WHERE start_bytes<?',(end-self.byte_budget,))
        self.end_bytes=end
    def close(self):self.db.close()


def page(before=None,path=None,budget=12000,anchor=None):
    import sqlite3,struct
    count=limits()[3]
    if before is not None and (type(before) is not int or before<1):raise ValueError('Invalid history cursor')
    path=Path(path).expanduser() if path is not None else archive_path()
    if not path.exists():return dict(version=1,records=[],before=None,more=False)
    if path.is_symlink():raise ValueError('Archive must not be a symlink')
    private_archive(path)
    db=sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        if before is None and anchor is not None:
            anchor=validate(anchor)
            found=db.execute('SELECT id FROM packets WHERE time=? AND direction=? AND frame=? ORDER BY id DESC LIMIT 1',(anchor['time'],anchor['direction'],bytes.fromhex(anchor['frame']))).fetchone()
            if found:before=found[0]
        rows=db.execute('SELECT id,time,direction,frame,origin,wire FROM packets WHERE id<? ORDER BY id DESC LIMIT ?',(before if before is not None else 9223372036854775807,count+1))
        records=[];size=0;more=False;cursor=before
        for ident,stamp,direction,frame,origin,wire in rows:
            cost=len(frame)*2+len(wire or b'')*2+512
            if len(records)>=count or size+cost>budget:
                if not records:raise ValueError('Archived packet exceeds service page budget')
                more=True;break
            row=dict(time=stamp,direction=direction,frame=frame.hex())
            if origin:
                parts=[];offset=0
                while offset<len(wire):
                    length=struct.unpack_from('!H',wire,offset)[0];offset+=2
                    parts.append(wire[offset:offset+length].hex());offset+=length
                row.update(origin=origin,wire_frames=parts)
            records.append(row);cursor=ident;size+=cost
        return dict(version=1,records=records,before=cursor,more=more)
    except sqlite3.Error as error:raise ValueError('Packet archive unavailable: '+str(error)) from error
    finally:db.close()


def validate(row):
    if not isinstance(row, dict) or row.get('direction') not in ('radio_to_host','host_to_radio_written'):
        raise ValueError('invalid raw direction')
    if not isinstance(row.get('time'),str) or len(row['time'])>64:raise ValueError('invalid timestamp')
    stamp = datetime.datetime.fromisoformat(row['time'])
    if stamp.tzinfo is None: raise ValueError('timestamp needs timezone')
    frame = bytes.fromhex(row['frame'])
    if not frame or len(frame) > 65536: raise ValueError('invalid raw frame size')
    result=dict(time=row['time'], direction=row['direction'], frame=frame.hex())
    if row.get('origin')=='vendor_reassembled':
        wire=row.get('wire_frames')
        if not isinstance(wire,list) or not 1<=len(wire)<=64:raise ValueError('invalid vendor fragments')
        parts=[bytes.fromhex(part) for part in wire]
        if any(not part.startswith(b'\xff\1') or len(part)>264 for part in parts):raise ValueError('invalid vendor frame')
        result.update(origin='vendor_reassembled',wire_frames=[part.hex() for part in parts])
    return result


def record_size(row):
    return len(row['frame'])//2+sum(len(part)//2 for part in row.get('wire_frames',[]))


class History:
    def __init__(self):
        self.records=collections.deque(); self.size=0
        self.max_records,self.max_bytes,_,_=limits()
        self.archive=None

    def add(self, row):
        row=validate(row);size=record_size(row)
        if self.archive is not None:
            try:self.archive.add(row)
            except Exception as error:
                # Disk failure must not interrupt radio reception. Queries expose
                # the archive's last successful records; the owner logs the fault.
                import sys
                print('Packet archive write failed: '+str(error),file=sys.stderr,flush=True)
                self.archive.close();self.archive=None
        self.records.append(row);self.size+=size
        while len(self.records)>self.max_records or self.size>self.max_bytes:
            self.size-=record_size(self.records.popleft())
        return row

    def decoded(self, describe):
        lines=collections.deque(maxlen=self.max_records)
        for row in self.records:
            if row['direction']!='radio_to_host':continue
            text=describe(bytes.fromhex(row['frame']))
            if text and not text.startswith(('Malformed ', 'Short ')):
                stamp=datetime.datetime.fromisoformat(row['time']).strftime('%H:%M:%S')
                lines.append((stamp+' '+text+'\n').encode('utf-8'))
        return lines

    def export(self):
        header=dict(type='snapshot', version=1, records=len(self.records), raw_bytes=self.size)
        return (json.dumps(header)+'\n'+''.join(json.dumps(row)+'\n' for row in self.records)).encode('utf-8')

    def save(self, filename=SNAPSHOT):
        target=Path(filename);target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix='.raw-',dir=target.parent)
        try:
            with os.fdopen(fd,'w') as f:
                json.dump(dict(version=1,records=list(self.records)),f);f.write('\n');f.flush();os.fsync(f.fileno())
            os.replace(temp,target)
            directory=os.open(target.parent,os.O_RDONLY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:
            if os.path.exists(temp):os.unlink(temp)

    @classmethod
    def load(cls, filename=SNAPSHOT):
        result=cls()
        with open(filename) as f:saved=json.load(f)
        if not isinstance(saved,dict) or saved.get('version')!=1 or not isinstance(saved.get('records'),list):raise ValueError('invalid raw snapshot')
        for row in saved['records'][-result.max_records:]:result.add(row)
        return result
