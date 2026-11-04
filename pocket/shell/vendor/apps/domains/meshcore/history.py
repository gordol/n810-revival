"""Private durable message archive; UI snapshots are only a bounded recent view."""
import hashlib
import os
from pathlib import Path
import sqlite3
import stat
import sys
import tempfile

# Reuse the companion owner's existing service codec; no RNS stack import.
_codec_root=str(Path(__file__).resolve().parents[1]/'reticulum')
if _codec_root not in sys.path:sys.path.insert(0,_codec_root)
from discovery_codec import pack,unpack


class History:
    def __init__(self, path):
        self.path = Path(path)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError('Message archive must be private and user-owned')
        finally:
            os.close(fd)
        db = self.connect()
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, body BLOB NOT NULL)')
            self._migrate(db)
        finally:
            db.close()
        # Persist the initial directory entry as well as the database contents.
        directory = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    @staticmethod
    def _legacy(body,identity):
        import json  # One-time import boundary, never used for current writes.
        value=json.loads(body)
        if not isinstance(value,dict) or value.get('id')!=identity:
            raise ValueError('Legacy message identity does not match its archive key')
        return value

    def _digest(self,db):
        digest=hashlib.sha256()
        for rowid,identity,body in db.execute('SELECT rowid,id,body FROM messages ORDER BY rowid'):
            if isinstance(body,str):pack(self._legacy(body,identity))
            else:
                value=unpack(body)
                if not isinstance(value,dict) or value.get('id')!=identity:raise ValueError('Invalid binary message identity')
            raw=body.encode('utf-8') if isinstance(body,str) else bytes(body)
            for item in (str(rowid).encode(),identity.encode('utf-8'),raw):
                digest.update(len(item).to_bytes(8,'big'));digest.update(item)
        return digest.hexdigest()

    def _migrate(self,db):
        # Reserve the writer before inspecting data. Other writers cannot race
        # the consistent backup or interleave TEXT rows with this transaction.
        if db.execute('PRAGMA user_version').fetchone()[0]==2:return
        db.execute('BEGIN IMMEDIATE')
        temporary=None
        try:
            if not db.execute("SELECT 1 FROM messages WHERE typeof(body)='text' LIMIT 1").fetchone():
                db.execute('PRAGMA user_version=2');db.commit();return
            digest=self._digest(db)
            # A changed legacy archive receives its own backup. An interrupted
            # retry reuses the same digest, without overwriting earlier data.
            backup=self.path.with_name(self.path.name+'.before-msgpack-'+digest[:24])
            if backup.exists() or backup.is_symlink():
                info=backup.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077:
                    raise ValueError('Unsafe pre-migration message backup')
                previous=sqlite3.connect('file:'+str(backup)+'?mode=ro',uri=True)
                try:
                    if self._digest(previous)!=digest:raise ValueError('Pre-migration backup does not match original messages')
                finally:previous.close()
            else:
                fd,temporary=tempfile.mkstemp(prefix='.message-backup-',dir=self.path.parent);os.close(fd)
                source=sqlite3.connect(self.path,timeout=10);destination=sqlite3.connect(temporary)
                try:source.backup(destination)
                finally:destination.close();source.close()
                fd=os.open(temporary,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
                os.replace(temporary,backup);temporary=None
                directory=os.open(self.path.parent,os.O_RDONLY)
                try:os.fsync(directory)
                finally:os.close(directory)
            for rowid,identity,body in db.execute("SELECT rowid,id,body FROM messages WHERE typeof(body)='text' ORDER BY rowid"):
                db.execute('UPDATE messages SET body=? WHERE rowid=?',(pack(self._legacy(body,identity)),rowid))
            db.execute('PRAGMA user_version=2');db.commit()
        except BaseException:
            db.rollback();raise
        finally:
            if temporary is not None:
                try:os.unlink(temporary)
                except FileNotFoundError:pass

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.execute('PRAGMA synchronous=FULL')
        return db

    def put(self, row, replace=True):
        db = self.connect()
        try:
            with db:
                db.execute('INSERT INTO messages(id,body) VALUES (?,?) ON CONFLICT(id) '+
                           ('DO UPDATE SET body=excluded.body' if replace else 'DO NOTHING'),
                           (row['id'], pack(row)))
        finally:
            db.close()

    def latest(self, limit=32):
        db = self.connect()
        try:
            return list(reversed([unpack(row[0]) for row in db.execute(
                'SELECT body FROM messages ORDER BY rowid DESC LIMIT ?', (limit,))]))
        finally:
            db.close()
