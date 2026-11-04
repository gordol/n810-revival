"""Exercise the real owner loop with local fake radio and controller endpoints."""
import json
import os
from pathlib import Path
import select
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest


class ServiceTests(unittest.TestCase):
    def test_intent_survives_power_cycles_and_owner_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'.local/state/n810-aprs').mkdir(parents=True)
            source = Path(__file__).parent
            for name in ('feed_control.py',):
                shutil.copy(source/name, root/name)
            # The production peer check remains Linux-only; this fixture runs on macOS too.
            with (root/'feed_control.py').open('a') as stream:
                stream.write('\ndef authorize(peer, uid=None): return True\n')
            (root/'bluez_events.py').write_text('''
import socket
class BlueZ:
 def __init__(self):
  self.reader,self.writer=socket.socketpair();self.reader.setblocking(False)
  self.messages=[];self.set_power(True,None)
 def set_power(self,power,token):
  assert type(power) is bool,'power command lost requested boolean'
  self.messages.append({'kind':'controller','state':{'available':True,'powered':power,'devices':[],'error':None}})
  if token is not None:
   self.messages.append({'kind':'reply','token':token-1,'ok':False,'error':'stale callback'})
   self.messages.append({'kind':'reply','token':token,'ok':True})
  self.writer.send(b'!')
 def drain(self):
  self.reader.recv(4096);result=self.messages;self.messages=[];return result
 def close(self):self.reader.close();self.writer.close()
''')
            (root/'n810-frame-history.py').write_text('''
def limits():return 200,262144,100000,50
class Archive:
 def seed(self,rows):pass
 def close(self):pass
class History:
 records=[]
 archive=None
 @classmethod
 def load(cls):return cls()
 def decoded(self,describe):return []
 def export(self):return b''
 def save(self):pass
SNAPSHOT='fixture'
''')
            (root/'n810-packet-monitor.py').write_text('def describe(value):return str(value)\n')
            (root/'radio.py').write_text('''
import pathlib,os,time
p=pathlib.Path(os.environ['HOME'])/'starts'
with p.open('a') as f:f.write('start\\n')
print('UV-PRO connected | APRS receive monitor | Ctrl-C stops',flush=True)
while True:time.sleep(60)
''')
            text = (source/'n810-aprs-feed.py').read_text()
            text = text.replace('def main():', '''_real_save_intent=save_intent
def save_intent(path,enabled):
    marker=Path.home()/'failed-save-once'
    if not enabled and not marker.exists():
        marker.touch()
        raise OSError('injected sync failure')
    return _real_save_intent(path,enabled)
def main():''')
            text = text.replace("'/home/nokia/uvpro-aprs-listen.py'", repr(str(root/'radio.py')))
            text = text.replace("'/dev/shm/n810-aprs.sock'", repr(str(root/'feed.sock')))
            text = text.replace("'/dev/shm/n810-aprs-replay.sock'", repr(str(root/'replay.sock')))
            # Deliver a matching observation before the queued power action is dispatched.
            text = text.replace('                desired=power_request[2]',
                "                intent.observe_controller(dict(intent.controller,powered=power_request[2]))\n                desired=power_request[2]")
            (root/'owner.py').write_text(text)
            environment = dict(os.environ, HOME=str(root))
            process = None
            peer = None
            buffer = bytearray()
            next_id = 0

            def start():
                nonlocal process, peer
                process = subprocess.Popen([sys.executable, str(root/'owner.py')], env=environment,
                    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                deadline = time.monotonic()+4
                while True:
                    if process.poll() is not None:
                        self.fail(process.stderr.read().decode())
                    if time.monotonic()>deadline:self.fail('owner failed to listen')
                    peer = socket.socket(socket.AF_UNIX)
                    try:peer.connect(str(root/'feed.sock'));break
                    except (FileNotFoundError,ConnectionRefusedError):
                        peer.close();peer=None
                        time.sleep(.01)
                buffer.clear()

            def receive(predicate):
                deadline = time.monotonic()+5
                while True:
                    while b'\n' in buffer:
                        line, _, rest = buffer.partition(b'\n');buffer[:] = rest
                        if line.startswith(b'@FEED '):
                            value=json.loads(line[6:])
                            if predicate(value):return value
                    remaining=deadline-time.monotonic()
                    if remaining<=0:self.fail('missing expected owner publication')
                    if select.select([peer],[],[],remaining)[0]:
                        data=peer.recv(65536)
                        if not data:self.fail('owner closed control stream')
                        buffer.extend(data)

            def command(action, ok=True):
                nonlocal next_id
                next_id+=1;ident=str(next_id)
                peer.sendall((json.dumps(dict(type='feed_control',version=1,request_id=ident,action=action))+'\n').encode())
                answer=receive(lambda x:x['type']=='reply' and x['request_id']==ident)
                self.assertEqual(answer['ok'],ok,answer)

            def stop():
                nonlocal process,peer
                if peer:peer.close();peer=None
                if process:
                    process.terminate()
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill();process.wait();self.fail('owner failed graceful exit')
                    error=process.stderr.read().decode();process.stderr.close()
                    self.assertEqual(process.returncode,0,error)
                    process=None

            try:
                start();command('subscribe')
                receive(lambda x:x['type']=='state' and x['radio']['connected'] is True)
                command('receive_stop',ok=False)
                command('subscribe')
                failed_state=receive(lambda x:x['type']=='state')
                self.assertTrue(failed_state['reception']['enabled'])
                self.assertTrue(failed_state['radio']['connected'])
                command('controller_off')
                command('receive_stop')
                command('controller_on')
                command('subscribe')
                state=receive(lambda x:x['type']=='state')
                self.assertFalse(state['reception']['enabled'])
                self.assertEqual((root/'starts').read_text().splitlines(),['start'])
                stop()
                start();command('subscribe')
                state=receive(lambda x:x['type']=='state')
                self.assertFalse(state['reception']['enabled'])
                self.assertEqual((root/'starts').read_text().splitlines(),['start'])
                command('receive_start')
                receive(lambda x:x['type']=='state' and x['radio']['connected'] is True)
                self.assertEqual(len((root/'starts').read_text().splitlines()),2)
                command('radio_disconnect');command('subscribe')
                state=receive(lambda x:x['type']=='state')
                self.assertFalse(state['reception']['enabled'])
                self.assertTrue(state['controller']['powered'])
            finally:
                stop()


if __name__ == '__main__':unittest.main()
