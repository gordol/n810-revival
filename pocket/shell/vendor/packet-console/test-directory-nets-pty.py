#!/usr/bin/env python3
"""Mac/Linux PTY acceptance for unchanged Directory/Nets in private REPLAY."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import time
import unittest

HERE=Path(__file__).resolve().parent
STAMP='2020-01-02T03:04:05.000+00:00'

def address(call,last=False):return bytes(ord(c)<<1 for c in call.ljust(6))+bytes([0x60|last])
FRAME=(b'\0'+address('APRS')+address('TEST',True)+b'\x03\xf0>Net Mon 19:30 146.820MHz').hex()

class LegacyReplayPTY(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='np-',dir='/tmp');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'r';self.home=self.root/'home'
        self.env=dict(os.environ,TERM='xterm-256color',HOME=str(self.home))
        for k in ('TMUX','TMUX_PANE'):self.env.pop(k,None)
        live=Path(self.temp.name)/'live.json';catalog=Path(self.temp.name)/'catalog.json'
        live.write_text(json.dumps(dict(captured='2020-01-02T04:00:00+00:00',packets=[dict(time=STAMP,direction='radio_to_host',frame=FRAME)])))
        catalog.write_text(json.dumps(dict(stations=[dict(call='TEST',first=STAMP,last=STAMP,packets=1)],evidence=[],via=[])))
        self.server=subprocess.Popen([sys.executable,str(HERE/'dev-env.py'),'serve','--root',str(self.root),'--live',str(live),'--catalog',str(catalog)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=self.env)
        self.addCleanup(self.stop_server)
        ready=select.select([self.server.stdout,self.server.stderr],[],[],10)[0]
        self.assertTrue(ready,'feed startup timeout')
        if self.server.stdout not in ready:self.fail(self.server.stderr.readline().decode())
        self.meta=json.loads(self.server.stdout.readline())
        self.contract=json.loads((HERE/'contracts/directory-nets-pty.json').read_text())
    def stop_server(self):
        self.server.terminate()
        try:self.server.communicate(timeout=4)
        except subprocess.TimeoutExpired:self.server.kill();self.server.communicate()
    def expand(self,argv):
        values=dict(python=sys.executable,repo=str(HERE),root=str(self.root))
        return [s.format(**values) for s in argv]
    def app(self,name):return next(a for a in self.contract['apps'] if a['id']==name)
    def read_until(self,fd,token,timeout=12):
        data=b'';deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if select.select([fd],[],[],.1)[0]:
                try:part=os.read(fd,65536)
                except OSError:break
                if not part:break
                data+=part
                if token in data:return data
        self.fail('PTY missing '+repr(token)+'; tail='+repr(data[-1500:]))
    def exercise(self,name,title):
        master,slave=pty.openpty()
        fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',40,133,0,0))
        child=subprocess.Popen(self.expand(self.app(name)['argv']),stdin=slave,stdout=slave,stderr=slave,cwd=HERE,env=self.env,start_new_session=True)
        os.close(slave)
        try:
            output=self.read_until(master,title)
            if name=='directory':
                output+=self.read_until(master,b'TEST') if b'TEST' not in output else b''
            else:
                os.write(master,b'h');output+=self.read_until(master,b'TEST')
            self.assertNotIn(b'Traceback',output)
            fcntl.ioctl(master,termios.TIOCSWINSZ,struct.pack('HHHH',24,80,0,0));os.killpg(child.pid,signal.SIGWINCH)
            os.write(master,b'jku' if name=='nets' else b'jk')
            time.sleep(.15);os.write(master,b'q')
            deadline=time.monotonic()+8
            while child.poll() is None and time.monotonic()<deadline:
                if select.select([master],[],[],.1)[0]:
                    try:output+=os.read(master,65536)
                    except OSError:break
            child.wait(timeout=2)
            self.assertNotIn(b'Traceback',output)
            self.assertEqual(child.returncode,0)
        finally:
            if child.poll() is None:os.killpg(child.pid,signal.SIGKILL);child.wait()
            os.close(master)
    def test_directory_launch_and_resize(self):self.exercise('directory',b'STATIONS')
    def test_nets_launch_requires_seed_and_keeps_reminders_off(self):
        target=self.home/'.local/share/n810-radio/nets.json'
        self.assertFalse(target.exists(),'prepare unexpectedly seeded schedules')
        subprocess.run(self.expand(self.app('nets')['prepare']['argv']),env=self.env,check=True,capture_output=True)
        self.exercise('nets',b'NETS')
        state=json.loads((self.home/'.local/state/n810-aprs/nets-state.json').read_text())
        self.assertEqual((state['lead'],state['enabled']),(0,[]))
        self.assertTrue(any(r['call']=='TEST' for r in state['heard']))
    def test_existing_generic_terminal_adapter(self):
        runtime=HERE.parent/'explorations/current-world'
        if not (runtime/'terminal_host.py').exists():self.skipTest('sibling DSL runtime unavailable')
        sys.path.insert(0,str(runtime))
        from core import Host,Window
        from terminal_host import Terminal
        import selectors
        for name,title in [('directory','STATIONS'),('nets','NETS')]:
            if name=='nets':subprocess.run(self.expand(self.app(name)['prepare']['argv']),env=self.env,check=True,capture_output=True)
            host=Host(140,46,[Window(name,0,0,135,42)],animate=False)
            selector=selectors.DefaultSelector()
            terminal=Terminal(host,name,self.expand(self.app(name)['argv']),selector,
                              env=dict(self.env,TMUX='',TMUX_PANE=''),cwd=str(HERE))
            def pump_until(text=None,exited=False):
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    for key,mask in selector.select(.03):key.data.ready(mask)
                    host.flush(1000000)
                    display='\n'.join(terminal.screen.display)
                    self.assertNotIn('Traceback',display)
                    if text and text in display:return
                    if exited and terminal.child.poll() is not None:return
                self.fail('runtime PTY timeout: '+display)
            try:
                pump_until(title);pump_until('TEST' if name=='directory' else 'NEXT SEVEN DAYS')
                host.windows[0].w=82;host.windows[0].h=26;terminal.resize()
                terminal.key('h' if name=='nets' else 'j');pump_until('TEST')
                self.assertEqual(terminal.size,(80,24))
                terminal.key('q');pump_until(exited=True)
                self.assertEqual(terminal.child.returncode,0)
            finally:terminal.close();selector.close()

    def test_snapshot_and_environment_provenance_are_original(self):
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.connect(str(self.root/'replay.sock'));s.settimeout(2);data=b''
            while True:
                part=s.recv(65536)
                if not part:break
                data+=part
        header,row=[json.loads(x) for x in data.splitlines()]
        self.assertTrue(header['replay']);self.assertEqual(row['time'],STAMP)
        self.assertNotEqual(header['fixture_captured'],row['time'])
        self.assertEqual(row['direction'],'radio_to_host');self.assertEqual(row['frame'],FRAME)
        self.assertEqual(self.meta['mode'],'REPLAY');self.assertFalse(self.meta['transmit'])
        self.assertFalse((self.root/'kiss.sock').exists())

if __name__=='__main__':unittest.main()
