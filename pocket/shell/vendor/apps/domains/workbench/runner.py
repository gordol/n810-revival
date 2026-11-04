"""Apply a CPU bound before invoking the fixed receive-only replay adapter."""
import resource
import runpy
import sys
from pathlib import Path
resource.setrlimit(resource.RLIMIT_CPU,(15,16))
resource.setrlimit(resource.RLIMIT_CORE,(0,0))
script=Path(__file__).resolve().parents[2]/'cw-reference/stream_cw.py'
sys.path.insert(0,str(script.parent))
sys.argv=[str(script),*sys.argv[1:]]
runpy.run_path(str(script),run_name='__main__')
