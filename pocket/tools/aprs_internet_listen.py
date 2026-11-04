#!/usr/bin/env python3
"""Explicit receive-only APRS-IS capture, separate from RF observations."""
import argparse
from pathlib import Path
import socket
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from aprs_internet import InternetEvidence,login


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--call',required=True);p.add_argument('--filter',required=True)
    p.add_argument('--server',default='rotate.aprs2.net');p.add_argument('--port',type=int,default=14580)
    p.add_argument('--database',type=Path,default=Path('~/.local/state/pocket/aprs-internet.sqlite3').expanduser())
    a=p.parse_args();hello=login(a.call,a.filter)
    a.database.parent.mkdir(parents=True,exist_ok=True)
    store=InternetEvidence(a.database)
    try:
        with socket.create_connection((a.server,a.port),timeout=30) as sock:
            sock.sendall(hello.encode('ascii'));sock.settimeout(180)
            with sock.makefile('rb') as stream:
                while True:
                    raw=stream.readline(513)
                    if not raw:break
                    if len(raw)>512:raise ValueError('Oversize feed line')
                    try:store.ingest(raw.decode('ascii'))
                    except (ValueError,UnicodeDecodeError):continue
    finally:store.close()


if __name__=='__main__':main()
