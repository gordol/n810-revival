"""Explicit opt-in pause of the hidden desktop only, with independent resume guard.
Not enabled by the graphics launcher. Requires user approval before device use.
"""
from pathlib import Path
import os,select,signal,subprocess,sys,time

def state(pid):
 fields=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
 return fields[0],int(fields[4]),fields[19]

class PausedProcess:
 def __init__(self,pid,timeout=600):
  before=state(pid)
  if before[0] in ('T','t'):raise RuntimeError('Process was already stopped')
  self.fd=os.pidfd_open(pid)
  after=state(pid)
  if after[1:]!=before[1:] or after[0] in ('T','t'):
   os.close(self.fd);raise RuntimeError('Process identity/state changed')
  read_control,self.control=os.pipe();ready,write_ready=os.pipe()
  try:
   self.guard=subprocess.Popen([sys.executable,__file__,'--guard',str(self.fd),str(read_control),str(write_ready),str(timeout)],pass_fds=(self.fd,read_control,write_ready))
  except BaseException:
   os.close(self.control);os.close(ready);os.close(self.fd);raise
  finally:os.close(read_control);os.close(write_ready)
  try:
   if not select.select([ready],[],[],30)[0] or os.read(ready,1)!=b'P':raise RuntimeError('Pause guard did not acknowledge')
  except BaseException:
   os.close(self.control)
   try:self.guard.wait(timeout=35)
   finally:os.close(self.fd)
   raise
  finally:os.close(ready)
 def close(self):
  if self.fd is None:return
  try:
   try:os.write(self.control,b'R')
   except BrokenPipeError:pass
   os.close(self.control)
   try:self.guard.wait(timeout=35)
   except subprocess.TimeoutExpired:
    signal.pidfd_send_signal(self.fd,signal.SIGCONT)
    raise RuntimeError('Desktop resumed; pause guard did not finish')
   if self.guard.returncode:raise RuntimeError('Pause guard reported an error')
  finally:os.close(self.fd);self.fd=None
 def __enter__(self):return self
 def __exit__(self,*unused):self.close()

def pause_desktop(tty):
 if not tty.startswith('tty') or not tty[3:].isdigit():raise ValueError('Console required')
 if Path('/sys/class/tty/tty0/active').read_text().strip()==tty:raise RuntimeError('Desktop is still visible')
 matches=[]
 for p in Path('/proc').glob('[0-9]*'):
  try:
   args=(p/'cmdline').read_bytes().split(b'\0')
   if b'/usr/local/libexec/n810-pocket-session' in args and state(int(p.name))[1]==os.makedev(4,int(tty[3:])):matches.append(int(p.name))
  except (OSError,ValueError):continue
 if len(matches)!=1:raise RuntimeError('Expected one exact desktop owner')
 return PausedProcess(matches[0])

def guard(fd,control,ready,timeout):
 def interrupted(*unused):raise SystemExit(1)
 signal.signal(signal.SIGTERM,interrupted)
 try:
  signal.pidfd_send_signal(fd,signal.SIGSTOP)
  os.write(ready,b'P');os.close(ready)
  if select.select([control],[],[],timeout)[0]:os.read(control,1)
 finally:
  try:signal.pidfd_send_signal(fd,signal.SIGCONT)
  except ProcessLookupError:pass
  os.close(fd);os.close(control)

if __name__=='__main__':
 if len(sys.argv)!=6 or sys.argv[1]!='--guard':raise SystemExit('Internal guard entry only')
 guard(int(sys.argv[2]),int(sys.argv[3]),int(sys.argv[4]),float(sys.argv[5]))
