from pathlib import Path
import os,shutil,json,hashlib,py_compile
assert os.geteuid()==0
base=Path('/usr/local/lib/n810-pocket');old=Path('/tmp/pocket-overlap-20261109')
backup=base/'normal-gpu-rollback-20261109';backup.mkdir(exist_ok=False)
entry=Path('/usr/local/sbin/n810-pocket-console');shutil.copy2(entry,backup/entry.name)
template=base/'native-template';template.mkdir()
for f in old.iterdir():
 if f.is_file() and (f.suffix=='.py' or f.name in ('BUILD.json','MANIFEST.json','PARAMETERS.json','PROBE-SETTINGS.json')) and f.name not in ('owner-state.json','owner-restored.json','gpu-final.json','stage.py','run_comparison.py','benchmark_app.py'):
  shutil.copy2(f,template/f.name)
(template/'payload').mkdir();shutil.copy2(old/'payload/n810_mbx_gpu_probe.ko',template/'payload/n810_mbx_gpu_probe.ko')
managed=Path('/usr/local/share/pocket-gui/managed-native');managed.mkdir()
shutil.copytree(old/'benchmark/source-scene/pocket',managed/'source')
shutil.copytree(old/'benchmark/assets-scene',managed/'assets',symlinks=False)
f=managed/'source/graphics/gpu_scene.py';f.write_text(f.read_text().replace("self.lib=C.CDLL(str(Path(platform.library).resolve().parent/'window.so'))","self.lib=self.display.lib if self.display is not None and hasattr(self.display.lib,'pocket_scene_open') else C.CDLL(str(Path(platform.library).resolve().parent/'window.so'))",1))
for asset in managed.rglob('*'):
 if asset.is_dir():os.chmod(asset,0o755)
 elif asset.is_file():os.chmod(asset,0o755 if '.so' in asset.name else 0o644)
shutil.copy2('/tmp/native_owner_20261109.py',base/'native_owner.py')
py_compile.compile(str(base/'native_owner.py'),doraise=True)
entry.write_text('''#!/bin/sh
set -eu
case "${1:-}" in
run)
 if test "$(cat /usr/local/lib/n810-pocket/renderer 2>/dev/null || echo tui)" = gpu; then
  exec /usr/bin/python3 -I /usr/local/lib/n810-pocket/native_owner.py
 fi;;
status)
 if test -f /run/n810-pocket-native/active.json; then cat /run/n810-pocket-native/active.json; exit 0; fi;;
*) exit 2;;
esac
exec /usr/bin/python3 -I /usr/local/lib/n810-pocket/console_helper.py "$1"
''');os.chmod(entry,0o755)
(base/'renderer').write_text('gpu\n')
print('INSTALLED_NORMAL_GPU_DEFAULT; rollback: write tui to /usr/local/lib/n810-pocket/renderer')
