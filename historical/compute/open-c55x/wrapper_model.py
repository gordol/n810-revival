"""Restricted leaf-wrapper model; no real C caller, return stack or pipeline."""
from copy import deepcopy
from fir_model import model_fir

# SPRU281E Tables 6-2/6-3; native large-model c55_std only.
ENTRY_FIELDS = {
    (1, 14): 1, (1, 10): 0, (1, 9): 0, (1, 8): 1, (1, 7): 0,
    (1, 6): 0, (1, 5): 0, (2, 15): 1, (2, 10): 0, (2, 8): 0,
    **{(2, bit): 0 for bit in range(8)}, (3, 5): 0,
}


def model_wrapper(code, memory, state):
    frame = deepcopy(state)
    if any(((frame['ST'][reg] >> bit) & 1) != value
           for (reg, bit), value in ENTRY_FIELDS.items()):
        raise ValueError('nonstandard C entry status')
    if len(frame['XAR']) != 8 or any(not 0 <= p < (1 << 23) for p in frame['XAR']):
        raise ValueError('invalid 23-bit pointer frame')
    for pointer, words in zip(frame['XAR'][:3], (8, 8, 1)):
        if (pointer & 0xFFFF) + words > 0xFFFF:
            raise ValueError('pointer wrap outside proof scope')
    body = None
    pc = 0
    while pc < len(code):
        if code[pc:pc+2] == b'\x48\x04':
            if pc+2 != len(code) or body is None:
                raise ValueError('invalid terminal RET')
            return {'state_before_ret': frame, 'body': body,
                    'return_stack_emulated': False}
        if pc+1 >= len(code):
            raise ValueError('truncated wrapper instruction')
        op, operand = code[pc:pc+2]
        if op == 0x90:
            src, dst = operand >> 4, operand & 15
            if src not in range(7, 16) or dst not in range(7, 16):
                raise ValueError('unsupported pointer move')
            value = frame['XCDP'] if src == 7 else frame['XAR'][src-8]
            if dst == 7:
                frame['XCDP'] = value
            else:
                frame['XAR'][dst-8] = value
            pc += 2
        elif op == 0x46:
            bit, reg, value = operand >> 4, (operand & 7) >> 1, operand & 1
            if operand & 8 or (reg, bit) != (1, 10):
                raise ValueError('status change outside wrapper subset')
            if value:
                frame['ST'][reg] |= 1 << bit
            else:
                frame['ST'][reg] &= ~(1 << bit)
            pc += 2
        elif op == 0xD1 and body is None:
            # Decode the checked 28-byte inline numerical body with its existing
            # independent functional model. Its synthetic RET only ends that model.
            st1, st2, st3 = frame['ST'][1:]
            fields = {'C54CM': (st1 >> 5) & 1, 'FRCT': (st1 >> 6) & 1,
                      'M40': (st1 >> 10) & 1, 'SATD': (st1 >> 9) & 1,
                      'SMUL': (st3 >> 1) & 1, 'SXMD': (st1 >> 8) & 1,
                      'AR0LC': st2 & 1, 'AR1LC': (st2 >> 1) & 1,
                      'CDPLC': (st2 >> 8) & 1}
            body = model_fir(code[pc:pc+28] + b'\x48\x04', memory,
                             frame['XAR'], frame['XCDP'], fields)
            frame['XAR'] = body['pointers']
            frame['XCDP'] = body['cdp']
            frame['AC'][0] = body['accumulators'][0]
            # Arithmetic status side-effects (e.g. ACOV0) are not modeled.
            pc += 28
        else:
            raise ValueError(f'unsupported wrapper opcode at byte {pc}')
    raise ValueError('no terminal RET')
