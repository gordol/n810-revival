#!/usr/bin/env python3
"""On-demand laptop web consoles, managed for the current login by launchd."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import time

ROOT=Path(__file__).resolve().parent
PRIVATE=ROOT/'phone-terminal/.private'
SERVICES={'terminal':('local.n810.phone-terminal','phone-terminal/server.cjs',8443),
          'native':('local.n810.web-console','web-console/server.cjs',8444)}


def run(*args):
    return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)


def listening(host,port):
    try:
        with socket.create_connection((host,port),timeout=.5):return True
    except OSError:return False


def managed(label):
    result=run('/bin/launchctl','list',label)
    return result.returncode==0,result.stdout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('start','stop','status'))
    parser.add_argument('service',nargs='?',choices=(*SERVICES,'all'),default='all')
    args=parser.parse_args()
    config=json.loads((PRIVATE/'config.json').read_text())
    host=config['bind'];node=shutil.which('node')
    failed=False
    for name,(label,script,port) in SERVICES.items():
        if args.service not in (name,'all'):continue
        exists,_=managed(label)
        alive=listening(host,port)
        if args.action=='stop':
            if exists:
                result=run('/bin/launchctl','remove',label)
                if result.returncode:raise SystemExit(result.stderr.strip())
                print(name+': managed service stopped')
            else:print(name+': no managed service; any manually started server was left alone')
            continue
        if args.action=='start' and not alive:
            if not node:raise SystemExit('Node is unavailable in the current PATH')
            if exists:
                result=run('/bin/launchctl','remove',label)
                if result.returncode:raise SystemExit(result.stderr.strip())
            logs=[]
            for suffix in ('out','err'):
                path=PRIVATE/(name+'-service.'+suffix+'.log')
                path.touch(mode=0o600,exist_ok=True);logs.append(str(path))
            result=run('/bin/launchctl','submit','-l',label,'-o',logs[0],'-e',logs[1],
                       '--',node,str(ROOT/script))
            if result.returncode:raise SystemExit(result.stderr.strip())
            for _ in range(20):
                if listening(host,port):break
                time.sleep(.15)
            alive=listening(host,port);exists,_=managed(label)
        state='listening (managed)' if alive and exists else 'listening (external process)' if alive else 'stopped'
        print(f'{name}: {state} — https://{host}:{port}')
        if not alive:failed=True
    return int(failed)


if __name__=='__main__':raise SystemExit(main())
