# SPDX-License-Identifier: MIT
"""Local native-size image allocation, sampler and real admission-block checks."""
from pathlib import Path
import os,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='mbx-native-windows-') as d:
 service=(root/'kernel/mbx_render_service.h').read_text();a=service.index('    resident_job=resources.count');z=service.index('    if(merge_job&&!window_merge)',a)
 (Path(d)/'native_admission.inc').write_text(service[a:z])
 for name in ('window_native','window_native_encoder','window_native_admission'):
  sources=[root/'tests'/('test_'+name+'.c')]
  if name.endswith('encoder'):sources += [root/'common'/('mbx_vgp_'+n+'.c') for n in ('wire','draw','transform','isa')]
  binary=str(Path(d)/name)
  subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-Wno-unused-variable','-fsanitize=address,undefined','-I'+str(root/'common'),'-I'+d,*map(str,sources),'-o',binary],check=True)
  subprocess.run([binary],check=True)
