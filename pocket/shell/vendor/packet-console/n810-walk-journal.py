"""Buffered private JSONL journal for walk sessions."""
import datetime
import json
import os
import time


class Journal:
    def __init__(self,folder):
        folder.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.path=folder/(datetime.datetime.now().strftime('%Y%m%d-%H%M%S')+'-%d.jsonl'%os.getpid())
        self.fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        self.rows=[];self.due=time.monotonic()+30
    def add(self,kind,**fields):
        self.rows.append(dict(type=kind,time=datetime.datetime.now().astimezone().isoformat(timespec='milliseconds'),**fields))
        if len(self.rows)>=256:self.flush()
    def flush(self):
        if self.rows:
            data=''.join(json.dumps(row,separators=(',',':'))+'\n' for row in self.rows).encode()
            while data:
                n=os.write(self.fd,data)
                if n<=0:raise OSError('Walk log write failed')
                data=data[n:]
            os.fsync(self.fd);self.rows.clear()
        self.due=time.monotonic()+30
    def close(self):
        try:self.flush()
        finally:os.close(self.fd)
