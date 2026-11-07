#!/usr/bin/env python3
"""Validate FIR instruction bytes/model against arbitrary precision and C.

This is local code-generation/functional-model evidence, not DSP execution.
"""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import random
import subprocess
from fir_model import model_fir, signed
from subset import encode

STATUS = {"C54CM": 0, "FRCT": 0, "M40": 1, "SATD": 0, "SMUL": 0,
          "SXMD": 1, "AR0LC": 0, "AR1LC": 0, "CDPLC": 0}


def run(command):
    result = subprocess.run(list(map(str, command)), capture_output=True,
                            text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def oracle(x, h):
    return max(-32768, min(32767, sum(a*b for a, b in zip(x, h)) // 32768))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--cc', default='cc')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    source = here / 'fir8_one.s'
    code = encode(source.read_text())
    (out / 'fir8_one.bin').write_bytes(code)
    byte_match = None
    # Cross-check every register variant of the three newly supported forms.
    coverage = [f'{op} *AR{ar}+,*CDP+,AC{acc}' for op in ('MPYM', 'MACM')
                for ar in range(8) for acc in range(4)]
    coverage += [f'MOV HI(saturate(AC{acc} << #1)),*AR{ar}+'
                 for ar in range(8) for acc in range(4)]
    if args.build:
        build = args.build.resolve()
        for name, text in (('fir8_one', source.read_text()),
                           ('fir-coverage', ' .text\n' + '\n'.join(' ' + x for x in coverage) + '\n')):
            asm, obj = out / (name + '.s'), out / (name + '.o')
            asm.write_text(text)
            run([build / 'gas/as-new', asm, '-o', obj])
            run([build / 'binutils/objcopy', '-O', 'binary', '-j', '.text', obj,
                 out / (name + '.gnu.bin')])
            assert (out / (name + '.gnu.bin')).read_bytes() == encode(text)
            assert 'RELOCATION RECORDS' not in run([build / 'binutils/objdump', '-r', obj])
            (out / (name + '.dis')).write_text(run([build / 'binutils/objdump', '-d', '-r', obj]))
        byte_match = True
    # Rebuild the unchanged C reference instead of trusting a preexisting .so.
    c_source = here.parent / 'fir_q15.c'
    library = out / 'libfir-reference.so'
    run([args.cc, '-O2', '-std=c99', '-Wall', '-Wextra', '-Werror', '-fPIC',
         '-shared', c_source, '-o', library])
    lib = ctypes.CDLL(str(library))
    shortp = ctypes.POINTER(ctypes.c_short)
    lib.n810_fir_q15.argtypes = [shortp, shortp, shortp, ctypes.c_uint, ctypes.c_uint]
    lib.n810_fir_q15.restype = None
    short8 = ctypes.c_short * 8
    output = (ctypes.c_short * 1)()
    counters = {'cases': 0, 'clamp_low': 0, 'clamp_high': 0, 'negative_fraction': 0}

    def check(x, h, smul=0):
        exact_sum = sum(a*b for a, b in zip(x, h))
        expected = oracle(x, h)
        original = dict(zip(range(0x1000, 0x1008), (a & 0xFFFF for a in x)))
        original.update(zip(range(0x3000, 0x3008), (a & 0xFFFF for a in h)))
        original.update({0x2000: 0xCAFE, 0x0FFF: 0xA55A, 0x1008: 0xA55A,
                         0x1FFF: 0xA55A, 0x2001: 0xA55A,
                         0x2FFF: 0xA55A, 0x3008: 0xA55A})
        modes = {**STATUS, 'SMUL': smul}
        result = model_fir(code, original.copy(), [0x1000, 0x2000] + [0]*6, 0x3000, modes)
        assert signed(result['memory'][0x2000], 16) == expected, (x, h, expected, result)
        desired = original.copy()
        desired[0x2000] = expected & 0xFFFF
        assert result['memory'] == desired
        assert result['pointers'] == [0x1008, 0x2001] + [0]*6
        assert result['cdp'] == 0x3008 and result['stores'] == [0x2000]
        assert result['reads'] == [address for k in range(8) for address in (0x1000+k, 0x3000+k)]
        assert result['accumulators'] == [exact_sum, None, None, None]
        lib.n810_fir_q15(short8(*x), short8(*h), output, 1, 8)
        assert output[0] == expected, (x, h, expected, output[0])
        counters['cases'] += 1
        counters['clamp_low'] += exact_sum // 32768 < -32768
        counters['clamp_high'] += exact_sum // 32768 > 32767
        counters['negative_fraction'] += exact_sum < 0 and exact_sum % 32768 != 0

    # Exhaust signed sample range against five diagnostically different taps.
    for coefficient in (-32768, -1, 1, 16384, 32767):
        for sample in range(-32768, 32768):
            check([sample] + [0]*7, [coefficient] + [0]*7)
    # Every tap position gets the signed extremes; all taps also accumulate.
    for position in range(8):
        for a in (-32768, -1, 0, 1, 32767):
            for b in (-32768, -1, 0, 1, 32767):
                x, h = [0]*8, [0]*8
                x[position], h[position] = a, b
                check(x, h)
    for a in (-32768, -1, 0, 1, 32767):
        for b in (-32768, -1, 0, 1, 32767):
            check([a]*8, [b]*8)
    # Exact quotient and saturation transition boundaries, on both sides.
    for target in (32767*32768, 32768*32768, -32768*32768, -32769*32768,
                   -32768, 0, 32768):
        for offset in (-1, 0, 1):
            total = target + offset
            first = max(-32768, min(32767, total // 32767))
            residual = total - first*32767
            tail = []
            for _ in range(3):
                v = max(-32768, min(32767, residual))
                tail.append(v)
                residual -= v
            assert residual == 0
            check([first] + tail + [0]*4, [32767, 1, 1, 1] + [0]*4)
    # Cancellation must not be corrupted by special fractional multiply mode.
    check([-32768, -32768] + [0]*6, [-32768, 32767] + [0]*6)
    check([-32768]*8, [-32768, 32767]*4)
    rng = random.Random(242055)
    for _ in range(4096):
        check([rng.randrange(-32768, 32768) for _ in range(8)],
              [rng.randrange(-32768, 32768) for _ in range(8)])
    for _ in range(4096):
        check([rng.randrange(-32768, 32768) for _ in range(8)],
              [rng.randrange(-32768, 32768) for _ in range(8)], smul=1)
    for key in STATUS.keys() - {'SMUL'}:
        bad = dict(STATUS)
        bad[key] = 1 - bad[key]
        try:
            model_fir(code, {}, [0]*8, 0, bad)
        except ValueError:
            continue
        raise AssertionError('accepted unsupported mode ' + key)
    # Guard against silently accepting a broken accumulation-only kernel.
    try:
        model_fir(code[3:], {0x1000: 1, 0x3000: 1}, [0x1000] + [0]*7, 0x3000, STATUS)
    except ValueError:
        pass
    else:
        raise AssertionError('accepted MAC before MPY')
    result = {'status': 'PASS', 'hardware_execution': False,
              'scope': 'instruction encoding, bounded functional model and unchanged C reference',
              'kernel_bytes': len(code), 'kernel_sha256': hashlib.sha256(code).hexdigest(),
              'gnu_byte_match': byte_match, 'new_encoding_cases': len(coverage),
              'model_vs_python_vs_c': counters,
              'required_modes': {k:v for k,v in STATUS.items() if k != 'SMUL'},
              'reference_source_sha256': hashlib.sha256(c_source.read_bytes()).hexdigest(),
              'accumulator_absolute_bound': 8 * 32768 * 32768,
              'unsupported_mode_rejections': len(STATUS)-1,
              'smul_one_additional_cases': 4096,
              'smul_supported_values': [0, 1]}
    (out / 'fir-validation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
