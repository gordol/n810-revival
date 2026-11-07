# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit FCC download and local import; no automatic startup network work."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import sqlite3
import zipfile
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler,Request,build_opener
from datetime import datetime,timezone

SOURCE='https://data.fcc.gov/download/pub/uls/complete/l_amat.zip'
MAX_ARCHIVE=512*1024*1024


class FCCRedirects(HTTPRedirectHandler):
    def redirect_request(self,request,response,code,message,headers,newurl):
        destination=urlparse(newurl)
        if destination.scheme!='https' or destination.hostname!='data.fcc.gov':
            raise ValueError('FCC download redirected outside the expected HTTPS host')
        return super().redirect_request(request,response,code,message,headers,newurl)


def sha256(path):
    with Path(path).open('rb') as file:return hashlib.file_digest(file,'sha256').hexdigest()


def atomic_json(path,value):
    fd,temp=tempfile.mkstemp(prefix='.fcc-state-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as file:
            json.dump(value,file,indent=2);file.write('\n');file.flush();os.fsync(file.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def download(cache,previous,*,opener=None,progress=None):
    destination=cache/'l_amat.zip'
    # Keep urllib's standard client identification. FCC rejects our former
    # custom Pocket-ULS User-Agent with HTTP 403 even for this public archive.
    headers={}
    cached=destination.is_file() and sha256(destination)==previous.get('archive_sha256')
    if previous.get('etag') and cached:
        headers['If-None-Match']=previous['etag']
    opener=opener or build_opener(FCCRedirects())
    try:response=opener.open(Request(SOURCE,headers=headers),timeout=60)
    except HTTPError as error:
        if error.code==304 and 'If-None-Match' in headers:return destination,previous,False
        raise
    # FCC can answer a conditional GET with 200 despite an unchanged ETag.
    # A verified local copy with the same strong tag/size needs no body download.
    length=response.headers.get('Content-Length')
    if cached and previous.get('etag') and not previous['etag'].startswith('W/') and response.headers.get('ETag')==previous['etag'] and length and int(length)==destination.stat().st_size:
        response.close()
        return destination,previous,False
    fd,temp=tempfile.mkstemp(prefix='.fcc-download-',dir=cache)
    try:
        with response,os.fdopen(fd,'wb') as output:
            length=response.headers.get('Content-Length')
            if length and int(length)>MAX_ARCHIVE:raise ValueError('FCC download exceeds size limit')
            total=0
            while True:
                data=response.read(1024*1024)
                if not data:break
                total+=len(data)
                if total>MAX_ARCHIVE:raise ValueError('FCC download exceeds size limit')
                output.write(data)
                if progress:
                    progress('Downloading FCC: '+str(total//1048576)+' MiB'+(' / '+str(int(length)//1048576)+' MiB' if length else ''))
            if not total or length and total!=int(length):raise ValueError('FCC download was empty or incomplete')
            output.flush();os.fsync(output.fileno())
            metadata=dict(etag=response.headers.get('ETag'),last_modified=response.headers.get('Last-Modified'))
        os.replace(temp,destination)
        metadata['archive_sha256']=sha256(destination)
        return destination,metadata,True
    finally:
        if os.path.exists(temp):os.unlink(temp)


def update(database, cache_dir, progress=None, minimum_stations=500000, archive=None, cancelled=None):
    from fcc_database import build, status
    database = Path(database).expanduser().resolve()
    cache = Path(cache_dir).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    def notify(message):
        if cancelled is not None and cancelled.is_set():
            from concurrent.futures import CancelledError
            raise CancelledError('FCC update cancelled; previous database retained')
        if progress:progress(message)
    with (cache/'update.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('FCC update already running') from None
        state_path = cache/'update.json'
        previous = json.loads(state_path.read_text()) if state_path.exists() else {}
        if archive is None:
            notify('Checking FCC weekly amateur license data…')
            archive, metadata, changed = download(cache, previous, progress=notify)
        else:
            archive = Path(archive).expanduser().resolve()
            metadata, changed = dict(archive_sha256=sha256(archive)), True
        if not changed and database.is_file() and previous.get('database') == str(database):
            if sha256(database) == previous.get('database_sha256') and status(database).get('schema_version', 0) >= 2:
                notify('FCC snapshot is already current')
                return dict(updated=False, **status(database))
        notify('Compiling offline FCC database…')
        result = build(archive, database, minimum_stations=minimum_stations,
                       progress=lambda name, count: notify(name+': '+str(count)+' records'),cancelled=cancelled)
        state = dict(metadata, database=str(database), database_sha256=sha256(database),
                     last_checked_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), import_result=result)
        atomic_json(state_path, state)
        notify('Offline FCC database ready')
        return dict(updated=True, **result)


def main(argv=None):
    from uls_directory import user_database
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=user_database())
    parser.add_argument('--cache-dir', type=Path, default=Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'pocket/fcc')
    parser.add_argument('--archive', type=Path, help='Use an already downloaded official ZIP without network access')
    parser.add_argument('--minimum-stations', type=int, default=500000)
    args = parser.parse_args(argv)
    try:
        result = update(args.database, args.cache_dir, progress=lambda message: print(message, file=sys.stderr, flush=True),
                        minimum_stations=args.minimum_stations, archive=args.archive)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile, sqlite3.Error) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
