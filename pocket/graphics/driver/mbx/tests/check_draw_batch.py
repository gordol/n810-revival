# SPDX-License-Identifier: MIT
from pathlib import Path
import os,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='mbx-draw-batch-') as directory:
 d=Path(directory);(d/'draw').symlink_to(root/'common',target_is_directory=True)
 exe=str(d/'test');sources=[root/'tests/test_draw_batch.c',*[root/'common'/('mbx_vgp_'+n+'.c') for n in ('wire','draw','transform','isa')]]
 subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation','-Wno-return-type','-fsanitize=address,undefined','-I'+str(root/'common'),'-I'+str(d),*map(str,sources),'-o',exe],check=True)
 subprocess.run([exe],check=True)
