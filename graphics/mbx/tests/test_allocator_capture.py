import struct,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime'))
from check_capture import validate,SIZE

def fixture():
 b=bytearray(SIZE);ta,table,target,guard,param,tiles=0x88000000,0x88100000,0x88200000,0x88300000,0x88400000,0x88500000
 struct.pack_into('<16I',b,0,0x3142584d,SIZE,ta,0x01010003,83952391,0x40,6,1,table,target,guard,0,0,param,tiles,0x31534154)
 b[64:8256]=b'\x3c'*8192;b[8256:12352]=b'\xa5'*4096
 pages=[guard]*8192;pages[1]=target;pages[16:32]=[param+i*4096 for i in range(16)];pages[32]=tiles;pages[128:132]=[ta+i*4096 for i in range(4)];pages[144]=ta+16384;pages[146]=ta+20480;pages[148]=ta+24576
 m=struct.pack('<8192I',*pages);b[12352:45120]=b[45120:77888]=m
 p=[0]*16384;p[:5]=[0xe0000000,0xa8804000,0x0e080410,0xd6887610,0x22220e80];p[7]=p[10]=0x43000000;p[11:17]=[0x3f800000]*6;p[21]=p[25]=0x3d800000;b[77888:143424]=struct.pack('<16384I',*p)
 t=[0]*1024;t[:32:2]=[0x22000000]*16;t[30]|=0x80000000;b[143424:147520]=struct.pack('<1024I',*t);b[-4096:]=b'\x5a'*4096;b[147520:163904]=struct.pack('<8192H',*( (i+1)&8191 for i in range(8192)))
 return b

class CaptureTests(unittest.TestCase):
 def test_valid_owned_layout(self):self.assertEqual(validate(fixture())['status'],'TA_ALLOCATOR_INITIALIZED_BOUNDS_PASS')
 def test_each_immutable_boundary(self):
  for offset in (24,64,4160,8256,12352,45120,77888,143424,147520+16384,SIZE-1):
   b=fixture();b[offset]^=1
   with self.subTest(offset=offset),self.assertRaises(ValueError):validate(b)
 def test_other_engine_completion_does_not_authorize_release(self):
  for wrong in (4,0x10,0x100,0x400,0xffffffff,0x40|0x20):
   b=fixture();struct.pack_into('<I',b,20,wrong)
   with self.subTest(events=wrong),self.assertRaises(ValueError):validate(b)
 def test_context_roundtrip_only_allows_declared_objects(self):
  b=fixture();struct.pack_into('<I',b,20,0x100);struct.pack_into('<I',b,24,13);struct.pack_into('<I',b,60,0x32534154);b[147520+20480]=1;b[147520+24576]=2
  self.assertEqual(validate(b)['status'],'TA_CONTEXT_ROUNDTRIP_BOUNDS_PASS')
  for offset in (147520+20480+260,147520+24576+520):
   c=bytearray(b);c[offset]=1
   with self.assertRaises(ValueError):validate(c)
 def test_geometry_requires_both_completions_and_parameter_data(self):
  b=fixture();struct.pack_into('<I',b,20,0x110);struct.pack_into('<I',b,24,46);struct.pack_into('<I',b,60,0x34534154)
  with self.assertRaises(ValueError):validate(b)
  b[77992]=1
  self.assertEqual(validate(b)['status'],'TA_TRIANGLE_PARAMETER_BOUNDS_PASS')
  for wrong in (0x10,0x100):
   c=bytearray(b);struct.pack_into('<I',c,20,wrong)
   with self.assertRaises(ValueError):validate(c)
 def test_frame_terminated_geometry_requires_matching_submission(self):
  b=fixture();struct.pack_into('<I',b,20,0x110);struct.pack_into('<I',b,24,47);struct.pack_into('<I',b,60,0x35534154);b[77992]=1
  self.assertEqual(validate(b)['status'],'TA_TRIANGLE_PARAMETER_BOUNDS_PASS')
  struct.pack_into('<I',b,24,46)
  with self.assertRaises(ValueError):validate(b)
 def test_complete_context_candidate_requires_its_own_write_count(self):
  b=fixture();struct.pack_into('<I',b,20,0x110);struct.pack_into('<I',b,24,50);struct.pack_into('<I',b,60,0x37534154);b[77992]=1
  self.assertEqual(validate(b)['status'],'TA_TRIANGLE_PARAMETER_BOUNDS_PASS')
  for wrong in (46,47,48):
   c=bytearray(b);struct.pack_into('<I',c,24,wrong)
   with self.assertRaises(ValueError):validate(c)
 def test_seed_context_is_separate_and_guarded(self):
  b=fixture();b[147520+28672:]=struct.pack('<2I',28|(4<<13),31)+bytes(4088);b.extend(b'\x5a'*4096)
  struct.pack_into('<I',b,4,len(b));struct.pack_into('<I',b,20,0x110);struct.pack_into('<I',b,24,50);struct.pack_into('<I',b,60,0x38534154);b[77992]=1
  for table in (12352,45120):struct.pack_into('<I',b,table+152*4,0x88000000+28672)
  self.assertEqual(validate(b)['status'],'TA_TRIANGLE_PARAMETER_BOUNDS_PASS')
  for offset in (147520+28672,147520+28672+519,147520+32768,len(b)-1,12352+152*4):
   c=bytearray(b);c[offset]^=1
   with self.subTest(offset=offset),self.assertRaises(ValueError):validate(c)
 def test_disjoint_dpm_seed_uses_reserved_pages(self):
  b=fixture();b[147520+28672:]=struct.pack('<2I',17|(10<<13),26)+bytes(4088);b.extend(b'\x5a'*4096)
  struct.pack_into('<I',b,4,len(b));struct.pack_into('<I',b,20,0x110);struct.pack_into('<I',b,24,50);struct.pack_into('<I',b,60,0x43534154);b[77992]=1
  for table in (12352,45120):struct.pack_into('<I',b,table+152*4,0x88000000+28672)
  self.assertEqual(validate(b)['status'],'TA_TRIANGLE_PARAMETER_BOUNDS_PASS')
  struct.pack_into('<2I',b,147520+28672,28|(4<<13),31)
  with self.assertRaises(ValueError):validate(b)
 def test_allocation_overlap_rejected(self):
  b=fixture();struct.pack_into('<I',b,8,0x88100000)
  with self.assertRaises(ValueError):validate(b)
if __name__=='__main__':unittest.main()
