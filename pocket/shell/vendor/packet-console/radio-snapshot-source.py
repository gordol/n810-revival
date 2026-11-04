#!/usr/bin/env python3
"""Mirror the existing cached read-only local API into a private Pocket snapshot."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import signal
import ssl
import tempfile
import time
import urllib.parse
import urllib.request


def observed(stamp):
    try:return datetime.datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()
    except (AttributeError,ValueError):return None


def save(path,payload):
    data=json.dumps(payload,separators=(',',':')).encode()+b'\n'
    if path.exists() and path.read_bytes()==data:return False
    fd,name=tempfile.mkstemp(prefix='.radio-',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:stream.write(data)
        os.replace(name,path)
    finally:
        Path(name).unlink(missing_ok=True)
    return True


def load_retained(path):
    """Seed from existing observations so an initial outage cannot erase them."""
    try:
        if path.stat().st_size>20*1024*1024:return {}
        value=json.loads(path.read_text())
        if not isinstance(value,dict):return {}
        return {key:value[key] for key in ('catalog','live','connector') if isinstance(value.get(key),dict)}
    except (OSError,ValueError):return {}


def acquire(output,access):
    """Hold one OS lock per output; reuse only an identical access-file identity."""
    output=output.expanduser().resolve();access=access.expanduser().resolve()
    path=output.with_name(output.name+'.producer.lock')
    fd=os.open(path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    handle=os.fdopen(fd,'r+')
    info=os.fstat(handle.fileno())
    if info.st_uid!=os.getuid() or info.st_mode&0o077:
        handle.close();raise ValueError('Producer lock must be private and owned by this user')
    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        try:owner=json.loads(handle.read(4096))
        except ValueError:handle.close();raise ValueError('Producer ownership is initializing; retry shortly') from None
        handle.close()
        if owner.get('output')!=str(output) or owner.get('access')!=str(access):
            raise ValueError('Output already owned by a different API access configuration')
        return None
    handle.seek(0);handle.truncate()
    json.dump(dict(version=1,pid=os.getpid(),output=str(output),access=str(access)),handle)
    handle.flush()
    return handle


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--access',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--watch',action='store_true')
    args=parser.parse_args();access=args.access.expanduser().resolve();output=args.output.expanduser().resolve()
    if access.stat().st_uid!=os.getuid() or access.stat().st_mode&0o077:parser.error('API access file must be private and owned by this user')
    output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if output.parent.stat().st_uid!=os.getuid() or output.parent.stat().st_mode&0o077:parser.error('output directory must be private and owned by this user')
    try:owner=acquire(output,access)
    except ValueError as exc:parser.error(str(exc))
    if owner is None:
        print(json.dumps({'producer':'reused'}),flush=True);return 0
    config=json.loads(access.read_text());origin=config['origin'].rstrip('/')
    if urllib.parse.urlsplit(origin).scheme!='https':parser.error('API origin must use HTTPS')
    context=ssl.create_default_context(cafile=config['certificate'])
    payload=load_retained(output);due={'catalog':0.,'live':0.};stopped=False
    print(json.dumps({'producer':'started'}),flush=True)
    def stop(*_):
        nonlocal stopped
        stopped=True
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
    while not stopped:
        for kind in ('catalog','live'):
            if stopped:break
            if time.monotonic()<due[kind]:continue
            request=urllib.request.Request(origin+'/api/'+kind,headers={'Cookie':config['cookie']})
            try:
                with urllib.request.urlopen(request,context=context,timeout=20) as response:
                    raw=response.read(8*1024*1024+1)
                    if len(raw)>8*1024*1024:raise ValueError('API response too large')
                value=json.loads(raw)
                if not isinstance(value,dict) or not isinstance(value.get('data'),dict):raise ValueError('API snapshot unavailable')
                payload[kind]=value
                if kind=='live':
                    stamp=observed(value.get('fetched'))
                    if stamp is not None:
                        payload['connector']={'ssh':{'success':value.get('error') is None,'observed_at':stamp}}
            except (OSError,ValueError):
                # An HTTP failure does not prove that the remote SSH link failed.
                retained=dict(payload.get(kind,{}));retained['error']='Local radio API unavailable; retained observations may be stale.';payload[kind]=retained
            due[kind]=time.monotonic()+(90 if kind=='catalog' else 5)
        save(output,payload)
        if not args.watch:break
        time.sleep(min(1,max(0,min(due.values())-time.monotonic())))
    owner.close()
    return 0


if __name__=='__main__':raise SystemExit(main())
