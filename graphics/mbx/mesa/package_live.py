from pathlib import Path
import hashlib,json,shutil,tarfile
here=Path(__file__).resolve().parent;driver=here.parent
stage=here/'mbx-gears-live-stage'
stage.mkdir(exist_ok=True)
shutil.copytree(driver/'runtime',stage,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
shutil.copyfile(driver/'BUILD.json',stage/'BUILD.json')
for name in ('desktop_pause.py','run_live.py','run_gears_gpu.py','run_service_frame.py','stop_service.py','bin_frame.py','read_frame.py'):
    shutil.copyfile(here/name,stage/name)
(stage/'lib').mkdir(exist_ok=True)
shutil.copyfile(here/'artifacts/libGL.so.1',stage/'lib/libGL.so.1')
shutil.copyfile(here/'artifacts/profile-sampler',stage/'profile-sampler');(stage/'profile-sampler').chmod(0o755)
shutil.copyfile(here/'artifacts/gears-status',stage/'gears-status');(stage/'gears-status').chmod(0o755)
shutil.copyfile(driver.parent/'outputs/nokia-glxgears-software-baseline-20261102/mesa-utils-bin_8.5.0-1_armel.deb',stage/'mesa-utils-bin_8.5.0-1_armel.deb')
pins={str(p.relative_to(stage)):hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file() and p.name!='LIVE-PINS.json'}
(stage/'LIVE-PINS.json').write_text(json.dumps(pins,indent=2)+'\n')
with tarfile.open(here/'mbx-gears-live-stage.tar.gz','w:gz') as t:t.add(stage,arcname=stage.name)
print(json.dumps({'module':pins['payload/n810_mbx_gpu_probe.ko'],'libGL':pins['lib/libGL.so.1'],'glxgears_package':pins['mesa-utils-bin_8.5.0-1_armel.deb']},indent=2))
