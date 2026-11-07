#!/usr/bin/env python3
"""Check the documented large-model C leaf wrapper locally; no DSP execution."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import random
import subprocess
from copy import deepcopy
from fir_model import signed
from subset import encode
from wrapper_model import ENTRY_FIELDS, model_wrapper


def run(argv):
    p = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=30)
    if p.returncode:
        raise RuntimeError(p.stdout+p.stderr)
    return p.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--build', type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    asm = here/'fir8_std.s'
    code = encode(asm.read_text())
    kernel = encode((here/'fir8_one.s').read_text())
    assert len(code) == 38 and code[6:34] == kernel[:-2]
    (out/'fir8_std.bin').write_bytes(code)
    coverage = [f'MOV {a},{b}' for a in [f'XAR{i}' for i in range(8)]+['XCDP']
                for b in [f'XAR{i}' for i in range(8)]+['XCDP']]
    coverage += [f'{op} #{bit},ST{reg}_55' for op in ('BSET','BCLR')
                 for bit,reg in ((10,1),)]
    gnu_match = None
    if args.build:
        build = args.build.resolve()
        for name,text in [('fir8_std',asm.read_text()),
                           ('wrapper-coverage',' .text\n'+'\n'.join(' '+s for s in coverage)+'\n')]:
            (out/(name+'.s')).write_text(text)
            obj = out/(name+'.o')
            run([build/'gas/as-new',out/(name+'.s'),'-o',obj])
            run([build/'binutils/objcopy','-O','binary','-j','.text',obj,out/(name+'.gnu.bin')])
            assert (out/(name+'.gnu.bin')).read_bytes() == encode(text)
            assert 'RELOCATION RECORDS' not in run([build/'binutils/objdump','-r',obj])
            (out/(name+'.dis')).write_text(run([build/'binutils/objdump','-d','-r',obj]))
        gnu_match = True
    library = out/'libfir.so'
    run(['cc','-O2','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC',
         here.parent/'fir_q15.c','-o',library])
    lib = ctypes.CDLL(str(library))
    shortp = ctypes.POINTER(ctypes.c_short)
    lib.n810_fir_q15.argtypes = [shortp,shortp,shortp,ctypes.c_uint,ctypes.c_uint]
    lib.n810_fir_q15.restype = None
    arr = ctypes.c_short*8
    y = (ctypes.c_short*1)()
    rng = random.Random(2420_55_42)
    base_st = [0xBEEF,0x4100,0xE000,0x0C02]
    count = 0

    def make_state(status):
        x,h,y = 0x121000,0x233000,0x342000  # synthetic 23-bit addresses, not OMAP allocation claims
        return {'XAR':[x,h,y]+[rng.randrange(1<<23) for _ in range(5)],
                'XCDP':rng.randrange(1<<23),'XDP':rng.randrange(1<<23),
                'AC':[rng.randrange(-(1<<39),1<<39) for _ in range(4)],
                'T':[rng.randrange(1<<16) for _ in range(4)],'SP':0x8000,'SSP':0x9000,
                'RETA':0x123456,'CFCT':rng.randrange(256),'ST':list(status)}

    def check(status,x=None,h=None):
        nonlocal count
        if x is None:
            x = [rng.randrange(-32768,32768) for _ in range(8)]
            h = [rng.randrange(-32768,32768) for _ in range(8)]
        state = make_state(status)
        before = deepcopy(state)
        xp,hp,yp = state['XAR'][:3]
        memory = {xp+i:v&65535 for i,v in enumerate(x)}
        memory.update({hp+i:v&65535 for i,v in enumerate(h)})
        memory.update({yp:0xCAFE,xp-1:0xA55A,xp+8:0xA55A,
                       hp-1:0xA55A,hp+8:0xA55A,yp-1:0xA55A,yp+1:0xA55A})
        original = memory.copy()
        result = model_wrapper(code,memory,state)
        after = result['state_before_ret']
        expected = max(-32768,min(32767,sum(a*b for a,b in zip(x,h))//32768))
        lib.n810_fir_q15(arr(*x),arr(*h),y,1,8)
        assert signed(memory[yp],16) == y[0] == expected
        original[yp] = expected&65535
        assert memory == original and state == before
        assert after['XAR'] == [xp+8,yp+1,yp]+before['XAR'][3:]
        assert after['XCDP'] == hp+8
        assert after['AC'] == [sum(a*b for a,b in zip(x,h))]+before['AC'][1:]
        assert after['ST'][1:] == before['ST'][1:]  # ST0 arithmetic flags are outside this model.
        for name in ('T','XDP','SP','SSP','RETA','CFCT'):
            assert after[name] == before[name],name
        assert not result['return_stack_emulated']
        count += 1

    # Exhaust the allowed variable bits of each status word separately.
    for register,mask in ((1,0xB81F),(2,0x1800),(3,0xF0C7)):
        bits = [b for b in range(16) if mask&(1<<b)]
        for pattern in range(1<<len(bits)):
            st = list(base_st)
            st[register] = (st[register]&~mask) | sum(((pattern>>i)&1)<<bit for i,bit in enumerate(bits))
            check(st)
    for _ in range(4096):
        check([rng.randrange(65536),0x4100|(rng.randrange(65536)&0xB81F),
               0xE000|(rng.randrange(65536)&0x1800),0x0C00|(rng.randrange(65536)&0xF0C7)])
    for x,h in [([-32768]*8,[-32768]*8),([-32768]*8,[32767]*8),
                ([-1]*8,[1]*8),([-32768]*8,[-32768,32767]*4)]:
        check(base_st,x,h)
    for (reg,bit),value in ENTRY_FIELDS.items():
        state = make_state(base_st)
        state['ST'][reg] ^= 1<<bit
        try:
            model_wrapper(code,{},state)
        except ValueError:
            pass
        else:
            raise AssertionError('accepted invalid C entry mode')
    # An omitted restoration must be observable by the context check.
    state = make_state(base_st)
    xp,hp,yp = state['XAR'][:3]
    mem = {xp+i:1 for i in range(8)}|{hp+i:1 for i in range(8)}|{yp:0}
    result = model_wrapper(code[:34]+code[36:],mem.copy(),state)
    assert result['state_before_ret']['ST'][1] != state['ST'][1]
    try:
        model_wrapper(code[:4]+code[6:],mem.copy(),state)
    except ValueError:
        pass
    else:
        raise AssertionError('accepted missing wide-accumulator setup')
    syntax_rejections = ['BSET #15,ST3_55','BCLR #1,ST1_55','MOV XSP,XAR0',
                         'PSH mmap(ST1_55)','CALL external_function']
    for text in syntax_rejections:
        try:
            encode(text)
        except ValueError:
            pass
        else:
            raise AssertionError('accepted syntax outside wrapper subset')
    for index,value in ((0,1<<23),(0,0xFFFF),(1,0xFFFF),(2,0xFFFF)):
        bad = make_state(base_st)
        bad['XAR'][index] = value
        try:
            model_wrapper(code,{},bad)
        except ValueError:
            pass
        else:
            raise AssertionError('accepted invalid pointer frame')
    result = {'status':'PASS','hardware_execution':False,'c_compiler_interop_executed':False,
              'return_stack_emulated':False,'kernel_bytes':len(code),
              'kernel_sha256':hashlib.sha256(code).hexdigest(),'gnu_byte_match':gnu_match,
              'new_encoding_cases':len(coverage),'numerical_and_context_cases':count,
              'invalid_entry_modes_rejected':len(ENTRY_FIELDS),
              'mode_setup_restore_mutations_detected':2,
              'unsupported_syntax_rejections':len(syntax_rejections),
              'invalid_pointer_frames_rejected':4,
              'abi':'documented TI c55_std pointer/register convention, large model; entry SMUL preserved at 0 or 1',
              'limits':'restricted functional/encoding model only; arithmetic flag side-effects, pipeline, actual caller/return and interrupts untested'}
    (out/'wrapper-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
