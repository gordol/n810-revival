"""Build the graphical frontend's existing cell renderer and SDL presenter."""
from pathlib import Path
import hashlib,json,os,shlex,subprocess,sys
pocket=Path(__file__).resolve().parents[1];root=pocket.parent;out=pocket/'build/graphics';out.mkdir(parents=True,exist_ok=True)
shared=root/'mbx-driver/display/native'
subprocess.run(['cc','-O2','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',str(shared/'cells.c'),'-o',str(out/'cells.so')],check=True)
flags=shlex.split(subprocess.check_output(['sdl2-config','--cflags','--libs'],text=True))
subprocess.run(['cc','-O2','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',str(pocket/'graphics/native/window.c'),*flags,'-o',str(out/'window.so')],check=True)
os.environ['XDG_CACHE_HOME']=str(out/'cache')
sys.path.insert(0,str(pocket/'shell'))
from native_runtime import select
native=select(build=True)
if not native['library']:raise SystemExit(native['reason'])
config={'font':str(root/'outputs/mbx-native-shell-20261105/console-font.psf'),'renderer_library':str(out/'cells.so'),'display_library':str(out/'window.so'),'native_library':native['library']}
(out/'frontend.json').write_text(json.dumps(config,indent=2)+'\n')
print('Built graphical frontend; no device or installed desktop changes')
