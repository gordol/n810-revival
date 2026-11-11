# SPDX-License-Identifier: MIT
"""Local software checks for bounded retained-window checkpoints; no device."""
from pathlib import Path
import os,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='mbx-window-checkpoint-') as directory:
 d=Path(directory);(d/'draw').symlink_to(root/'common',target_is_directory=True)
 service=(root/'kernel/mbx_render_service.h').read_text();a=service.index('    resident_job=resources.count');z=service.index('    if(merge_job&&!window_merge)',a)
 (d/'native_admission.inc').write_text(service[a:z])
 sources=[root/'tests/test_window_checkpoint.c',root/'mesa/separate_blend.c',*[root/'common'/('mbx_vgp_'+n+'.c') for n in ('wire','draw','transform','isa')]]
 exe=str(d/'test')
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-Wno-unused-variable','-Wno-return-type','-fsanitize=address,undefined','-I'+str(root/'common'),'-I'+str(d),*map(str,sources),'-o',exe],check=True)
 subprocess.run([exe],check=True)
