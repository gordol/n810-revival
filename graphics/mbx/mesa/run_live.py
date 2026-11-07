"""Bounded physical standard-glxgears GPU run with visible mode/FPS evidence."""
from pathlib import Path
import hashlib,json,os,subprocess,sys
root=Path(sys.argv[1]).resolve()
assert os.geteuid()==0
pins=json.loads((root/'LIVE-PINS.json').read_text())
for name,pin in pins.items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==pin,name
base=Path('/sys/module/n810_mbx_gpu_probe/parameters')
assert not base.exists()
subprocess.run([sys.executable,str(root/'run_gears_gpu.py'),str(root)],check=True)
