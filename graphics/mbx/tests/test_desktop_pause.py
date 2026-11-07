"""Linux-only tests use our own sleep children, never a desktop/device."""
from pathlib import Path
import subprocess,sys,time,os,signal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'mesa'))
from desktop_pause import PausedProcess,state
p=subprocess.Popen(['sleep','60'])
def resumed():
 for _ in range(100):
  if state(p.pid)[0] not in ('T','t'):return
  time.sleep(.02)
 raise AssertionError('Child did not resume')
try:
 with PausedProcess(p.pid):
  time.sleep(.05);assert state(p.pid)[0]=='T'
 resumed()
 with PausedProcess(p.pid,timeout=.2):
  time.sleep(.3);resumed()
 os.kill(p.pid,signal.SIGSTOP);time.sleep(.05)
 try:PausedProcess(p.pid);raise AssertionError('Already-stopped child accepted')
 except RuntimeError:pass
 assert state(p.pid)[0]=='T';os.kill(p.pid,signal.SIGCONT);resumed()
 code='import sys,time;sys.path.insert(0,sys.argv[1]);from desktop_pause import PausedProcess;p=PausedProcess(int(sys.argv[2]));print("PAUSED",flush=True);time.sleep(60)'
 parent=subprocess.Popen([sys.executable,'-c',code,sys.path[0],str(p.pid)],stdout=subprocess.PIPE,text=True)
 assert parent.stdout.readline().strip()=='PAUSED';assert state(p.pid)[0]=='T'
 parent.kill();parent.wait(timeout=5);resumed()
 print('PASS normal release, timeout, already-stopped refusal, and automatic resume after controller SIGKILL')
finally:os.kill(p.pid,signal.SIGCONT);p.terminate();p.wait(timeout=5)
