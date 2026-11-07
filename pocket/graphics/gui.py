"""Launch the complete graphical desktop using the existing platform adapter."""
from pathlib import Path
import os,subprocess,sys
root=Path(__file__).resolve().parents[2]
if sys.platform=='darwin':
 platform=root/'experiments/gpu-terminal-20261107'
 subprocess.run([sys.executable,str(platform/'build_mac.py')],check=True)
 os.execv(sys.executable,[sys.executable,str(platform/'native.py'),*sys.argv[1:]])
else:
 # Other platforms supply their context/presenter explicitly to the shared entry.
 os.execv(sys.executable,[sys.executable,str(Path(__file__).with_name('full.py')),*sys.argv[1:]])
