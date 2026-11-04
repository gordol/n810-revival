"""Bounded read-only access to the local FCC lookup snapshot."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from data_paths import data_root
import re
import sqlite3
import time
from functools import lru_cache


def default_database():
    configured=os.environ.get('POCKET_ULS_DB')
    if configured:return Path(configured).expanduser()
    local=data_root()/'uls.sqlite'
    if local.is_file():return local
    return Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'pocket'/'uls.sqlite'


def lookup(path,station):
    path=Path(path).expanduser().resolve()
    try:revision=(path.stat().st_mtime_ns,path.stat().st_size)
    except OSError:revision=None
    # Reuse identities across views, invalidated when the FCC snapshot changes.
    return _lookup(str(path),station,revision,datetime.now(timezone.utc).date().isoformat())


@lru_cache(maxsize=512)
def _lookup(path,station,revision,day):
    match=re.fullmatch(r'([A-Z0-9]{1,6})(?:-([0-9]{1,2}))?',station.strip().upper())
    if not match or match[2] is not None and int(match[2])>15:
        raise ValueError('Enter a US callsign, optionally with SSID 0 to 15')
    path=Path(path).expanduser().resolve()
    if not path.is_file():raise ValueError('FCC database is not installed. Choose a prepared ULS SQLite file.')
    deadline=time.monotonic()+2
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=1) as db:
        db.row_factory=sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        db.execute('PRAGMA trusted_schema=OFF')
        db.set_progress_handler(lambda:int(time.monotonic()>deadline),1000)
        metadata={row['key']:json.loads(row['value']) for row in db.execute('SELECT key,value FROM fcc_meta')}
        row=db.execute('''SELECT s.*, d.usid, d.service, d.granted, d.expires,
            d.action_date, d.postal_code FROM stations s JOIN license_details d USING(callsign)
            WHERE callsign=?''',(match[1],)).fetchone()
    date=metadata.get('source_data_date','')
    age=(datetime.now(timezone.utc).date()-datetime.fromisoformat(date).date()).days if date else None
    return dict(station=station.strip().upper(),base_callsign=match[1],record=dict(row) if row else None,
                source_data_date=date,source_age_days=age,imported_at=metadata.get('imported_at',''),
                source=metadata.get('source_url',''),stations=metadata.get('stations'),database=str(path))
