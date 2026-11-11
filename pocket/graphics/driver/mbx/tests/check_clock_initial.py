# SPDX-License-Identifier: MIT
"""Compile actual initial-admission and clock-cleanup blocks with fault injection."""
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = (root / 'kernel/n810_mbx_gpu_probe.c').read_text()
with tempfile.TemporaryDirectory(prefix='mbx-initial-clock-') as temporary:
    out = Path(temporary)
    start = source.index('static unsigned int initial_divider(')
    end = source.index('static void retain_fault(', start)
    (out / 'clock_cleanup.inc').write_text(source[start:end])
    start = source.index('    if((c->initial.fclk&6U)')
    end = source.index('    for(i=0;i<3;++i)', start)
    (out / 'clock_admission.inc').write_text(source[start:end])
    binary = out / 'test'
    subprocess.run([os.environ.get('CC', 'cc'), '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-fsanitize=address,undefined', '-I'+str(out),
                    str(root / 'tests/test_clock_initial.c'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
