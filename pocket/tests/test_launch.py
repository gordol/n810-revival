"""Exercise make n810 and real input/rendering in an isolated terminal."""
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'shell/vendor/terminal'))
sys.path.insert(0,str(ROOT/"shell"))
from runtime_codec import frame,unpack,HEADER
import pyte
from test_connections import ReceiveOwner


class LaunchTests(unittest.TestCase):
    def test_make_shell_first_then_socket_attach_and_detach(self):
        with tempfile.TemporaryDirectory(prefix='pocket-ui-', dir='/tmp') as temporary:
            folder = Path(temporary)
            management = folder/'reticulum.sock'
            station = subprocess.Popen([sys.executable, str(ROOT/'shell/vendor/apps/domains/reticulum/owner.py'), '--socket', str(management), '--state', str(folder/'reticulum'), '--station', 'fixture'], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            def stop_station():
                if station.poll() is None: station.terminate()
                station.wait(timeout=5)
                station.stderr.close()
            self.addCleanup(stop_station)
            deadline=time.monotonic()+5
            while not management.exists() and station.poll() is None and time.monotonic()<deadline: time.sleep(.01)
            self.assertTrue(management.exists())
            owner = ReceiveOwner(folder/'owner')
            self.addCleanup(owner.close)
            master, slave = pty.openpty()
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 32, 100, 0, 0))
            env = {key:value for key,value in os.environ.items() if not key.startswith(('N810_', 'CURRENT_WORLD_', 'PYTHON', 'XDG_'))}
            env.update(HOME=str(folder), XDG_STATE_HOME=str(folder/'state'), TERM='xterm-256color', SHELL='/bin/sh', ENV='', BASH_ENV='')
            started = time.monotonic()
            child = subprocess.Popen(['make', 'n810', 'PYTHON='+sys.executable, 'EXTRA=--control-socket '+str(folder/'desktop.sock')], cwd=ROOT,
                                     env=env, stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
            os.close(slave)
            screen = pyte.Screen(100,32); stream = pyte.ByteStream(screen); chunks = []
            def text(): return '\n'.join(screen.display)
            def wait(predicate, description):
                end = time.monotonic()+10
                while time.monotonic()<end:
                    if select.select([master],[],[],.02)[0]:
                        try: raw = os.read(master,65536)
                        except OSError: raw = b''
                        if raw: chunks.append(raw); stream.feed(raw)
                    if predicate(): return
                    if child.poll() is not None: break
                self.fail(description+'\n'+text()+'\n'+b''.join(chunks)[-1000:].decode(errors='replace'))
            try:
                wait(lambda: '[S Socket folder]' in text() and 'Local services' in text(), 'offline shell did not open')
                first_frame = time.monotonic()-started
                self.assertEqual(owner.clients, [])
                os.write(master, ('e'+str(owner.root)+'\rs').encode())
                wait(lambda: 'Attached' in text(), 'explicit socket connection did not appear')
                wait(lambda:len(owner.clients)==1,'receive owner did not accept the attached client')
                os.write(master,b'\x1b[Z\x1b[C')
                wait(lambda:'[*Reticulum]' in text(), 'independent Reticulum selector absent')
                self.assertEqual(len(owner.clients),1)
                os.write(master,('e'+str(management)+'\rs').encode())
                wait(lambda:'Attached' in text(), 'Reticulum owner did not attach through normal UI')
                def activate(title,expected=True):
                    with socket.socket(socket.AF_UNIX) as client:
                        client.settimeout(3);client.connect(str(folder/'desktop.sock'))
                        client.sendall(frame(dict(activate=title)))
                        wait(lambda:bool(select.select([client],[],[],0)[0]), 'activation reply timed out')
                        reply=unpack(client.recv(65536)[HEADER:]);self.assertEqual(reply['ok'],expected,title+': '+str(reply))
                activate('Terrain Profile',expected=False)
                activate('Reticulum')
                wait(lambda:'[Data]' in text() and 'fixture' in text(), 'Reticulum app failed with Connections also open')
                activate('Connections')
                wait(lambda:'[*Reticulum]' in text(), 'Connections did not return')
                os.write(master,b'd')
                wait(lambda:'Not attached' in text(), 'Reticulum detach failed')
                os.write(master,b'\x1b[Z\x1b[D')
                wait(lambda:'[*Device]' in text() and 'Attached' in text(), 'receive attachment lost on service switch')
                os.write(master,b'd')
                wait(lambda: 'Local shell' in text(), 'disconnect did not return to local shell')
                for title in ('Messages','Services','Nets','APRS Walk Logs','CW','Radio Feed','Heard','Audio Monitor','Stations','Station Map','Help','Scenery'):
                    prior=len(chunks)
                    activate(title)
                    wait(lambda:len(chunks)>prior, 'lazy application did not render: '+title)
                    self.assertNotIn('could not open.',text(),title+'\n'+text())
                os.write(master,b'\x1dq')
                wait(lambda: child.poll() is not None,'normal quit failed')
                self.assertEqual(child.returncode,0)
                self.assertFalse(any('ssh' in line for line in text().splitlines() if 'Connecting' in line))
                print('\nNormal make n810: first actionable frame %.3fs; attach/detach and quit passed' % first_frame)
            finally:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGTERM)
                    try: child.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
                os.close(master)


if __name__ == '__main__': unittest.main()
