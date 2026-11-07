#!/usr/bin/env python3
"""Static legacy Gateway ownership/units audit, not active-device inspection."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import tarfile

DSP_SHA = '5f731c97b477064ce92e6a13c697de9c66fd8bea93b11f88ee867792b3e3d4f4'
KERNEL_SHA = '29e52706dc01317021d1a7fef9069766dbd87616fc8c67c6a7a2bc71c0020800'
PATCH_SHA = 'e45a93c6cf574e12c26cde9ac925389f2a136247f20a47c7b94204dd93e731c0'


def verify(path, digest):
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
            raise ValueError('source hash mismatch: ' + str(path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dsp_archive', type=Path)
    parser.add_argument('kernel_archive', type=Path)
    parser.add_argument('patch_archive', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    for path, digest in ((args.dsp_archive, DSP_SHA), (args.kernel_archive, KERNEL_SHA),
                         (args.patch_archive, PATCH_SHA)):
        verify(path, digest)
    evidence = []
    dsp_specs = [
        ('tokliBIOS/tokliBIOS.c', [(396, 408), (420, 431)]),
        ('tokliBIOS/tokliBIOSlib.h', [(86, 102), (224, 230)]),
        ('tokliBIOS/usertask.c', [(111, 133)]),
        ('apps/ex_task/task_test7.c', [(53, 69)]),
        ('tokliBIOS/tokliBIOS.h', [(38, 60)])]
    kernel_specs = [
        ('ipbuf.h', [(37, 42)]), ('dsp.h', [(85, 87), (183, 187)]),
        ('dsp_common.h', [(45, 50)]),
        ('task.c', [(767, 795), (1092, 1103), (2470, 2485), (2514, 2525)])]
    for path, prefix, specs in (
            (args.dsp_archive, 'dspgw-3.3-dsp/', dsp_specs),
            (args.kernel_archive, 'kernel-source-diablo/kernel-source/arch/arm/plat-omap/dsp/', kernel_specs)):
        with tarfile.open(path, 'r:*') as archive:
            for relative, spans in specs:
                name = prefix + relative
                content = archive.extractfile(name).read()
                lines = content.decode('latin1').splitlines()
                evidence.append({'archive': path.name, 'file': name,
                                 'sha256': hashlib.sha256(content).hexdigest(),
                                 'spans': [{'start': start, 'end': end,
                                            'lines': lines[start-1:end]} for start, end in spans]})
    patch = gzip.decompress(args.patch_archive.read_bytes()).decode('latin1')
    section = next(s for s in re.split(r'(?=^--- )', patch, flags=re.M)
                   if s.startswith('--- ') and '/arch/arm/plat-omap/dsp/task.c' in s.splitlines()[0])
    hunks = [(int(a), int(b or '1')) for a, b in
             re.findall(r'^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@', section, re.M)]
    checked = [(720, 850), (1030, 1110), (2447, 2526)]
    overlaps = [(start, count) for start, count in hunks
                if any(start <= end and start + max(count, 1) - 1 >= begin for begin, end in checked)]
    if overlaps:
        raise ValueError('packaging patch changes inspected transfer regions; re-audit required')
    result = {
        'scope': 'DSP Gateway 3.3 DSP source and preserved N8x0 2.6.21 ARM transport source; not current firmware/kernel',
        'hardware_execution': False, 'current_kernel_compatibility_proven': False,
        'source_archives': {args.dsp_archive.name: DSP_SHA, args.kernel_archive.name: KERNEL_SHA,
                            args.patch_archive.name: PATCH_SHA},
        'evidence': evidence, 'task_patch_original_hunks': hunks,
        'task_patch_overlaps_transfer_regions': False,
        'findings': [
            'ARM read/write lengths are octets; private descriptor counts and DSP pointers use 16-bit words.',
            'Private descriptor fields are c,s,al,ah. ARM uses four u16 fields; do not map a host-native DSP struct over serialized data.',
            'DSP bksndp waits for the previous descriptor to become free, then publishes count/address/sync and sends a mailbox notification.',
            'ARM active block read releases private output ownership only after the block is drained, including partial-read tracking.',
            'Inference: a pipelined wrapper must obtain output ownership before writing the output buffer, not only when calling bksndp afterward.',
            'The example task copies output before bksndp and re-arms input immediately after publication. This does not by itself establish safe pipelining with a slow/partial ARM reader.',
            'A first adapter can serialize one transaction through complete readback; multiple buffers require explicit per-buffer ownership.',
            'No current-kernel cache/barrier behavior, DSP C ABI, firmware symbols or load address has been established.'
        ]}
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': 'STATIC_AUDIT_COMPLETE', 'source_files': len(evidence),
                      'task_patch_hunks': len(hunks), 'overlapping_hunks': len(overlaps),
                      'hardware_execution': False}, indent=2))


if __name__ == '__main__':
    main()
