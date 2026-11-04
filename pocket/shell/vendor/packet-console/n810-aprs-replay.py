#!/usr/bin/env python3
"""Export/decode bounded raw history offline. Never opens Bluetooth or a TX socket."""
import argparse
import datetime
import importlib.util
import json
from pathlib import Path
import socket
import sys


def load(name,filename):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source=parser.add_mutually_exclusive_group()
    source.add_argument('--file',help='Saved raw-frames.json snapshot')
    source.add_argument('--socket',default='/dev/shm/n810-aprs-replay.sock')
    parser.add_argument('--format',choices=('json','decoded','kiss'),default='decoded')
    parser.add_argument('--include-tx',action='store_true',help='Include completed host-to-radio writes; default RX only')
    args=parser.parse_args()
    history=load('history','n810-frame-history.py')
    if args.file:
        records=history.History.load(args.file).records
    else:
        c=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);c.settimeout(5)
        try:
            c.connect(args.socket)
            with c.makefile('rb') as f:
                header=json.loads(f.readline())
                if header.get('type')!='snapshot' or header.get('version')!=1:raise ValueError('Invalid replay header')
                records=[history.validate(json.loads(f.readline())) for _ in range(header['records'])]
        finally:c.close()
    monitor=load('monitor','n810-packet-monitor.py')
    bridge=load('bridge','n810-kiss-bridge.py')
    for row in records:
        if row['direction']!='radio_to_host' and not args.include_tx:continue
        frame=bytes.fromhex(row['frame'])
        if args.format=='json':print(json.dumps(row))
        elif args.format=='kiss':sys.stdout.buffer.write(bridge.encode(frame))
        else:
            text=monitor.describe(frame)
            if text:
                stamp=datetime.datetime.fromisoformat(row['time']).strftime('%H:%M:%S')
                print(stamp,text)


if __name__=='__main__':main()
