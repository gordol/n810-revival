"""Build/test the portable executor boundary, including native sanitizers.

Pass --native-build pointing at an existing pinned native CMake build; no network
or board is accessed. This test does not rebuild or change that native library.
"""
import argparse,ctypes,json,math,os,shlex,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'shell/vendor/apps/domains/reticulum'))
from external_node import pack,unpack
from native_rpc import OPERATIONS

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--native-build',type=Path,required=True);parser.add_argument('--bridge-output',type=Path);args=parser.parse_args()
 flags=(args.native_build/'CMakeFiles/pocket_rns.dir/flags.make').read_text()
 includes=shlex.split(next(line.split('=',1)[1] for line in flags.splitlines() if line.startswith('CXX_INCLUDES =')))
 source=ROOT/'tests/native/rpc_dispatch_test.cpp';compiler=os.environ.get('CXX','c++')
 base=[compiler,'-std=c++17','-DNATIVE','-I'+str(ROOT/'shell/native/reticulum'),*includes,str(source)]
 cases=dict(init=[None,b'/host/path-must-not-be-used'],reset=[],online=[True],incoming=[b'x',1],identity=[b'z'*64,64,1],key=[7,True,None,64],destination=[7,0,b'pocket',b'data.v1',None],handler=[7,b'/service',2,b'a'*32,2],announce=[7,b'abc',3],public=[7,True],remove_destination=[7],link=[7,b'x'*16],link_id=[8,None],remote=[8],identify=[8,7],request=[8,b'/service',b'abc',3,99,15.0],reply=[8,b'r'*16,16,b'data',4],teardown=[8],resources=[8,1],resource=[8,b'abc',3,99],has_path=[b'h'*16],hops=[b'h'*16],lxmf_init=[7,b'name',None],lxmf_public=[True],lxmf_announce=[],lxmf_remember=[7],lxmf_send=[7,b'msg',3,99,0,None],appdata=[b'h'*16,None,8],cancel_stamp=[])
 assert set(cases)==OPERATIONS
 with tempfile.TemporaryDirectory(prefix='p-rpc-cpp-',dir='/tmp') as tmp:
  root=Path(tmp);library=root/'boundary.so';sanitizer=root/'sanitizer'
  subprocess.run(base+['-shared','-fPIC','-o',str(library)],check=True)
  lib=ctypes.CDLL(str(library));lib.pocket_rpc_test.argtypes=[ctypes.c_char_p,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t];lib.pocket_rpc_test.restype=ctypes.c_int
  lib.pocket_rpc_storage.restype=ctypes.c_char_p
  def call(name,values=None,raw=None):
   encoded=pack(values) if raw is None else raw;out=ctypes.create_string_buffer(65536)
   n=lib.pocket_rpc_test(name.encode(),encoded,len(encoded),out,len(out));assert n>0
   return unpack(out.raw[:n])
  for name,values in cases.items():
   before=lib.pocket_rpc_calls();r=call(name,values)
   assert r['result']>=0,(name,r);assert lib.pocket_rpc_calls()==before+1,name
   if name=='handler':assert lib.pocket_rpc_count()==2 and lib.pocket_rpc_last_byte()==ord('a')
   if name=='init':assert lib.pocket_rpc_storage()==b'/node/private'
  assert call('key',cases['key'])['outputs']==[b'k'*64]
  assert call('destination',cases['destination'])['outputs']==[b'd'*16]
  assert call('link',cases['link'])['outputs']==[]
  assert call('link_id',cases['link_id'])['outputs']==[b'i'*16]
  assert call('lxmf_send',cases['lxmf_send'])['outputs']==[b's'*36]
  assert call('appdata',cases['appdata'])['outputs']==[b'a'*3]
  bad=[('unknown',[]),('reset',[0]),('online',[1<<40]),('online',[(1<<64)-1]),('key',[7,1,0,64]),('key',[7,1,None,-1]),('handler',[7,b'/s',2,b'a'*16,2]),('handler',[7,b'/s',2,b'a'*272,17]),('handler',[7,b'/s',2,b'',1<<62]),('request',[8,b'/s',b'',0,1,math.nan]),('request',[8,b'/s',b'',0,1,math.inf]),('request',[8,b'/s',b'',0,1,True]),('announce',[7,b'abc',True]),('announce',[7,b'abc',2]),('destination',[7,0,b'pocket\0hidden',b'data',None]),('link',[7,b'short']),('has_path',[b'short']),('incoming',[b'x'*32768,32768])]
  for name,values in bad:
   before=lib.pocket_rpc_calls();r=call(name,values);assert r['result']<0,(name,r);assert lib.pocket_rpc_calls()==before,name
  malformed=[b'',b'\x91',b'\x91\xc6\xff\xff\xff\xff',b'\xdd\xff\xff\xff\xff',b'\x91\x91\xc0',b'\x90\xc0',b'\x91\xd3\x80',b'\x91\xc4\x08short']
  for raw in malformed:
   before=lib.pocket_rpc_calls();assert call('online',raw=raw)['result']<0;assert lib.pocket_rpc_calls()==before
  lib.pocket_rpc_request.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t];lib.pocket_rpc_request.restype=ctypes.c_int
  def request(value=None,raw=None):
   encoded=pack(value) if raw is None else raw;out=ctypes.create_string_buffer(65536)
   n=lib.pocket_rpc_request(encoded,len(encoded),out,len(out));assert n>0
   return unpack(out.raw[:n])
  common=dict(version=1,channel=1,session='ab'*16)
  requests=[dict(common,action='native_open',identity='12'*16,abi=2),dict(common,action='native_call',operation='request',arguments=cases['request']),dict(common,action='native_call',operation='reset',arguments=[]),dict(common,action='native_renew'),dict(common,action='native_cancel'),dict(common,action='native_callback',token='callback-1',data=b'\xc0\xdb'),dict(common,action='subscribe')]
  requests.extend(dict(requests[0],unix_ms=value) for value in (1,1793210000125,(1<<63)-1))
  before=lib.pocket_rpc_calls()
  for value in requests:
   decoded=request(value);assert 'error' not in decoded,(value,decoded)
   assert decoded['channel']==value['channel'] and decoded['session']==value['session']
   assert decoded['unix_ms']==value.get('unix_ms',0)
   if 'arguments' in value:assert decoded['arguments']==pack(value['arguments'])
   if 'data' in value:assert decoded['data']==value['data']
  clock_raw=pack(dict(requests[0],unix_ms=1))
  assert request(raw=clock_raw[:-1]+b'\xd3'+(1793210000125).to_bytes(8,'big',signed=True))['unix_ms']==1793210000125
  valid=requests[1]
  bad_requests=[{},dict(valid,version=True),dict(valid,version=2),dict(valid,channel=0),dict(valid,channel=-1),dict(valid,channel=1<<40),dict(valid,channel=True),dict(valid,channel=1.0),dict(valid,session='short'),dict(valid,session='AB'*16),dict(valid,session=b'ab'*16),dict(valid,action='snapshot'),dict(valid,action='native_call\0suffix'),dict(valid,arguments=[{}]),dict(valid,arguments=[[]]),dict(valid,arguments=[math.inf]),dict(valid,arguments=[0]*7),dict(valid,operation='x'*33),dict(valid,token='unexpected'),dict(valid,payload={}),dict(requests[0],abi=True),dict(requests[0],abi=-1),dict(requests[0],identity='bad'),dict(requests[5],data=[]),dict(requests[5],token='x'*65)]
  bad_requests.extend(dict(requests[0],unix_ms=value) for value in (0,-1,-(1<<63),1<<63,True,1.0,math.inf,b'123',None))
  bad_requests.extend(dict(value,unix_ms=1793210000125) for value in requests[1:7])
  for value in bad_requests:assert 'error' in request(value),(value,request(value))
  # Raw-map cases preserve duplicate keys, malformed string lengths and truncation.
  malformed_requests=[b'\x82'+pack('version')+pack(1)+pack('version')+pack(1),b'\xdf\xff\xff\xff\xff',b'\x81\xdb\xff\xff\xff\xff',pack(valid)+b'\xc0']
  for value in requests:
   encoded=pack(value)
   for n in range(len(encoded)):assert 'error' in request(raw=encoded[:n]),n
  for raw in malformed_requests:assert 'error' in request(raw=raw)
  assert lib.pocket_rpc_calls()==before,'Request decoding executed a native operation'
  lib.pocket_rpc_override(65);r=call('key',cases['key']);assert r['result']<0 and not r['outputs']
  lib.pocket_rpc_override(-7);r=call('key',cases['key']);assert r['result']==-7 and r['native_error']=='injected native error' and not r['outputs']
  subprocess.run(base+['-DPOCKET_RPC_SANITIZER_MAIN','-fsanitize=address,undefined','-fno-omit-frame-pointer','-o',str(sanitizer)],check=True)
  subprocess.run([str(sanitizer)],check=True,timeout=60)
 if args.bridge_output:
  native=args.native_build/('libpocket_rns.dylib' if sys.platform=='darwin' else 'libpocket_rns.so')
  subprocess.run([compiler,'-std=c++17','-DNATIVE','-I'+str(ROOT/'shell/native/reticulum'),*includes,str(ROOT/'tests/native/rpc_dispatch_bridge.cpp'),str(native),'-shared','-fPIC','-Wl,-rpath,'+str(args.native_build),'-o',str(args.bridge_output)],check=True)
 print(json.dumps(dict(passed=True,operations=len(cases),invalid_inputs=len(bad)+len(malformed),sanitized_mutations=200000,host_path_ignored=True,outer_requests=len(requests),invalid_outer_requests=len(bad_requests)+len(malformed_requests))))
if __name__=='__main__':main()
