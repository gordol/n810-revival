"""Exercise ULS context actions and real terrain through make n810 on a laptop."""
import fcntl
import importlib.util
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

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell'))
sys.path.insert(0,str(ROOT/'shell/vendor/terminal'))
from runtime_codec import frame,unpack,HEADER
import pyte


class LaunchTests(unittest.TestCase):
    def test_lookup_context_and_real_terrain_in_normal_launcher(self):
        if not (ROOT/'data/uls.sqlite').is_file():self.skipTest('Real FCC snapshot not installed')
        with tempfile.TemporaryDirectory(prefix='pocket-uls-',dir='/tmp') as folder:
            folder=Path(folder);station_db=folder/'stations.sqlite'
            spec=importlib.util.spec_from_file_location('uls_fixture_directory',ROOT/'shell/vendor/packet-console/n810-directory-model.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            db=module.database(station_db)
            db.execute('INSERT INTO stations VALUES (?,?,?,?)',('W1AW-7','2026-11-02T00:00:00+00:00','2026-11-02T00:00:00+00:00',1));db.execute('INSERT INTO evidence VALUES (?,?,?,?)',('W1AW-7','position','2026-11-02T00:00:00+00:00','[46.9731667,-123.1381667]'));db.commit();db.close()
            from terrain_qth import QTH
            QTH(folder/'state/qth.msgpack').save(5.5555,5.5555,height_m=15)
            master,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',38,120,0,0))
            env={k:v for k,v in os.environ.items() if not k.startswith(('POCKET_','N810_','CURRENT_WORLD_','XDG_','PYTHON'))}
            env.update(HOME=str(folder),XDG_STATE_HOME=str(folder/'state'),TERM='xterm-256color')
            extra=f'--no-local-services --no-save --state {folder}/state --station-db {station_db} --control-socket {folder}/ui.sock'
            child=subprocess.Popen(['make','n810','PYTHON='+sys.executable,'EXTRA='+extra],cwd=ROOT,env=env,
                                   stdin=slave,stdout=slave,stderr=slave,start_new_session=True)
            os.close(slave);screen=pyte.Screen(120,38);stream=pyte.ByteStream(screen);raw=bytearray()
            def text():return '\n'.join(screen.display)
            def wait(predicate,label):
                until=time.monotonic()+15
                while time.monotonic()<until:
                    if select.select([master],[],[],.02)[0]:
                        try:data=os.read(master,65536)
                        except OSError:data=b''
                        if data:raw.extend(data);stream.feed(data)
                    if predicate():return
                    if child.poll() is not None:break
                self.fail(label+'\n'+text()+'\n'+bytes(raw[-1500:]).decode(errors='replace'))
            def activate(name):
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(3);client.connect(str(folder/'ui.sock'));client.sendall(frame(dict(activate=name)))
                    wait(lambda:bool(select.select([client],[],[],0)[0]),'Activation reply')
                    reply=unpack(client.recv(65536)[HEADER:]);self.assertTrue(reply['ok'],reply)
            def desktop_status():
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(3);client.connect(str(folder/'ui.sock'))
                    client.sendall(frame(dict(command='status')))
                    wait(lambda:bool(select.select([client],[],[],0)[0]),'Desktop status reply')
                    reply=unpack(client.recv(65536)[HEADER:])
                    return reply
            def focused(name):return desktop_status().get('focus')==name
            try:
                wait(lambda:'[*Device]' in text(),'Desktop did not start')
                activate('Stations');wait(lambda:'W1AW-7' in text(),'Station fixture did not appear')
                wait(lambda:'FCC LICENSE' in text(),'Inline FCC identity did not appear')
                os.write(master,b'u')
                wait(lambda:'ARRL HQ OPERATORS CLUB' in text() and focused('ULS Lookup'),'U did not open selected license')
                self.assertNotIn(str(ROOT/'data/uls.sqlite'),text())
                activate('Stations')
                os.write(master,b'\x1b[21;2~')
                wait(lambda:'Lookup ULS' in text(),'Station context menu missing ULS lookup')
                self.assertIn('Use as profile start',text())
                os.write(master,b'Lookup ULS\r')
                wait(lambda:'ARRL HQ OPERATORS CLUB' in text(),'Context ULS lookup did not show real license')
                self.assertIn('2026-11-01',text())
                activate('Terrain Profile');wait(lambda:'[From A]' in text(),'Terrain map did not open')
                wait(lambda:'▀' in text() and 'Loading offline map' not in text(),'Offline map did not finish loading')
                # Real SGR mouse clicks in the app map, followed by the Profile action.
                os.write(master,b'\x1b[<0;38;17M\x1b[<0;38;17m')
                wait(lambda:'From selected' in text(),'Map did not select From endpoint')
                os.write(master,b'\x1b[<0;56;20M\x1b[<0;56;20m')
                wait(lambda:'Endpoints selected' in text(),'Map did not select To endpoint')
                os.write(master,b'p')
                wait(lambda:'LOS blocked' in text() or 'LOS clear' in text(),'Real terrain graph did not finish')
                self.assertIn('USGS',text())
                wait(lambda:'grid ~' in text() and ' m N/S' in text(),'Completed terrain frame did not display source resolution')
                destination=ROOT.parent/'outputs/fcc-directory-20261102'
                destination.mkdir(exist_ok=True)
                (destination/'pocket-real-terrain-screen.txt').write_text(text())
                os.write(master,b'mf')
                wait(lambda:'Frequency presets' in text(),'Band chooser did not open')
                os.write(master,b'\x1b[B\r')
                wait(lambda:'223.5' in text() or '220 MHz' in text(),'VHF 220 preset did not apply')
                os.write(master,b'l')
                wait(lambda:'Red clear' in text(),'Map LOS overlay did not finish')
                (destination/'pocket-los-map-screen.txt').write_text(text())
                activate('Station Map')
                wait(lambda:'[ Terrain T ]' in text(),'Station Map terrain button missing')
                wait(lambda:'Loading offline map' not in text() and 'loading requested' not in text(),'Station Map did not finish loading')
                os.write(master,b'++')
                wait(lambda:'Enter confirm' in text(),'Preview did not hold the zoom overlay')
                time.sleep(.5)
                self.assertIn('Enter confirm',text())
                os.write(master,b'\r')
                wait(lambda:'Zoom accepted' in text() or 'Zoom applied' in text(),'Enter gave no zoom acknowledgement')
                wait(lambda:'Zoom applied' in text(),'Confirmed zoom did not finish')
                os.write(master,b'\x1b[<2;38;17M')
                wait(lambda:'LOS radius from here' in text(),'Map location context actions missing')
                os.write(master,b'LOS radius from here\r')
                wait(lambda:'LOS radius T' in text(),'House mode did not open within Station Map')
                os.write(master,b'r')
                wait(lambda:'[Radius 10 km R]' in text(),'Selected radius not visible on map button')
                self.assertTrue('10 km radius' in text() or 'Radius 10 km selected' in text())
                before=desktop_status()['map']
                os.write(master,b'L')
                wait(lambda:'Red clear' in text() and '10 km radius' in text(),'L did not calculate selected radius')
                after=desktop_status()['map']
                self.assertEqual(after['center'],before['center']);self.assertEqual(after['span'],before['span'])
                os.write(master,b'R')
                wait(lambda:'Red clear' in text() and '20 km radius' in text(),'R alone did not recalculate the enabled overlay')
                self.assertEqual(desktop_status()['map']['span'],before['span'])
                os.write(master,b'j')
                wait(lambda:'Fresnel 60%' in text() or 'F60%' in text(),'Fresnel mode not shown on map')
                os.write(master,b'h')
                wait(lambda:'House radius LOS settings' in text(),'House antenna settings did not open')
                os.write(master,b'm')
                wait(lambda:'LOS radius T' in text(),'House map did not return')
                os.write(master,b'c')
                wait(lambda:'Selection cleared' in text(),'House pin could not be cleared')
                os.write(master,b'g')
                wait(lambda:'Profile from saved QTH to callsign' in text(),'QTH callsign shortcut missing')
                os.write(master,b'W1AW-7\r')
                wait(lambda:'X ' in text() and 'from start' in text(),'QTH profile did not show limiting sample')
                os.write(master,b'i')
                wait(lambda:'ray clear' in text(),'Profile sample close-up missing')
                os.write(master,b'x')
                wait(lambda:'limiting sample' in text(),'Limiting sample was not located on map')
                # Per-app switch must be reachable and actually gate running tools.
                activate('Station Map');os.write(master,b's')
                wait(lambda:'[T] Terrain / LOS:' in text(),'Sidebar terrain settings link missing')
                os.write(master,b't')
                wait(lambda:focused('Settings') and 'Terrain profiles, LOS and obstructions' in text(),'App settings page did not open')
                os.write(master,b'\r')
                wait(lambda:'[ ]' in text(),'Terrain feature did not switch off')
                activate('Station Map')
                wait(lambda:'[ Terrain T ]' not in text() and 'LOS radius T' not in text(),'Disabled terrain controls remained visible')
                activate('Terrain Profile')
                wait(lambda:'Terrain / LOS disabled' in text(),'Standalone profile bypassed app preference')
                activate('Settings');os.write(master,b'\r')
                wait(lambda:'[x]' in text(),'Terrain feature did not switch back on')
                for title in ('Terminal','Terminal 2','Terminal 3'):
                    os.write(master,b'\x1d,')
                    wait(lambda:'Applications' in text(),'App menu did not open')
                    os.write(master,b'Terminal\r')
                    wait(lambda:focused(title),'New shell window missing: '+title)
                os.write(master,b'\x1dq');wait(lambda:child.poll() is not None,'Desktop did not quit')
                self.assertEqual(child.returncode,0)
            finally:
                if child.poll() is None:
                    os.killpg(child.pid,signal.SIGTERM)
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=5)
                os.close(master)


if __name__=='__main__':unittest.main()
