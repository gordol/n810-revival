"""Mixed KISS/vendor parsing against real walk bytes and synthetic boundaries."""
import importlib.util,json,unittest
from pathlib import Path
ROOT=Path(__file__).parent
spec=importlib.util.spec_from_file_location('stream',ROOT/'uvpro-stream.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
spec=importlib.util.spec_from_file_location('bridge',ROOT/'n810-kiss-bridge.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
fixture=json.loads((ROOT/'fixtures/walk-mixed-vendor.json').read_text())
FRAME=bytes.fromhex(fixture['complete_kiss_frame'])
MIXED=bytes.fromhex(fixture['captured_mixed_frame'])
def gaia(command,body):return b'\xff\1\0'+bytes([len(body)])+b'\0\2'+command.to_bytes(2,'big')+body

def fragments(packet):
 parts=[packet[i:i+53] for i in range(0,len(packet),53)]
 return [gaia(9,b'\2'+bytes([i|(128 if i==len(parts)-1 else 0)])+part) for i,part in enumerate(parts)]

class Tests(unittest.TestCase):
 def test_recover_actual_walk_fragments(self):
  wire=fragments(FRAME[1:]);self.assertEqual(MIXED,b'\0'+b''.join(wire[:2]))
  packets=[];events=[];obs=s.Observer(packet=packets.append,frame=lambda *event:events.append(event))
  for byte in b'\xc0'+MIXED+wire[2]:obs.feed(bytes([byte]))
  self.assertEqual(len(packets),1);self.assertTrue(packets[0].startswith('VCAPK>APMI06'))
  self.assertEqual(events,[(FRAME,'vendor_reassembled',wire)])
 def test_kiss_and_vendor_duplicates_both_orders(self):
  for wire in (b''.join(fragments(FRAME[1:]))+b.encode(FRAME),b.encode(FRAME)+b''.join(fragments(FRAME[1:]))):
   packets=[];obs=s.Observer(packet=packets.append);obs.feed(wire);self.assertEqual(len(packets),1)
  packets=[];obs=s.Observer(packet=packets.append);obs.feed(b.encode(FRAME)*2);self.assertEqual(len(packets),2)
 def test_fragment_gap_timeout_and_new_packet(self):
  events=[];clock=[0];obs=s.Observer(frame=lambda *x:events.append(x),clock=lambda:clock[0]);parts=fragments(FRAME[1:])
  obs.feed(parts[0]+parts[2]);self.assertEqual(events,[])
  obs.feed(parts[0]);clock[0]=6;obs.feed(parts[1]+parts[2]);self.assertEqual(events,[])
  obs.feed(b''.join(parts));self.assertEqual(events[0][0],FRAME)
 def test_vendor_inside_kiss_payload_is_not_parsed_as_transport(self):
  embedded=b''.join(fragments(FRAME[1:]));outer=FRAME[:1+7*3+2]+embedded
  events=[];obs=s.Observer(frame=lambda *event:events.append(event));obs.feed(b.encode(outer))
  self.assertEqual(events,[(outer,'kiss',[])])
 def test_vendor_payload_delimiters_are_length_framed(self):
  packet=FRAME[1:]+b'\xc0\xdb\xff\x01';events=[];obs=s.Observer(frame=lambda *x:events.append(x))
  for byte in b''.join(fragments(packet)):obs.feed(bytes([byte]))
  self.assertEqual(events[0][0],b'\0'+packet)
 def test_replies_and_other_events_are_not_packets(self):
  packets=[];obs=s.Observer(packet=packets.append)
  obs.feed(gaia(0x8039,b'\x80'+FRAME[1:])+gaia(9,b'\1'+bytes(4)))
  self.assertEqual(packets,[])
 def test_malformed_kiss_resynchronizes(self):
  events=[];obs=s.Observer(frame=lambda *x:events.append(x))
  obs.feed(b'\xc0\0\xdb\1\xc0'+b.encode(FRAME))
  self.assertEqual(events,[(FRAME,'kiss',[])])
 def test_native_bss_preserves_vendor_wire_without_fake_ax25(self):
  packet=bytes.fromhex('0107204e3043414c4c0121052450494e47')
  wire=fragments(packet);events=[];packets=[]
  obs=s.Observer(frame=lambda *x:events.append(x),packet=packets.append)
  obs.feed(b''.join(wire))
  self.assertEqual(events,[(b'\0'+packet,'vendor_reassembled',wire)])
  self.assertEqual(packets,[])
  obs.feed(b.encode(b'\0'+packet))
  self.assertEqual(len(events),1)
 def test_unknown_reassembled_data_keeps_raw_evidence(self):
  wire=fragments(b'not AX25');events=[];packets=[]
  obs=s.Observer(frame=lambda *x:events.append(x),packet=packets.append)
  obs.feed(b''.join(wire))
  self.assertEqual(events,[(b'\0not AX25','vendor_reassembled',wire)])
  self.assertEqual(packets,[])

if __name__=='__main__':unittest.main(verbosity=2)
