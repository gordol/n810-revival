"""Cross-build the non-X pixel presenter locally. Never accesses the Nokia."""
from pathlib import Path
import subprocess,json,base64,hashlib
pocket=Path(__file__).resolve().parents[1];root=pocket.parent;out=pocket/'build/graphics-nokia';out.mkdir(parents=True,exist_ok=True)
shared=root/'mbx-driver/display/native'
inputs={f.name:f.read_bytes() for f in [shared/'present.c',shared/'present.h',shared/'cells.c',shared/'cells.h',pocket/'graphics/native/nokia.c']}
script=r'''
from pathlib import Path
import subprocess,json,base64,sys
p=Path('/tmp/pocket-graphics-nokia-20261107');p.mkdir(exist_ok=True)
for name,data in json.load(sys.stdin).items():(p/name).write_bytes(base64.b64decode(data))
flags=['-O2','-std=c99','-Wall','-Wextra','-Werror','-fPIC','-shared','-mcpu=arm1136jf-s','-marm','-mfloat-abi=soft']
for target,sources in [('cells.so',['cells.c']),('window.so',['nokia.c','present.c'])]:
 subprocess.run(['arm-linux-gnueabi-gcc',*flags,*[str(p/n) for n in sources],'-o',str(p/target)],check=True)
'''
vm=['/opt/homebrew/bin/limactl','shell','n810-builder','--']
subprocess.run(vm+['python3','-c',script],input=json.dumps({n:base64.b64encode(v).decode() for n,v in inputs.items()}).encode(),check=True)
for n in ('cells.so','window.so'):(out/n).write_bytes(subprocess.check_output(vm+['cat','/tmp/pocket-graphics-nokia-20261107/'+n]))
(out/'BUILD.json').write_text(json.dumps({'status':'CROSS_BUILT_NOT_DEVICE_TESTED','sources':{n:hashlib.sha256(v).hexdigest() for n,v in inputs.items()},'artifacts':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ('cells.so','window.so')}},indent=2)+'\n')
print('Built non-X Nokia frontend libraries; no device access')
