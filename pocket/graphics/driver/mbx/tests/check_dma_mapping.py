# SPDX-License-Identifier: MIT
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
s=(r/'kernel/mbx_dma_sink.h').read_text();body=s[s.index(' slast=ns;dlast=nd;'):s.index(' gpu_dma_sink_stage=11;')]
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text((r/'tests/test_dma_mapping_range.c').read_text().replace('/* ACTUAL_MAPPING_RANGE */',body))
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
print('DMA mapping: 200 offset/reversed rectangles and full screen; every touched byte covered')
