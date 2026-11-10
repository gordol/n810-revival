# SPDX-License-Identifier: MIT
from pathlib import Path
import os,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='mbx-window-channels-') as directory:
 d=Path(directory);(d/'draw').symlink_to(root/'common',target_is_directory=True)
 sources=[root/'tests/test_window_channels.c',root/'mesa/linear_resource.c',*[root/'common'/('mbx_vgp_'+n+'.c') for n in ('wire','draw','transform','isa')]]
 exe=str(d/'test');subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-misleading-indentation','-fsanitize=address,undefined','-I'+str(root/'common'),'-I'+str(d),*map(str,sources),'-o',exe],check=True);subprocess.run([exe],check=True)

 subprocess.run([os.environ.get('CXX','c++'),'-x','c++','-std=c++17','-Wall','-Wextra','-Werror','-fsyntax-only','-I'+str(root/'common'),'-'],input='#include "mbx_window_export.h"\nstatic_assert(sizeof(mbx_window_view)==16);static_assert(sizeof(mbx_window_rect)==16);\n',text=True,check=True)
