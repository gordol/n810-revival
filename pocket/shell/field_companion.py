"""Portable, offline field cards and private companion observations."""
from contextlib import closing
from datetime import datetime, timezone
import os
import json
import tempfile
from pathlib import Path
import re
import sqlite3
import stat
import uuid

from runtime_codec import atomic_write, pack, unpack

PACK = 'pocket.field-pack/1'
LOG = 'pocket.field-log/1'
LIMIT = 1024 * 1024
KINDS = ('guide', 'phrase')


def state_root():
    return Path(os.environ.get('XDG_STATE_HOME') or Path.home()/'.local/state')/'current-world/field-companion'


def text(value, maximum, *, multiline=False):
    if (not isinstance(value, str) or not value.strip() or len(value) > maximum or
            any(not c.isprintable() and not (multiline and c == '\n') for c in value)):
        raise ValueError('Invalid or oversized field text')
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', value):
        raise ValueError('Expected a lowercase identifier')
    return value


def mapping(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError('Missing or unexpected fields')


def check_pack(data):
    mapping(data, 'format id region cards')
    if data['format'] != PACK:
        raise ValueError('Unsupported field pack format')
    identifier(data['id'])
    text(data['region'], 120)
    cards = data['cards']
    if not isinstance(cards, list) or not 1 <= len(cards) <= 256:
        raise ValueError('A pack needs 1 to 256 cards')
    seen = set()
    for card in cards:
        mapping(card, 'id kind title body source terms')
        key = identifier(card['id'])
        if key in seen or card['kind'] not in KINDS:
            raise ValueError('Duplicate card or unsupported card kind')
        seen.add(key)
        for field, limit in [('title', 160), ('body', 16000), ('source', 512), ('terms', 512)]:
            text(card[field], limit, multiline=field == 'body')
    return data


def bounded_bytes(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError('Select a regular file')
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT:
        raise ValueError('Transfer exceeds one MiB')
    return raw


def read_file(path):
    return unpack(bounded_bytes(path), LIMIT)


def write_file(path, data):
    if len(pack(data)) > LIMIT:
        raise ValueError('Transfer exceeds one MiB')
    atomic_write(path, data)


def read_log(path):
    try:
        return json.loads(bounded_bytes(path).decode('utf-8'))
    except RecursionError as error:
        raise ValueError('Observation file is nested too deeply') from error


def encoded_log(notes):
    return json.dumps(dict(format=LOG, notes=notes), ensure_ascii=False).encode('utf-8')


def write_log(path, notes):
    raw = encoded_log(notes)
    if len(raw) > LIMIT:
        raise ValueError('Transfer exceeds one MiB')
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def activate(path, root):
    data = check_pack(read_file(path))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    write_file(root/'active.pack', data)
    return data


def active(root):
    try:
        return check_pack(read_file(root/'active.pack'))
    except FileNotFoundError:
        return None


FIELDS = ('id', 'region', 'time', 'source', 'kind', 'body')


def observation(region, source, kind, body):
    return dict(zip(FIELDS, (str(uuid.uuid4()), region, datetime.now(timezone.utc).isoformat(),
                             source, kind, body)))


def validate_note(note):
    mapping(note, ' '.join(FIELDS))
    if str(uuid.UUID(text(note['id'], 36))) != note['id']:
        raise ValueError('Expected canonical observation UUID')
    identifier(note['region'])
    if datetime.fromisoformat(text(note['time'], 40)).utcoffset() is None:
        raise ValueError('Observation time needs a UTC offset')
    text(note['source'], 96)
    if note['kind'] not in ('note', 'transcript', 'translation'):
        raise ValueError('Unknown observation kind')
    text(note['body'], 4096, multiline=True)


class Journal:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root/'observations.sqlite3'
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS notes (id TEXT PRIMARY KEY, region TEXT, '
                       'time TEXT, source TEXT, kind TEXT, body TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS region_time ON notes(region, time)')

    def merge(self, batch):
        mapping(batch, 'format notes')
        notes = batch['notes']
        if batch['format'] != LOG or not isinstance(notes, list) or len(notes) > 1024:
            raise ValueError('Unsupported observation batch')
        added = 0
        with closing(sqlite3.connect(self.path)) as db, db:
            for note in notes:
                validate_note(note)
                values = tuple(note[key] for key in FIELDS)
                result = db.execute('INSERT INTO notes VALUES (?, ?, ?, ?, ?, ?) '
                                    'ON CONFLICT(id) DO NOTHING', values)
                if result.rowcount:
                    added += 1
                elif db.execute('SELECT * FROM notes WHERE id=?', (note['id'],)).fetchone() != values:
                    raise ValueError('Conflicting observation ID')
        return added

    def export_page(self, region, after=''):
        if after and str(uuid.UUID(after)) != after:
            raise ValueError('Invalid export cursor')
        size = len(encoded_log([]))
        notes = []
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute('SELECT * FROM notes WHERE region=? AND id>? ORDER BY id LIMIT 1025',
                              (identifier(region), after))
            for row in rows:
                note = dict(zip(FIELDS, row))
                size += len(json.dumps(note, ensure_ascii=False).encode('utf-8')) + (2 if notes else 0)
                if size > LIMIT or len(notes) == 1024:
                    return notes, notes[-1]['id']
                notes.append(note)
        return notes, None

    def recent(self, region, limit=100):
        with closing(sqlite3.connect(self.path)) as db:
            rows = db.execute('SELECT * FROM notes WHERE region=? ORDER BY julianday(time) DESC, id '
                              'LIMIT ?', (identifier(region), limit))
            return [dict(zip(FIELDS, row)) for row in rows]
