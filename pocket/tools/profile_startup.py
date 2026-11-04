#!/usr/bin/env python3
"""Measure a real shell frame and input response in an isolated 100x30 PTY."""
import argparse
import fcntl
import os
from pathlib import Path
import pty
import select
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from runtime_codec import frame,pack,unpack,HEADER

FIRST_OUTPUT_PROBE='''import os,sys,time,struct
receipt,script=sys.argv[1:3];sys.argv=sys.argv[2:]
sys.path.insert(0,os.path.dirname(script))
class Output:
    def __init__(self,target):self.target=target;self.done=False;self.frame=False
    def __getattr__(self,name):return getattr(self.target,name)
    def write(self,value):
        if MARKER in value:self.frame=True
        return self.target.write(value)
    def flush(self):
        self.target.flush()
        if self.frame and not self.done:
            self.done=True
            value=struct.pack('!dd',time.monotonic(),time.process_time())
            with open(receipt+'.tmp','wb') as stream:stream.write(value)
            os.replace(receipt+'.tmp',receipt)
sys.stdout=Output(sys.stdout)
with open(script,'rb') as source:code=compile(source.read(),script,'exec')
exec(code,dict(__name__='__main__',__file__=script))
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--shell',type=Path,default=Path(__file__).resolve().parents[1]/'shell')
    parser.add_argument('--native',type=Path)
    parser.add_argument('--report',type=Path,help='optional complete binary MessagePack report')
    parser.add_argument('--profile',type=Path,help='optional cProfile output; timings include instrumentation')
    parser.add_argument('--timeout',type=float,default=90)
    parser.add_argument('--no-metrics',action='store_true',help='avoid renderer diagnostics when profiling normal startup')
    parser.add_argument('--launcher',action='store_true',help='use the same launch.py entry as make n810')
    parser.add_argument('--saved-session',type=Path,help='read a copy of this desktop without changing it')
    parser.add_argument('--local-services',action='store_true',help='attach existing local services after the first frame')
    parser.add_argument('--sample-seconds',type=float,default=0,help='observe the running desktop after first input')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='pocket-start-',dir='/tmp') as temporary:
        state=Path(temporary);master,slave=pty.openpty()
        if args.saved_session:
            (state/'session').write_bytes(args.saved_session.read_bytes())
            if args.local_services:
                for name in ('reticulum-owner.msgpack','reticulum-owner.json','meshcore-owner.toml'):
                    source=args.saved_session.parent/name
                    if source.is_file():
                        target=state/name;target.write_bytes(source.read_bytes());target.chmod(0o600)
        fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,100,0,0))
        command=[sys.executable,str(args.shell/'demo.py'),'--shell','--no-save','--no-local-services','--session',str(state/'session'),'--app-state',str(state),'--control-socket',str(state/'ui.sock'),'--metrics',str(state/'metrics.msgpack')]
        if args.launcher:command[1:2]=[str(args.shell/'launch.py'),'--state',str(state)]
        if args.local_services:command.remove('--no-local-services')
        if args.no_metrics:
            index=command.index('--metrics');del command[index:index+2]
        if args.native:command+=['--native',str(args.native)]
        marker='\x1b[?2026l' if args.saved_session else '[*Device]'
        if args.profile:command[1:1]=['-m','cProfile','-o',str(args.profile)]
        else:
            probe=FIRST_OUTPUT_PROBE.replace('MARKER',repr(marker))
            command[1:1]=['-c',probe,str(state/'first-output.bin')]
        began=time.monotonic();child=subprocess.Popen(command,stdin=slave,stdout=slave,stderr=slave,env={**os.environ,'TERM':'xterm-256color'})
        os.close(slave);raw=bytearray();report={}
        def pump():
            if select.select([master],[],[],.01)[0]:
                try:raw.extend(os.read(master,65536))
                except OSError:pass
            if len(raw)>262144:del raw[:-131072]
            if child.poll() is not None:raise RuntimeError(bytes(raw[-3000:]).decode(errors='replace'))
            if time.monotonic()-began>args.timeout:raise TimeoutError(bytes(raw[-3000:]).decode(errors='replace'))
        try:
            while marker.encode() not in raw:pump()
            report['first_frame_seconds']=time.monotonic()-began
            if not args.profile:
                while not (state/'first-output.bin').exists():pump()
                # The child records this at flush, before starting services;
                # reading /proc after delivery can include those later imports.
                stamp,cpu=struct.unpack('!dd',(state/'first-output.bin').read_bytes())
                measured=dict(monotonic=stamp,cpu_seconds=cpu)
                report['child_first_frame_seconds']=measured['monotonic']-began
                report['child_first_frame_cpu_seconds']=measured['cpu_seconds']
            if sys.platform=='linux':
                # Read the child directly: starting a status helper here changes
                # the first-input measurement on a slow single-core device.
                fields=Path('/proc',str(child.pid),'stat').read_text().rsplit(')',1)[1].split()
                report['first_frame_process']={
                    'cpu_seconds':(int(fields[11])+int(fields[12]))/os.sysconf('SC_CLK_TCK'),
                    'minor_faults':int(fields[7]),'major_faults':int(fields[9])}
            with socket.socket(socket.AF_UNIX) as client:
                client.connect(str(state/'ui.sock'));client.sendall(frame({'activate':'System'}));client.setblocking(False)
                requested=time.monotonic()
                while not select.select([client],[],[],0)[0]:pump()
                response=unpack(client.recv(65536)[HEADER:]);assert response['ok'],response
                report['input_response_seconds']=time.monotonic()-requested
            if args.sample_seconds:
                until=time.monotonic()+args.sample_seconds
                while time.monotonic()<until:pump()
            os.write(master,b'\x1dq')
            while child.poll() is None:
                if select.select([master],[],[],.05)[0]:
                    try:os.read(master,65536)
                    except OSError:pass
                if time.monotonic()-began>args.timeout:raise TimeoutError('quit')
            assert child.returncode==0,child.returncode
            if not args.no_metrics:
                measured=unpack((state/'metrics.msgpack').read_bytes())
                report['metrics']=measured['renderer']['startup']
                if args.sample_seconds:
                    report['model_work']=measured['model_work'];report['phases']=measured['phases']
            if args.report:args.report.write_bytes(pack(report))
            for name in ('first_frame_seconds','child_first_frame_cpu_seconds','input_response_seconds'):
                if name in report:print(name+'\t'+str(report[name]))
        finally:
            if child.poll() is None:child.terminate();child.wait(timeout=10)
            os.close(master)

if __name__=='__main__':main()
