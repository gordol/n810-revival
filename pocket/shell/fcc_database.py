# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Import the FCC weekly amateur snapshot into a compact offline SQLite directory."""
from contextlib import closing
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import zipfile

import re


def base_call(value):
    if not isinstance(value, str):
        raise ValueError('Callsign required')
    match = re.fullmatch(r'([A-Z0-9]{1,6})(?:-([0-9]{1,2}))?', value.strip().upper())
    if not match or match[2] is not None and int(match[2]) > 15:
        raise ValueError('Use a base callsign or callsign with SSID 0 to 15')
    return match[1]

SOURCE = 'https://data.fcc.gov/download/pub/uls/complete/l_amat.zip'
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_MEMBER = 1024 * 1024 * 1024
MAX_RECORD = 65536


def iso_date(value):
    if not value:
        return ''
    try:
        return datetime.strptime(value, '%m/%d/%Y').date().isoformat()
    except ValueError as error:
        raise ValueError('Invalid FCC date: ' + value) from error


def records(archive, name, minimum):
    """FCC fields can contain physical line breaks; record tags delimit records."""
    tag = name[:2].encode('ascii') + b'|'
    pending = bytearray()
    def parsed(raw):
        fields = raw.decode('latin-1').rstrip('\r\n').split('|')
        fields = [value.replace('\r', ' ').replace('\n', ' ').strip() for value in fields]
        if len(fields) < minimum or fields[0] != name[:2] or not fields[1].isdigit():
            raise ValueError('Malformed ' + name + ' record')
        return fields
    with archive.open(name) as stream:
        while True:
            line = stream.readline(MAX_RECORD + 1)
            if not line:
                break
            if line.startswith(tag) and pending:
                yield parsed(pending)
                pending.clear()
            if not pending and not line.startswith(tag):
                raise ValueError('Unexpected continuation in ' + name)
            pending.extend(line)
            if len(pending) > MAX_RECORD:
                raise ValueError('FCC record exceeds size bound')
        if pending:
            yield parsed(pending)


def archive_info(path):
    path = Path(path)
    if not 0 < path.stat().st_size <= MAX_ARCHIVE:
        raise ValueError('FCC ZIP exceeds size bound or is empty')
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    with zipfile.ZipFile(path) as archive:
        items = archive.infolist()
        if len(items) > 64 or len({i.filename for i in items}) != len(items):
            raise ValueError('Archive has duplicate or excessive members')
        result = {}
        for name in ('HD.dat', 'EN.dat', 'AM.dat'):
            item = archive.getinfo(name)
            if not 0 < item.file_size <= MAX_MEMBER or item.flag_bits & 1:
                raise ValueError('Invalid FCC member size or encryption')
            result[name] = dict(bytes=item.file_size, member_time=datetime(*item.date_time).isoformat())
    return dict(archive_sha256=sha, archive_bytes=path.stat().st_size, members=result,
                source_data_date=min(v['member_time'][:10] for v in result.values()),
                time_basis='ZIP member timestamps; timezone unspecified')


def build(archive_path, destination, *, minimum_stations=1, progress=None, cancelled=None):
    """Build in a sibling file and publish only after validation; retain old data on failure."""
    info = archive_info(archive_path)
    destination = Path(destination)
    if destination.is_symlink():
        raise ValueError('Database destination must not be a symlink')
    if destination.resolve() == Path(archive_path).resolve():
        raise ValueError('Database and archive must have different paths')
    if destination.exists():
        with closing(sqlite3.connect(destination.resolve().as_uri() + '?mode=ro', uri=True)) as old:
            if old.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='notes'").fetchone():
                if old.execute('SELECT COUNT(*) FROM notes').fetchone()[0]:
                    raise ValueError('Keep FCC snapshots separate from a database containing local notes')
    fd, temporary = tempfile.mkstemp(prefix='.fcc-build-', suffix='.sqlite', dir=destination.parent)
    os.close(fd)
    conn = None
    counts = {}
    skipped_blank_callsigns = 0
    try:
        conn = sqlite3.connect(temporary)
        if cancelled is not None:
            conn.set_progress_handler(lambda:int(cancelled.is_set()),10000)
        conn.executescript('''
            PRAGMA journal_mode=DELETE;
            PRAGMA synchronous=FULL;
            PRAGMA cache_size=-16384;
            PRAGMA temp_store=FILE;
            CREATE TABLE headers (usid INTEGER PRIMARY KEY, callsign TEXT, status TEXT,
                service TEXT, granted TEXT, expires TEXT, action_date TEXT);
            CREATE TABLE entities (usid INTEGER PRIMARY KEY, name TEXT, city TEXT,
                region TEXT, postal_code TEXT, priority INTEGER, street_address TEXT,
                po_box TEXT, attention_line TEXT, frn TEXT, entity_type TEXT, applicant_type TEXT);
            CREATE TABLE amateurs (usid INTEGER PRIMARY KEY, license_class TEXT);
        ''')
        with zipfile.ZipFile(archive_path) as archive:
            for filename, minimum in (('HD.dat', 44), ('EN.dat', 19), ('AM.dat', 6)):
                count = 0
                with conn:
                    for row in records(archive, filename, minimum):
                        count += 1
                        if progress and count % 25000 == 0:
                            progress(filename, count)
                        if filename == 'HD.dat':
                            if row[6] not in ('HA', 'HV'):
                                continue
                            if not row[4] and row[5] != 'A':
                                skipped_blank_callsigns += 1
                                continue
                            call = base_call(row[4])
                            conn.execute('INSERT INTO headers VALUES (?,?,?,?,?,?,?)',
                                         (int(row[1]), call, row[5], row[6], iso_date(row[7]),
                                          iso_date(row[8]), iso_date(row[43])))
                        elif filename == 'EN.dat':
                            if row[5] not in ('L', ''):
                                continue
                            name = row[7] or ' '.join(v for v in (row[8], row[9], row[10], row[11]) if v)
                            # FCC EN positions are 1-based in pa_ddef51.pdf:
                            # street 16, PO box 20, attention 21, FRN 23, applicant type 24.
                            extra=lambda index:row[index] if len(row)>index else ''
                            conn.execute('''INSERT INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                                ON CONFLICT(usid) DO UPDATE SET name=excluded.name, city=excluded.city,
                                region=excluded.region, postal_code=excluded.postal_code, priority=excluded.priority,
                                street_address=excluded.street_address, po_box=excluded.po_box,
                                attention_line=excluded.attention_line, frn=excluded.frn,
                                entity_type=excluded.entity_type, applicant_type=excluded.applicant_type
                                WHERE excluded.priority > entities.priority''',
                                         (int(row[1]), name, row[16], row[17], row[18], int(row[5] == 'L'),
                                          row[15], extra(19), extra(20), extra(22), row[5], extra(23)))
                        else:
                            conn.execute('INSERT INTO amateurs VALUES (?,?)', (int(row[1]), row[5]))
                counts[filename] = count
                if progress:
                    progress(filename, count)
        conn.executescript('''
            CREATE TABLE selected AS SELECT * FROM (
                SELECT h.*, ROW_NUMBER() OVER (PARTITION BY callsign ORDER BY
                    (status='A') DESC, action_date DESC, granted DESC, usid DESC) AS ranking
                FROM headers h) WHERE ranking=1;
            CREATE TABLE stations (callsign TEXT PRIMARY KEY, name TEXT, city TEXT, region TEXT,
                country TEXT, license_class TEXT, status TEXT, source TEXT, updated_at TEXT);
            CREATE TABLE license_details (callsign TEXT PRIMARY KEY, usid INTEGER,
                service TEXT, granted TEXT, expires TEXT, action_date TEXT, postal_code TEXT,
                street_address TEXT, po_box TEXT, attention_line TEXT, frn TEXT,
                entity_type TEXT, applicant_type TEXT);
            CREATE TABLE fcc_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        ''')
        with conn:
            conn.execute('''INSERT INTO stations SELECT s.callsign, COALESCE(e.name,''),
                COALESCE(e.city,''), COALESCE(e.region,''), '', COALESCE(a.license_class,''),
                s.status, ?, ? FROM selected s
                LEFT JOIN entities e ON e.usid=s.usid LEFT JOIN amateurs a ON a.usid=s.usid''',
                         (SOURCE, info['source_data_date']))
            conn.execute('''INSERT INTO license_details SELECT s.callsign, s.usid, s.service,
                s.granted, s.expires, s.action_date, COALESCE(e.postal_code,''),
                COALESCE(e.street_address,''), COALESCE(e.po_box,''), COALESCE(e.attention_line,''),
                COALESCE(e.frn,''), COALESCE(e.entity_type,''), COALESCE(e.applicant_type,'')
                FROM selected s LEFT JOIN entities e ON e.usid=s.usid''')
            total, named = conn.execute("SELECT COUNT(*), SUM(name!='') FROM stations").fetchone()
            if total < minimum_stations or not named or named < total * .9:
                raise ValueError('FCC import failed station count or name coverage validation')
            info.update(stations=total, named_stations=named, records=counts, schema_version=2,
                        skipped_blank_inactive_callsigns=skipped_blank_callsigns,
                        imported_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                        source_url=SOURCE, refresh_policy='Complete weekly snapshot; no daily deltas')
            conn.executemany('INSERT INTO fcc_meta VALUES (?,?)', ((k, json.dumps(v)) for k, v in info.items()))
        conn.executescript('DROP TABLE selected; DROP TABLE headers; DROP TABLE entities; DROP TABLE amateurs; VACUUM;')
        if conn.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('SQLite integrity check failed')
        conn.close()
        conn = None
        with open(temporary, 'rb') as stream:
            os.fsync(stream.fileno())
        if progress:
            progress('Saving offline FCC database', total)
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return info
    finally:
        if conn is not None:
            conn.close()
        for suffix in ('', '-journal'):
            try:
                os.unlink(temporary + suffix)
            except FileNotFoundError:
                pass


def lookup(database, call):
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute('''SELECT s.*, d.* FROM stations s JOIN license_details d USING(callsign)
            WHERE callsign=?''', (base_call(call),)).fetchone()
        return dict(row, requested_callsign=call.upper()) if row else None


def status(database):
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True)) as conn:
        result = {key: json.loads(value) for key, value in conn.execute('SELECT key,value FROM fcc_meta')}
    result['database_bytes'] = Path(database).stat().st_size
    result['source_age_days'] = (datetime.now(timezone.utc).date() - datetime.fromisoformat(result['source_data_date']).date()).days
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', required=True, type=Path)
    sub = parser.add_subparsers(dest='action', required=True)
    load = sub.add_parser('import')
    load.add_argument('archive', type=Path)
    load.add_argument('--minimum-stations', type=int, default=500000)
    sub.add_parser('status')
    query = sub.add_parser('lookup')
    query.add_argument('callsign')
    args = parser.parse_args(argv)
    try:
        if args.action == 'import':
            result = build(args.archive, args.database, minimum_stations=args.minimum_stations,
                           progress=lambda name, count: print(f'{name}: {count} records', file=sys.stderr, flush=True))
        elif args.action == 'lookup':
            result = lookup(args.database, args.callsign)
        else:
            result = status(args.database)
        print(json.dumps(result, sort_keys=True))
        return 0 if result is not None else 1
    except (OSError, ValueError, KeyError, sqlite3.Error, zipfile.BadZipFile, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
