# SPDX-License-Identifier: MIT
"""Local retained-image API and real multi-process transaction checks; no device."""
from pathlib import Path
import os,subprocess,tempfile
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='mbx-sharing-') as directory:
 for name in ('job_lock','window_export'):
  binary=str(Path(directory)/name)
  subprocess.run([os.environ.get('CC','cc'),'-std=c11','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-pthread','-fsanitize=address,undefined','-I'+str(root/'common'),str(root/'tests'/('test_'+name+'.c')),'-o',binary],check=True)
  subprocess.run([binary],check=True,timeout=30)
