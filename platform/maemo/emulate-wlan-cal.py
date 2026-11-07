#!/usr/bin/env python3
"""Offline ARM harness: original wlan-cal code, mocked CAL and file I/O only."""
import argparse, sys, json, struct, hashlib, importlib.util
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_ARM, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC
from elftools.elf.elffile import ELFFile
base=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--binary',type=Path,required=True)
p.add_argument('--cal-image',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
a.out.mkdir(parents=True,exist_ok=False)
a.out.chmod(0o700)
spec=importlib.util.spec_from_file_location('cal_inspect',base.parent/'scripts/n810-cal-inspect.py')
cal=importlib.util.module_from_spec(spec);spec.loader.exec_module(cal)
backup=a.cal_image
records=cal.scan(backup.read_bytes());selected={}
for r in records:
 if r['header_crc_ok'] and r['data_crc_ok']:
  if r['name'] not in selected or r['version']>selected[r['name']]['version']:selected[r['name']]=r
binary=a.binary
if hashlib.sha256(binary.read_bytes()).hexdigest() != 'e562b686c736adef908b6d052f6c742d8fee93d482def95d4793d1be5fac5ca9':
 raise SystemExit('This harness requires the pinned Maemo wlan-cal binary; hook addresses are version-specific.')
u=Uc(UC_ARCH_ARM, UC_MODE_ARM);u.mem_map(0x8000,0x18000);u.mem_map(0x200000,0x200000);u.mem_map(0x400000,0x100000);u.mem_map(0x600000,0x1000)
with binary.open('rb') as f:
 elf=ELFFile(f)
 for seg in elf.iter_segments():
  if seg['p_type']=='PT_LOAD':u.mem_write(seg['p_vaddr'],seg.data())
heap=0x200000;fds={};writes={};reads=[];ppu=[]
def alloc(data):
 global heap
 p=heap;heap+=(len(data)+15)&~15;u.mem_write(p,data);return p
def string(p):
 b=bytearray()
 for i in range(4096):
  x=bytes(u.mem_read(p+i,1))
  if x==b'\0':return bytes(b)
  b+=x
 raise RuntimeError('Unterminated emulated string')
def ret(value):u.reg_write(UC_ARM_REG_R0,value&0xffffffff);u.reg_write(UC_ARM_REG_PC,u.reg_read(UC_ARM_REG_LR))
def hook(uc,address,size,data):
 if address==0x600000:uc.emu_stop();return
 if address not in {0x8594,0x85a0,0x85ac,0x85b8,0x85c4,0x85d0,0x85dc,0x85f4,0x8600,0x860c,0x8618,0x8630,0x863c}:return
 a,b,c,d=[uc.reg_read(r) for r in [UC_ARM_REG_R0,UC_ARM_REG_R1,UC_ARM_REG_R2,UC_ARM_REG_R3]]
 if address==0x8594:
  name=string(b).decode();r=selected.get(name);flags=struct.unpack('<I',bytes(uc.mem_read(uc.reg_read(UC_ARM_REG_SP),4)))[0]
  reads.append({'name':name,'requested_flags':flags,'found':r is not None,'length':r['length'] if r else 0})
  if r:
   p=alloc(r['payload']);uc.mem_write(c,struct.pack('<I',p));uc.mem_write(d,struct.pack('<I',len(r['payload'])));ret(0)
  else:uc.mem_write(c,struct.pack('<I',0));uc.mem_write(d,struct.pack('<I',0));ret(-1)
 elif address==0x85dc:uc.mem_write(a,struct.pack('<I',0x3f0000));ret(0)
 elif address==0x85ac:uc.mem_write(a,bytes(uc.mem_read(b,c)));ret(a)
 elif address==0x8600:
  x,y=string(a),string(b);ret((x>y)-(x<y))
 elif address==0x860c:
  path=string(a).decode();fd=len(fds)+3;fds[fd]=path;ret(fd)
 elif address==0x85d0:
  path=fds[a];assert path.startswith('/sys/devices/platform/wlan-omap/')
  writes[path]=bytes(uc.mem_read(b,c));ret(c)
 elif address==0x85f4:ppu.append({'property':a});ret(-1)
 elif address==0x85c4:raise RuntimeError('Original helper called abort')
 else:ret(0)
u.hook_add(UC_HOOK_CODE,hook);u.reg_write(UC_ARM_REG_SP,0x4ff000);u.reg_write(UC_ARM_REG_LR,0x600000)
u.emu_start(0x8908,0x600000,count=2000000)
assert u.reg_read(UC_ARM_REG_PC)==0x600000,'Instruction budget exhausted'
out=a.out
metadata={'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'backup_sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'cal_reads':reads,'ppu_calls':ppu,'writes':[],'limitations':['CAL record selection uses highest CRC-valid version per name; bank-selection semantics need separate validation.','PPU calls return missing-value errors; country and MAC outputs are not validated.','Captured files are analysis material, not installed driver inputs.']}
for path,content in writes.items():
 name=path.rsplit('/',1)[1]+'.bin';(out/name).write_bytes(content)
 metadata['writes'].append({'path':path,'file':name,'length':len(content),'sha256':hashlib.sha256(content).hexdigest()})
(out/'capture.json').write_text(json.dumps(metadata,indent=2)+'\n')
print(json.dumps({'cal_reads':reads,'writes':metadata['writes'],'ppu_calls':ppu},indent=2))
