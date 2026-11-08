#!/usr/bin/env python3
"""One passive receiver, RAM history, and a local Unix socket for viewers."""
import collections
import importlib.util
from pathlib import Path
import argparse
import json
import re
import signal
import os
import selectors
import socket
import subprocess
import sys
import time

SNAPSHOT = os.path.expanduser('~/.local/state/n810-aprs/last-packets.json')
_spec=importlib.util.spec_from_file_location('frame_history',Path(__file__).with_name('n810-frame-history.py'))
raw_module=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(raw_module)
_spec=importlib.util.spec_from_file_location('packet_monitor',Path(__file__).with_name('n810-packet-monitor.py'))
packet_monitor=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(packet_monitor)

PACKET = re.compile(rb'^\d\d:\d\d:\d\d \S+>\S+ ctl=[0-9a-f]+(?: pid=[0-9a-f]+)? ')

def load_snapshot(filename):
    try:
        with open(filename) as f:
            saved = json.load(f)
        if saved.get('version') != 1 or not isinstance(saved.get('packets'), list):
            raise ValueError('unsupported snapshot')
        result = collections.deque(maxlen=raw_module.limits()[0])
        for line in saved['packets'][-raw_module.limits()[0]:]:
            if not isinstance(line, str) or '\n' in line.rstrip('\n'):
                raise ValueError('invalid packet record')
            raw = line.rstrip('\n').encode('utf-8') + b'\n'
            if PACKET.match(raw):
                result.append(raw)
        return result
    except FileNotFoundError:
        return collections.deque(maxlen=raw_module.limits()[0])
    except (ValueError, OSError, AttributeError) as exc:
        print('Could not load snapshot: '+str(exc), file=sys.stderr, flush=True)
        return collections.deque(maxlen=raw_module.limits()[0])

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proxy', action='store_true', help='Expose a phone Bluetooth relay while receiving packets')
    args = parser.parse_args()
    receiver = '/home/nokia/n810-radio-proxy.py' if args.proxy else '/home/nokia/uvpro-aprs-listen.py'
    path = '/dev/shm/n810-aprs.sock'
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    # Refuse an active feed; only remove a stale socket.
    if os.path.exists(path):
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.connect(path)
        except ConnectionRefusedError:
            os.unlink(path)
        else:
            raise SystemExit('An APRS feed is already running')
        finally:
            probe.close()
    server.bind(path)
    os.chmod(path, 0o600)
    server.listen(4)
    server.setblocking(False)
    sel = selectors.DefaultSelector()
    sel.register(server, selectors.EVENT_READ)
    clients = {}
    replay_clients = set()
    replay_path='/dev/shm/n810-aprs-replay.sock'
    # Same owner as the decoded feed; an existing live decoded feed was rejected above.
    if os.path.exists(replay_path): os.unlink(replay_path)
    replay_server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    replay_server.bind(replay_path);os.chmod(replay_path,0o600);replay_server.listen(4);replay_server.setblocking(False)
    sel.register(replay_server,selectors.EVENT_READ)
    try:
        raw_history=raw_module.History.load()
        history=raw_history.decoded(packet_monitor.describe)
        if not raw_history.records: history=load_snapshot(SNAPSHOT)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        raw_history=raw_module.History()
        history=load_snapshot(SNAPSHOT)
        if not isinstance(exc,FileNotFoundError): print('Raw snapshot unavailable: '+str(exc),flush=True)

    latest_status = b''
    child = None
    retry_at = 0.0
    pending = b''
    try:
        raw_history.archive=raw_module.Archive()
        raw_history.archive.seed(raw_history.records)
    except Exception as error:
        if raw_history.archive is not None:raw_history.archive.close()
        raw_history.archive=None
        print('Packet archive unavailable: '+str(error),file=sys.stderr,flush=True)
    print('RAM feed ready: '+path+' | restored '+str(len(history))+' packets | raw snapshot on exit', flush=True)
    def drop(c):
        # A signal can interrupt removal after unregister, before clients.pop.
        try: sel.unregister(c)
        except KeyError: pass
        clients.pop(c, None)
        replay_clients.discard(c)
        c.close()
    def publish(line):
        nonlocal latest_status
        sys.stdout.write(line.decode('utf-8', 'replace')); sys.stdout.flush()
        if PACKET.match(line):
            history.append(line)
        else:
            latest_status = line
        for c in list(clients):
            if c in replay_clients: continue
            clients[c].extend(line)
            if len(clients[c]) > 262144:
                drop(c)
            else:
                sel.modify(c, selectors.EVENT_READ | selectors.EVENT_WRITE)
    def stop(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)
    try:
        while True:
            if child is None and time.monotonic() >= retry_at:
                publish(b'Connecting to UV-PRO Bluetooth...\n')
                child = subprocess.Popen([sys.executable, '-u', receiver]+([] if args.proxy else ['--retry']), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
                os.set_blocking(child.stdout.fileno(), False)
                sel.register(child.stdout, selectors.EVENT_READ)
            timeout = max(0, retry_at - time.monotonic()) if child is None else None
            for key, events in sel.select(timeout):
                if key.fileobj is replay_server:
                    c,_=replay_server.accept();c.setblocking(False)
                    clients[c]=bytearray(raw_history.export());replay_clients.add(c)
                    sel.register(c,selectors.EVENT_READ|selectors.EVENT_WRITE)
                elif key.fileobj is server:
                    c, _ = server.accept()
                    c.setblocking(False)
                    clients[c] = bytearray(b''.join(history)+latest_status)
                    sel.register(c, selectors.EVENT_READ | (selectors.EVENT_WRITE if clients[c] else 0))
                elif child is not None and key.fileobj is child.stdout:
                    data = os.read(child.stdout.fileno(), 8192)
                    if not data:
                        sel.unregister(child.stdout)
                        child.stdout.close()
                        child.wait()
                        child = None
                        pending = b''
                        retry_at = time.monotonic() + 10
                        publish(b'Radio disconnected - waiting to reconnect (retry in 10s).\n')
                        continue
                    pending += data
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        line += b'\n'
                        if line.startswith(b'@KISS '):
                            try: raw_history.add(json.loads(line[6:]))
                            except (ValueError,KeyError,TypeError) as exc: publish(('Invalid raw record: '+str(exc)+'\n').encode())
                        else: publish(line)
                else:
                    c = key.fileobj
                    try:
                        if events & selectors.EVENT_READ:
                            if not c.recv(1024):
                                drop(c); continue
                        if events & selectors.EVENT_WRITE and clients[c]:
                            n = c.send(clients[c]); del clients[c][:n]
                            if not clients[c]:
                                if c in replay_clients: drop(c)
                                else: sel.modify(c, selectors.EVENT_READ)
                    except (ConnectionError, OSError):
                        drop(c)
    except KeyboardInterrupt:
        pass
    finally:
        if child is not None:
            if child.poll() is None: child.terminate()
            try: extra=child.communicate(timeout=42 if args.proxy else 3)[0] or b''
            except subprocess.TimeoutExpired:
                child.kill();extra=child.communicate()[0] or b''
            for line in (pending+extra).splitlines():
                if line.startswith(b'@KISS '):
                    try: raw_history.add(json.loads(line[6:]))
                    except (ValueError,KeyError,TypeError): pass
        try:
            raw_history.save()
            if raw_history.archive is not None:raw_history.archive.close()
            print('Saved '+str(len(raw_history.records))+' raw records to '+raw_module.SNAPSHOT,flush=True)
        except OSError as exc:
            print('Snapshot save failed: '+str(exc), file=sys.stderr, flush=True)
        for c in list(clients): drop(c)
        sel.close(); server.close(); replay_server.close(); os.unlink(path); os.unlink(replay_path)


if __name__ == '__main__':
    main()
