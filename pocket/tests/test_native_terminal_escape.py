import sys,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from input import Input
from terminal_pointer_timing import IngressDecoder

class NativeEscapeTests(unittest.TestCase):
 def test_native_console_expires_escape_before_next_key(self):
  decoder=IngressDecoder(Input(passthrough=True))
  platform=SimpleNamespace(terminal_input=True,events=lambda:[])
  self.assertEqual(decoder.feed(b'\x1b'),[])
  self.assertEqual(decoder.events(platform,expire=True),[('key','\x1b')])
  self.assertEqual(decoder.feed(b'\r'),[('key','\r')])
 def test_fragmented_arrow_keeps_platform_events(self):
  decoder=IngressDecoder(Input(passthrough=True))
  platform=SimpleNamespace(terminal_input=True,events=lambda:[('focus',True)])
  self.assertEqual(decoder.feed(b'\x1b['),[])
  self.assertEqual(decoder.events(platform,expire=False),[('focus',True)])
  self.assertEqual(decoder.feed(b'C'),[('key','right')])
 def test_terminal_frontend_still_expires_escape(self):
  decoder=IngressDecoder(Input());decoder.feed(b'\x1b')
  self.assertEqual(decoder.events(expire=True),[('key','\x1b')])
if __name__=='__main__':unittest.main()
