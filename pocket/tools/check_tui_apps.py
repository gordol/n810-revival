# SPDX-License-Identifier: GPL-2.0-or-later
"""Local TUI launch/close smoke test; not radio, data or gameplay acceptance.

Run python3 pocket/tools/check_tui_apps.py from a source checkout.
Uses temporary state and a terminal emulator; never contacts a tablet.
"""
import os,sys,pty,fcntl,termios,struct,subprocess,socket,time,json,select,tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'pocket/shell'))
from runtime_codec import frame,frame_size,unpack,HEADER
sys.path.insert(0,str(root/'pocket/shell/vendor/terminal'));import pyte
screen=pyte.Screen(100,30);stream=pyte.ByteStream(screen)
with tempfile.TemporaryDirectory(prefix='pocket-tui-') as folder:
 p=Path(folder);master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',30,100,0,0))
 env=dict(os.environ,HOME=folder,XDG_STATE_HOME=folder,TERM='xterm-256color')
 child=subprocess.Popen([sys.executable,str(root/'pocket/shell/desktop.py'),'--shell','--native-stations','--station-db',str(p/'stations.sqlite3'),'--no-local-services','--no-save','--control-socket',str(p/'desktop.sock')],env=env,stdin=slave,stdout=slave,stderr=slave);os.close(slave)
 def drain(seconds):
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   if select.select([master],[],[],.02)[0]:
    try:stream.feed(os.read(master,65536))
    except OSError:break
 def req(q):
  with socket.socket(socket.AF_UNIX) as s:
   s.settimeout(5);s.connect(str(p/'desktop.sock'));s.sendall(frame(q));data=b''
   while True:
    data+=s.recv(8192);n=frame_size(data,8192)
    if n is not None and len(data)>=n:return unpack(data[HEADER:],8192)
 try:
  drain(2)
  for name in ['Settings','Help','Station Map','Offline Data','Messages','Services','Nets','APRS Walk Logs','CW','N810 Setup','ULS Lookup','Radio Feed','Heard','Connections','Stations','Audio Monitor','Radio Manager','Radio','System','Bluetooth','Symbian','Touch lab','Wildlife','Rainier walk','Surface room']:
   activation=req({'activate':name});assert activation.get('ok'),(name,activation)
   drain(.25);result={'ok':'Find:' in '\n'.join(screen.display),'opened':True} if name=='Settings' else req({'command':'app-status','name':name})
   assert result.get('ok') and not result.get('error'),(name,result)
   print(json.dumps({'app':name,'opened':result.get('opened'),'error':result.get('error')}),flush=True)
   os.write(master,b'\x1dX');drain(.2)
   if name!='Settings':assert not req({'command':'app-status','name':name}).get('opened'),name
  assert child.poll() is None
  print(json.dumps({'result':'PASS','scope':'25 TUI views opened and closed; external services not exercised'}),flush=True)
 finally:
  if child.poll() is None:
   try:os.write(master,b'\x1dq');drain(.3)
   except OSError:pass
  if child.poll() is None:child.terminate()

  try:child.wait(timeout=5)
  except subprocess.TimeoutExpired:child.kill();child.wait()
  os.close(master)
