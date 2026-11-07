"""Restricted C55x integer MAC functional model; not an execution emulator.

Decodes only the new forms exercised by fir8_one.s. No pipeline, status
side-effects, return stack, memory bus/cache, or interrupt behavior is modeled.
"""


def signed(value, bits):
    value &= (1 << bits) - 1
    return value - (1 << bits) if value & (1 << (bits - 1)) else value


def model_fir(code, memory, pointers, cdp, status):
    required = {"C54CM": 0, "FRCT": 0, "M40": 1, "SATD": 0,
                "SXMD": 1, "AR0LC": 0, "AR1LC": 0, "CDPLC": 0}
    if any(status.get(k) != v for k, v in required.items()):
        raise ValueError("unsupported numerical or addressing mode")
    if status.get('SMUL') not in (0, 1):
        raise ValueError('SMUL must be a bit; either value is inert with FRCT=0')
    ar = list(pointers)
    if len(ar) != 8:
        raise ValueError("eight auxiliary-register values required")
    accumulators = [None] * 4
    reads, stores = [], []
    pc = 0
    while pc < len(code):
        op = code[pc]
        if code[pc:pc+2] == b"\x48\x04":
            if pc + 2 != len(code):
                raise ValueError("bytes after terminal RET")
            return {"memory": memory, "pointers": ar, "cdp": cdp,
                    "accumulators": accumulators, "reads": reads, "stores": stores}
        if op == 0xD1 and pc + 2 < len(code):
            address, mode = code[pc+1:pc+3]
            if address & 31 != 3 or mode not in (1, 5, 17, 21, 33, 37, 49, 53):
                raise ValueError("unsupported multiply encoding")
            ptr, acc = address >> 5, mode >> 4
            reads.extend((ar[ptr], cdp))
            product = signed(memory[ar[ptr]], 16) * signed(memory[cdp], 16)
            product = signed(product, 32)  # FRCT=0; all signed 16x16 products fit.
            if mode & 4:
                if accumulators[acc] is None:
                    raise ValueError("MAC before accumulator initialization")
                product += accumulators[acc]
            if not -(1 << 39) <= product < (1 << 39):
                raise ValueError("40-bit accumulator overflow outside proof scope")
            accumulators[acc] = signed(product, 40)
            ar[ptr] += 1
            cdp += 1
            pc += 3
        elif op == 0xFA and pc + 3 < len(code):
            address, shift, mode = code[pc+1:pc+4]
            if address & 31 != 3 or shift != 1 or mode not in (4, 68, 132, 196):
                raise ValueError("unsupported saturating-store encoding")
            ptr, acc = address >> 5, mode >> 6
            if accumulators[acc] is None or ar[ptr] not in memory:
                raise ValueError("uninitialized accumulator or out-of-buffer store")
            shifted = accumulators[acc] * 2
            if not -(1 << 39) <= shifted < (1 << 39):
                raise ValueError("40-bit shifter overflow outside proof scope")
            saturated = max(-(1 << 31), min((1 << 31) - 1, shifted))
            high = ((saturated & ((1 << 40) - 1)) >> 16) & 0xFFFF
            memory[ar[ptr]] = high
            stores.append(ar[ptr])
            ar[ptr] += 1
            pc += 4
        else:
            raise ValueError(f"unsupported encoding at byte {pc}")
    raise ValueError("no terminal RET")
