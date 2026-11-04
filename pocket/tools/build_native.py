"""Build the optional compositor explicitly, outside the source checkout."""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,sys,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from native_runtime import select
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--arm-headers',type=Path,help='extracted Debian ARM Python 3.11 usr/include directory')
p.add_argument('--arm-vfp',action='store_true',help='use ARM1136 VFP instructions with the existing soft-float calling convention')
p.add_argument('--output',type=Path,help='private ARM build directory')
a=p.parse_args()
if a.arm_headers is None:
    if a.arm_vfp:p.error('--arm-vfp requires --arm-headers')
    if a.output:p.error('--output requires --arm-headers')
    result=select(build=True);print(result['library'] or result['reason'])
    raise SystemExit(0 if result['library'] else 1)
if a.output is None:p.error('--arm-headers requires --output')
compiler=shutil.which('arm-linux-gnueabi-gcc')
if not compiler:raise SystemExit('Install the ARM soft-float cross compiler in the build environment')
headers=a.arm_headers.resolve();root=Path(__file__).resolve().parents[1]/'shell/native'
if not (headers/'python3.11/Python.h').is_file() or not (headers/'arm-linux-gnueabi/python3.11/pyconfig.h').is_file():
    raise SystemExit('ARM Python 3.11 headers are incomplete')
out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
flags=['-O3','-std=c99','-Wall','-Wextra','-Werror','-fPIC','-shared','-pthread','-mcpu=arm1136jf-s','-marm','-mfloat-abi=soft','-ffp-contract=off','-fno-fast-math','-fno-builtin-sin','-fno-builtin-cos','-I'+str(headers/'python3.11'),'-I'+str(headers)]
if a.arm_vfp:
    flags[flags.index('-mfloat-abi=soft')]='-mfloat-abi=softfp';flags.append('-mfpu=vfp')
fd,name=tempfile.mkstemp(prefix='.cell-',suffix='.so',dir=out);os.close(fd)
try:
    subprocess.run([compiler,*flags,str(root/'cell_module.c'),'-o',name],check=True)
    raw=Path(name).read_bytes();os.replace(name,out/'_cellengine.abi3.so')
finally:
    Path(name).unlink(missing_ok=True)
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
identity=dict(system='Linux',machine='armv6l',python_tag='cpython-311',build_policy=5,
    abi='CPython limited API 3.11',sources={n:sha(root/n) for n in ('cell_module.c','cell_engine.c','window_host.c','scene_host.c','blend_host.c','input_pump.c')})
record=dict(cpu_features=['vfp'] if a.arm_vfp else [],identity=identity,sha256=hashlib.sha256(raw).hexdigest(),flags=flags,
    compiler=subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
    headers={str(path.relative_to(headers)):sha(path) for folder in ('python3.11','arm-linux-gnueabi/python3.11') for path in (headers/folder).rglob('*.h')})
(out/'provenance.json').write_text(json.dumps(record,indent=2)+'\n')
print(out/'_cellengine.abi3.so')
