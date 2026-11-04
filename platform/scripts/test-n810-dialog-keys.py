import os,pty,fcntl,termios,struct,subprocess,select,time

def dialog(args, keys):
 master,slave=pty.openpty()
 fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',24,80,0,0))
 child=subprocess.Popen(['whiptail']+list(map(str,args)),stdin=slave,stdout=slave,stderr=slave,env=dict(os.environ,TERM='linux'))
 os.close(slave)
 try:
  deadline=time.monotonic()+2
  while time.monotonic()<deadline:
   if select.select([master],[],[],.1)[0]:
    os.read(master,65536)
    break
  time.sleep(.2)
  os.write(master,keys)
  deadline=time.monotonic()+3
  while child.poll() is None and time.monotonic()<deadline:
   if select.select([master],[],[],.1)[0]:
    try: os.read(master,65536)
    except OSError: break
  return child.wait(timeout=2)
 finally:
  if child.poll() is None: child.kill(); child.wait()
  os.close(master)
assert dialog(['--defaultno','--yes-button','Shut down','--no-button','Keep running','--yesno','Confirm',10,60],b'\r')==1
assert dialog(['--defaultno','--yesno','Confirm',10,60],b'\x1b[D\r')==0
assert dialog(['--default-item','back','--menu','Power',14,60,2,'topoff','Top off','back','Return'],b'\r')==0
print('PASS: real whiptail Center defaults to keep running; Left/Center confirms; menu accepts Center')
