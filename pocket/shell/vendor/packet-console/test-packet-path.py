"""Preserve digipeater H flags without confusing source/destination C bits."""
import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('monitor',Path(__file__).with_name('n810-packet-monitor.py'))
monitor=importlib.util.module_from_spec(spec);spec.loader.exec_module(monitor)

def addr(call,ssid=0,last=False,high=False):
 return bytes(ord(c)<<1 for c in call.ljust(6))+bytes([0x60|(ssid<<1)|int(last)|(0x80 if high else 0)])

class Paths(unittest.TestCase):
 def test_used_digipeaters_and_unused_alias(self):
  frame=b'\0'+addr('APRS',high=True)+addr('N0CALL',high=True)+addr('JUPITR',high=True)+addr('W7DK',high=True)+addr('WIDE2',1,last=True)+b'\x03\xf0hello'
  self.assertEqual(monitor.describe(frame),'N0CALL>APRS,JUPITR*,W7DK*,WIDE2-1 ctl=03 pid=f0 hello')
 def test_direct_packet_no_false_repeated_flag(self):
  frame=b'\0'+addr('APRS',high=True)+addr('N0CALL',last=True,high=True)+b'\x03\xf0hello'
  self.assertEqual(monitor.describe(frame),'N0CALL>APRS ctl=03 pid=f0 hello')
 def test_vendor_bytes_are_not_ax25_addresses(self):
  frame=b'\0'+bytes.fromhex('ff01003700020009020082a09a92606c60ac8682a0964060ae92888a64406303f0')
  text=monitor.describe(frame)
  self.assertTrue(text.startswith('Malformed AX.25 address:'))
  self.assertNotIn('\0',text)
 def test_unused_explicit_digipeater(self):
  frame=b'\0'+addr('APRS')+addr('N0CALL')+addr('W7DK',last=True)+b'\x03\xf0hello'
  self.assertIn('N0CALL>APRS,W7DK ctl=',monitor.describe(frame))

if __name__=='__main__':unittest.main(verbosity=2)
