#!/usr/bin/env python3
"""Raw history and broker replay integration tests; no Bluetooth or RF."""
import ast
import selectors
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('history',ROOT/'n810-frame-history.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


def row(frame=b'\0test',direction='radio_to_host'):
 return dict(time='2026-10-14T12:34:56.123-07:00',direction=direction,frame=frame.hex())


def address(call,last=False):
 return bytes(ord(c)<<1 for c in call.ljust(6))+bytes([0x60|last])
FRAME=b'\0'+address('APRS')+address('N0CALL',True)+b'\x03\xf0raw replay test'


class HistoryTests(unittest.TestCase):
 def test_cleanup_resumes_after_interrupted_unregister(self):
  # Exercise the broker's actual closure with the state left by SIGTERM
  # between selector removal and removal from the client collections.
  tree=ast.parse((ROOT/'n810-aprs-feed.py').read_text())
  main=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='main')
  drop=next(node for node in main.body if isinstance(node,ast.FunctionDef) and node.name=='drop')
  with selectors.DefaultSelector() as selector:
   client,peer=socket.socketpair()
   try:
    clients={client:bytearray()};replays={client}
    selector.register(client,selectors.EVENT_READ)
    selector.unregister(client)
    scope=dict(sel=selector,clients=clients,replay_clients=replays)
    exec(compile(ast.Module(body=[drop],type_ignores=[]),str(ROOT/'n810-aprs-feed.py'),'exec'),scope)
    scope['drop'](client)
    self.assertFalse(clients)
    self.assertFalse(replays)
    self.assertEqual(client.fileno(),-1)
   finally:
    client.close();peer.close()

 def test_limits_and_directions(self):
  records=h.History()
  for _ in range(205):records.add(row())
  self.assertEqual(len(records.records),200)
  for _ in range(5):records.add(row(b'\0'+b'x'*65535))
  self.assertLessEqual(records.size,h.MAX_BYTES)
  records=h.History();records.add(row(FRAME));records.add(row(FRAME,'host_to_radio_written'))
  self.assertEqual(len(records.decoded(lambda frame:'N0CALL>APRS ctl=03 pid=f0 test')),1)
  for bad in (dict(row(),direction='queued'),dict(row(),frame='zz'),dict(row(),time='12:00')):
   with self.assertRaises((ValueError,KeyError)):records.add(bad)

 def test_vendor_metadata_survives_snapshot_and_counts_toward_limit(self):
  vendor=b'\xff\1\0\0\0\2\0\x39'
  record=dict(row(FRAME),origin='vendor_reassembled',wire_frames=[vendor.hex()])
  history=h.History();history.add(record)
  self.assertEqual(history.size,len(FRAME)+len(vendor))
  with tempfile.TemporaryDirectory(dir='/tmp') as root:
   path=Path(root)/'frames.json';history.save(path)
   self.assertEqual(list(h.History.load(path).records),[record])
  with self.assertRaises(ValueError):history.add(dict(record,wire_frames=['00']))

 def test_snapshot(self):
  with tempfile.TemporaryDirectory(dir='/tmp') as d:
   path=Path(d)/'frames.json';records=h.History();records.add(row(FRAME));records.save(path)
   restored=h.History.load(path)
   self.assertEqual(list(restored.records),list(records.records))
   self.assertEqual(path.stat().st_mode&0o777,0o600)

 def test_broker_shutdown_restore_and_readonly_export(self):
  with tempfile.TemporaryDirectory(prefix='fh-',dir='/tmp') as d:
   p=Path(d);decoded=str(p/'decoded.sock');replay=str(p/'replay.sock');saved=str(p/'raw.json')
   for name in ('n810-packet-monitor.py','n810-frame-history.py'):shutil.copyfile(ROOT/name,p/name)
   history=p/'n810-frame-history.py'
   history.write_text(history.read_text().replace("'~/.local/state/n810-aprs/raw-frames.json'",repr(saved)))
   fake=p/'fake.py'
   fake.write_text('import signal,sys,pathlib\nsignal.signal(signal.SIGTERM,lambda *_:sys.exit(0))\np=pathlib.Path(__file__).with_suffix(".started")\nif not p.exists():\n p.touch()\n print('+repr('@KISS '+json.dumps(row(FRAME)))+',flush=True)\n print("12:34:56 N0CALL>APRS ctl=03 pid=f0 raw replay test",flush=True)\n print('+repr('@KISS '+json.dumps(row(FRAME,'host_to_radio_written')))+',flush=True)\nprint("Fake receiver ready",flush=True)\nsignal.pause()\n')
   source=(ROOT/'n810-aprs-feed.py').read_text().replace("'/dev/shm/n810-aprs.sock'",repr(decoded)).replace("'/dev/shm/n810-aprs-replay.sock'",repr(replay)).replace("'/home/nokia/uvpro-aprs-listen.py'",repr(str(fake))).replace("'~/.local/state/n810-aprs/last-packets.json'",repr(str(p/'legacy.json')))
   (p/'feed.py').write_text(source)
   def start():
    process=subprocess.Popen([os.sys.executable,str(p/'feed.py')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    deadline=time.monotonic()+60
    while time.monotonic()<deadline:
     if Path(decoded).exists() and Path(replay).exists():return process
     if process.poll() is not None:raise RuntimeError(process.stdout.read().decode())
     time.sleep(.02)
    process.kill();output=process.communicate(timeout=10)[0]
    raise RuntimeError('broker did not start: '+output.decode())
   def export():
    c=socket.socket(socket.AF_UNIX);c.settimeout(30);c.connect(replay)
    with c.makefile('rb') as f:
     header=json.loads(f.readline());records=[json.loads(f.readline()) for _ in range(header['records'])]
     self.assertEqual(f.read(),b'')
    c.close();return records
   process=start();client=socket.socket(socket.AF_UNIX);client.settimeout(30);client.connect(decoded)
   try:
    data=b''
    while b'Fake receiver ready' not in data:data+=client.recv(8192)
    self.assertNotIn(b'@KISS',data)
    self.assertEqual(len(export()),2)
    self.assertFalse(Path(saved).exists(),'raw snapshot should not be written per packet')
    process.terminate();out=process.communicate(timeout=30)[0];self.assertEqual(process.returncode,0,out)
   finally:
    client.close()
    if process.poll() is None:process.kill();process.communicate()
   self.assertEqual(len(h.History.load(saved).records),2)
   archived=h.page(path=p/'packets.sqlite3')
   self.assertEqual(archived['records'],[row(FRAME,'host_to_radio_written'),row(FRAME)])
   self.assertFalse(Path(decoded).exists());self.assertFalse(Path(replay).exists())
   process=start();client=socket.socket(socket.AF_UNIX);client.settimeout(30);client.connect(decoded)
   try:
    data=b''
    while b'Fake receiver ready' not in data:data+=client.recv(8192)
    self.assertIn(b'12:34:56 N0CALL>APRS ctl=03 pid=f0 raw replay test',data)
    self.assertEqual(data.count(b'raw replay test'),1)
    self.assertEqual(len(export()),2)
    self.assertEqual(len(h.page(path=p/'packets.sqlite3')['records']),2)
   finally:
    client.close();process.terminate();out=process.communicate(timeout=30)[0]
    self.assertEqual(process.returncode,0,out)


if __name__=='__main__':unittest.main(verbosity=2)
