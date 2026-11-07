"""Exercise reader instructions against a real make-launched desktop in a PTY."""
import argparse,fcntl,os,pty,select,signal,struct,subprocess,sys,tempfile,termios,time,json,hashlib
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('root',type=Path,nargs='?',default=Path(__file__).resolve().parents[2]/'pocket');args=parser.parse_args();root=args.root.resolve()
sys.path.insert(0,str(root/'shell/vendor/terminal'))
import pyte
out=Path(tempfile.mkdtemp(prefix='pocket-instructions-'));env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ};env.update(TERM='xterm-256color',COLORTERM='truecolor',XDG_STATE_HOME=str(out/'state'),XDG_CONFIG_HOME=str(out/'config'),XDG_CACHE_HOME=str(out/'cache'),PYTHONDONTWRITEBYTECODE='1')
(out/'sources.json').write_text(json.dumps({str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'shell/desktop.py',root/'shell/help_browser.py',root/'shell/on_device_manual/browser.py',root/'shell/native_navigation.py')},indent=2)+'\n')
keys={'tab':b'\t','backtab':b'\x1b[Z','enter':b'\r','esc':b'\x1b','up':b'\x1b[A','down':b'\x1b[B','left':b'\x1b[D','right':b'\x1b[C','pageup':b'\x1b[5~','pagedown':b'\x1b[6~','home':b'\x1b[H','end':b'\x1b[F','f6':b'\x1b[17~','shift-f6':b'\x1b[17;2~','wm':b'\x1d','find':b'\x06','split':b'\x12','backspace':b'\x7f'}
class Desktop:
 def __init__(self):
  self.m,s=pty.openpty();fcntl.ioctl(s,termios.TIOCSWINSZ,struct.pack('HHHH',40,140,0,0));self.screen=pyte.Screen(140,40);self.stream=pyte.ByteStream(self.screen);self.p=subprocess.Popen(['make'],cwd=root,env=env,stdin=s,stdout=s,stderr=s,start_new_session=True);os.close(s);self.n=0;self.drain(1.3)
 def drain(self,delay=.35):
  end=time.monotonic()+delay
  while time.monotonic()<end:
   if select.select([self.m],[],[],.02)[0]:
    try:data=os.read(self.m,1048576)
    except OSError:break
    self.stream.feed(data)
  return '\n'.join(self.screen.display)
 def step(self,label,key=None,expect=None):
  if key:os.write(self.m,keys.get(key,key.encode()))
  text=self.drain();self.n+=1;(out/f'{self.n:03}-{label}.txt').write_text(text)
  assert 'Traceback' not in text,(label,'crash')
  if expect:assert expect in text,(label,'missing',expect)
  print('CHECKED' if expect else 'CAPTURED',label,flush=True);return text
 def menu(self,name):
  self.step('window-commands','wm');self.step('application-menu',',');self.step('find-'+name,name);return self.step('open-'+name,'enter',name)
 def close(self):
  if self.p.poll() is None:os.killpg(self.p.pid,signal.SIGTERM)

  try:self.p.wait(timeout=2)
  except subprocess.TimeoutExpired:os.killpg(self.p.pid,signal.SIGKILL);self.p.wait()
  os.close(self.m)
d=Desktop()
try:
 d.step('first-launch',expect='● Connections')
 d.menu('Help');d.step('help-reading',expect='Reading ·')
 d.step('first-tab','tab','Topics ·');d.step('back-to-reading','backtab','Reading ·')
 d.step('topics-back','esc','Topics ·');d.step('application-list','esc','Applications')
 d.step('first-application','home');d.step('desktop-topics','enter','Using Help');d.step('read-topic-with-tab','tab','Reading ·')
 d.step('scroll-down','down','2–');d.step('scroll-up','up','1–');d.step('scroll-j','j','2–');d.step('scroll-k','k','1–')
 page=d.step('page-down','pagedown');assert '1–21 /' not in page
 d.step('page-up','pageup','1–');end=d.step('end-text','end');assert '1–21 /' not in end
 d.step('home-text','home','1–')
 d.step('topic-pane','tab','Topics ·');d.step('next-topic','down','HELP 1/3');d.step('previous-topic','up','> Using Help');d.step('topic-j','j');d.step('topic-k','k','> Using Help');d.step('last-topic','end');d.step('first-topic','home','> Using Help');d.step('list-page-down','pagedown');d.step('list-page-up','pageup');d.step('list-first-again','home','> Using Help')
 d.step('list-search','/');d.step('list-query','Using','Using');d.step('accept-list-query','enter');d.step('clear-list-query','esc')
 d.step('read-topic','enter','Reading ·');d.step('left-to-topics','left','Topics ·');d.step('right-to-reading','right','Reading ·');d.step('manual-search','find','Search:');d.step('manual-query','pairing','Search: pairing');d.step('delete-query-char','backspace','Search: pairin')
 d.step('restore-query-char','g','Search: pairing');d.step('tab-to-results','tab','Topics ·');d.step('open-result','enter','Reading ·')
 d.step('follow-reference','1','All applications / Reticulum');d.step('reference-back','backspace','All applications / Devices')
 d.step('search-for-cancel','find');d.step('cancel-query','badword');d.step('cancel-search','esc')
 before=d.step('split-start','split','Left/Right resize');after=d.step('split-right','right');assert before.splitlines()[5]!=after.splitlines()[5]
 cancelled=d.step('split-cancel','esc');assert before.splitlines()[5]==cancelled.splitlines()[5]
 d.step('split-again','split','Left/Right resize');d.step('split-left','left');d.step('split-save','enter')
 d.step('back-to-topics','esc');d.step('back-to-applications','esc');d.step('close-help','esc');assert '● Help' not in d.drain()
 d.menu('Help')
 fcntl.ioctl(d.m,termios.TIOCSWINSZ,struct.pack('HHHH',22,50,0,0));d.screen.resize(lines=22,columns=50);os.killpg(d.p.pid,signal.SIGWINCH)
 d.step('narrow-reading',expect='Reading')
 d.step('narrow-topics','tab','[Topics]');d.step('narrow-reading-again','tab','[Reading]')
 fcntl.ioctl(d.m,termios.TIOCSWINSZ,struct.pack('HHHH',40,140,0,0));d.screen.resize(lines=40,columns=140);os.killpg(d.p.pid,signal.SIGWINCH);d.drain()
 d.menu('Calendar');d.step('calendar-focus',expect='● Calen');d.step('next-window','f6');d.step('previous-window','shift-f6','● Calen')
 before_move=d.step('wm-move','wm');d.step('start-move','m');d.step('move-right','right');d.step('move-down','down');moved=d.step('save-move','enter');assert before_move.splitlines()[2]!=moved.splitlines()[2]
 d.step('start-resize','r');d.step('resize-right','right');sized=d.step('save-resize','enter');d.step('maximize','Z');restored=d.step('restore','Z');assert sized.splitlines()[1:]==restored.splitlines()[1:]
 d.step('desktop-two','2','2*');d.step('desktop-one','1','1*');d.step('return-app','f6')
 d.menu('Settings');d.step('settings-tab','tab');d.step('settings-down','down');d.step('settings-enter','enter')
 d.step('overview-wm','wm');d.step('overview','d');d.step('preview-tab','tab');d.step('activate-preview','enter')
 d.step('effects-wm','wm');d.step('send-calendar','@');d.step('show-desktop-two','2','2*');d.step('pin-window','p');d.step('unpin-window','p');d.step('roll-window','o');d.step('unroll-window','o')
 d.step('next-desktop',']','3*');d.step('previous-desktop','[','2*')
 d.step('carry-next','}','3*');d.step('carry-previous','{','2*')
 d.step('background-toggle','b');d.step('background-restore','b');d.step('next-effect','e');d.step('palette','c');d.step('weather','w');d.step('tint','x');d.step('animate','a');d.step('move-style','M');d.step('resize-style','R')
 d.step('quit','q');d.p.wait(timeout=5);assert d.p.returncode==0
 print('PASS clean quit',flush=True)
 d.close();d=Desktop();d.step('restart-saved-session',expect='● Calendar');d.step('restart-quit-wm','wm');d.step('restart-desktop-one','1','Help');d.step('restart-quit','q');d.p.wait(timeout=5);assert d.p.returncode==0
finally:d.close();print('Evidence:',out,flush=True)
