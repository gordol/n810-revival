#!/usr/bin/env python3
"""Bounded receive-history capture; reads the existing replay socket only."""
import argparse
import collections
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import time


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def snapshot(path, history):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3); client.connect(path)
        with client.makefile('rb') as stream:
            header = json.loads(stream.readline(4096))
            count = header.get('records')
            if header.get('type') != 'snapshot' or header.get('version') != 1 or type(count) is not int or not 0 <= count <= 200:
                raise ValueError('Invalid snapshot header')
            rows = history.History(); size = 0
            for _ in range(count):
                line = stream.readline(150001); size += len(line)
                if len(line) > 150000 or size > 2*1024*1024: raise ValueError('Snapshot too large')
                rows.add(json.loads(line))
            return list(rows.records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=14400)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 86400: parser.error('seconds must be 1–86400')
    lock = os.open('/dev/shm/n810-rx-record.lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
    try: fcntl.flock(lock, fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: parser.exit(2, 'Receive capture already running\n')
    journal_module = load('rx_journal', 'n810-walk-journal.py')
    history = load('rx_history', 'n810-frame-history.py')
    journal = journal_module.Journal(Path.home()/'.local/state/n810-aprs/captures')
    running = True
    def stop(*_):
        nonlocal running
        running = False
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP): signal.signal(sig, stop)
    start = time.time(); deadline = time.monotonic()+args.seconds
    seen = collections.OrderedDict(); count = 0; synced = 0; last = None; first = True
    state_path = Path('/dev/shm/n810-rx-record.json')
    state = dict(pid=os.getpid(), log=str(journal.path), started_at=start,
                 receive_only=True, poll_seconds=10, flush_seconds=30, max_bytes=32*1024*1024)
    def status(error=None, active=True):
        state.update(observed_at=time.time(), active=active, records=count, synced_records=synced,
                     last_rx_time=last, error=error)
        temp = state_path.with_suffix('.tmp')
        temp.write_text(json.dumps(state)); os.chmod(temp, 0o600); os.replace(temp, state_path)
    journal.add('capture_start', receive_only=True, source='/dev/shm/n810-aprs-replay.sock',
                initial_history='retained original records; not new RF', duration_seconds=args.seconds,
                limitation='Snapshot ring holds 200 records; overflow between 10-second reads can lose records')
    try:
        while running and time.monotonic() < deadline:
            error = None
            try:
                rows = snapshot('/dev/shm/n810-aprs-replay.sock', history)
                for row in rows:
                    identity = hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest()
                    if identity in seen: continue
                    seen[identity] = None
                    while len(seen) > 2000: seen.popitem(last=False)
                    journal.add('raw_record', record=row)
                    count += 1
                    if row['direction'] == 'radio_to_host': last = row['time']
                if first or time.monotonic() >= journal.due:
                    journal.flush(); synced = count; first = False
            except (OSError, ValueError, KeyError, TypeError) as exc:
                error = str(exc)
            if time.monotonic() >= journal.due:
                journal.flush(); synced = count
            status(error)
            if os.fstat(journal.fd).st_size >= state['max_bytes']:
                journal.add('capture_limit', reason='32 MiB limit reached'); break
            for _ in range(10):
                if not running or time.monotonic() >= deadline: break
                time.sleep(1)
    finally:
        journal.add('capture_end', records=count); journal.close(); synced = count
        status(active=False); os.close(lock)


if __name__ == '__main__': main()
