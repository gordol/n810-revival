"""Compare optimized and portable packing, including halos and unaligned buffers."""
from pathlib import Path
import os, subprocess, tempfile
root = Path(__file__).resolve().parents[1]
cc = os.environ.get('CC', 'cc')
with tempfile.TemporaryDirectory() as name:
    tmp = Path(name)
    source = root / 'mesa/linear_resource.c'
    include = '-I' + str(root / 'mesa')
    subprocess.run([cc, '-O2', '-fsanitize=address,undefined', '-U__BYTE_ORDER__',
                    '-Dmbx_linear_pack=reference_pack', '-Dmbx_linear_size=reference_size',
                    include, '-c', str(source), '-o', str(tmp / 'reference.o')], check=True)
    subprocess.run([cc, '-O2', '-fsanitize=address,undefined', include,
                    str(root / 'tests/test_linear_pack_parity.c'), str(source),
                    str(tmp / 'reference.o'), '-o', str(tmp / 'test')], check=True)
    subprocess.run([str(tmp / 'test')], check=True)
