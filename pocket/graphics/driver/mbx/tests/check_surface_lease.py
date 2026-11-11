"""Linux ABI/ownership boundary tests in the existing builder; no device IO."""
from pathlib import Path
import base64,json,subprocess
p=Path(__file__).resolve().parents[1]
f={x.name:base64.b64encode(x.read_bytes()).decode() for x in [p/'common/mbx_owned_surface.h',p/'common/mbx_surface_lease.h',p/'tests/test_surface_lease.c']}
code='''import json,sys,base64,tempfile,subprocess,os
from pathlib import Path
with tempfile.TemporaryDirectory(dir='/dev/shm') as d:
 os.environ['TMPDIR']=d
 p=Path(d)
 for n,b in json.load(sys.stdin).items():(p/n).write_bytes(base64.b64decode(b))
 subprocess.run(['cc','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I'+d,str(p/'test_surface_lease.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
'''
subprocess.run(['/opt/homebrew/bin/limactl','shell','n810-builder','--','python3','-c',code],input=json.dumps(f),text=True,check=True)
