#!/usr/bin/env python3
"""Small C55x byte encoder, derived from TI SPRU374G, not GNU opcode tables.

Sequential moves/addition plus the narrow MPYM/MACM/saturating-store forms
used by fir8_one.s. No branches, task linking or firmware generation.
This emits instruction bytes, not a firmware image or a Gateway task.
"""
import argparse
from pathlib import Path
import re


def encode(source):
    code = bytearray()
    for number, original in enumerate(source.splitlines(), 1):
        line = original.split(";", 1)[0].strip()
        if not line or line == ".text" or re.fullmatch(r"\.global [A-Za-z_]\w*", line):
            continue
        if re.fullmatch(r"[A-Za-z_]\w*:", line):
            continue  # No instruction in this subset can refer to a label.
        if line == "NOP":
            code.append(0x20)  # 0010 000E, E=0. SPRU374G 5-344.
        elif line == "RET":
            code.extend((0x48, 0x04))  # 0100 100E xxxx x100. 5-377.
        elif m := re.fullmatch(r"MOV\s+\*AR([0-7])\+,\s*T([0-3])", line):
            ar, temp = map(int, m.groups())
            # 1010 FDDD AAAA AAAI. FDDD=0100+t; Smem=PPP0 0011.
            # 5-255, Table 6-2 (6-15, 6-18, 6-23).
            code.extend((0xA0 | (4 + temp), (ar << 5) | 3))
        elif m := re.fullmatch(r"MOV\s+T([0-3]),\s*\*AR([0-7])\+", line):
            temp, ar = map(int, m.groups())
            # 1100 FSSS AAAA AAAI. 5-312 and Table 6-2.
            code.extend((0xC0 | (4 + temp), (ar << 5) | 3))
        elif m := re.fullmatch(r"ADD\s+#([0-9]+),\s*T([0-3])", line):
            immediate, temp = map(int, m.groups())
            if not 0 <= immediate <= 15:
                raise ValueError(f"line {number}: immediate is outside k4")
            # 0100 000E kkkk FDDD. 5-15; E=0, FDDD=0100+t.
            code.extend((0x40, (immediate << 4) | (4 + temp)))
        elif m := re.fullmatch(r"(MPYM|MACM)\s+\*AR([0-7])\+,\s*\*CDP\+,\s*AC([0-3])", line):
            operation, ar, acc = m.groups()
            # SPRU374G 5-329 / 5-168: D1 Smem U%DD 00mm / 01mm.
            # U=0, %=0; Cmem *CDP+ has mm=01 (Table 6-2).
            code.extend((0xD1, (int(ar) << 5) | 3,
                         (int(acc) << 4) | (5 if operation == "MACM" else 1)))
        elif m := re.fullmatch(r"MOV\s+HI\(saturate\(AC([0-3])\s*<<\s*#1\)\),\s*\*AR([0-7])\+", line):
            acc, ar = map(int, m.groups())
            # SPRU374G 5-301: FA Smem uxSHIFTW SSxxx1x%; signed,
            # shift +1, saturate, no rounding, reserved bits zero.
            code.extend((0xFA, (ar << 5) | 3, 1, (acc << 6) | 4))
        elif m := re.fullmatch(r"MOV\s+(XAR[0-7]|XCDP),\s*(XAR[0-7]|XCDP)", line):
            def register(name):
                return 7 if name == "XCDP" else 8 + int(name[-1])
            src, dst = map(register, m.groups())
            # SPRU374G 5-280 and Table 6-2: 90 XSSS XDDD, full 23-bit move.
            code.extend((0x90, (src << 4) | dst))
        elif m := re.fullmatch(r"(BSET|BCLR)\s+#10,\s*ST1_55", line):
            operation = m.group(1)
            # SPRU374G 5-102/5-112: 46 kkkk nnn{clear=0,set=1}.
            code.extend((0x46, 0xA2 | (operation == "BSET")))
        else:
            raise ValueError(f"line {number}: unsupported instruction: {line}")
    return bytes(code)


def model(code, memory, pointers):
    """Functional data-path model only; no cycles, hazards, flags, or RET stack.

    Assumes SATA=0, ARnLC=0, accessible 16-bit words, no pointer wrap. RET
    ends this local model rather than emulating the DSP's return mechanism.
    """
    ar = list(pointers)
    if len(ar) != 8:
        raise ValueError("eight auxiliary-register values required")
    temps = [None] * 4
    pc = 0
    stores = []
    while pc < len(code):
        first = code[pc]
        if first == 0x20:
            pc += 1
            continue
        if pc + 1 >= len(code):
            raise ValueError("truncated instruction")
        second = code[pc + 1]
        if (first, second) == (0x48, 4):
            if pc + 2 != len(code):
                raise ValueError("bytes after terminal RET")
            return memory, ar, stores
        if first in range(0xA4, 0xA8) and second & 31 == 3:
            ptr, temp = second >> 5, first - 0xA4
            temps[temp] = memory[ar[ptr]] & 0xFFFF
            ar[ptr] += 1
        elif first in range(0xC4, 0xC8) and second & 31 == 3:
            ptr, temp = second >> 5, first - 0xC4
            if temps[temp] is None or ar[ptr] not in memory:
                raise ValueError("uninitialized register or out-of-buffer store")
            stores.append(ar[ptr])
            memory[ar[ptr]] = temps[temp]
            ar[ptr] += 1
        elif first == 0x40 and second & 15 in range(4, 8):
            temp = (second & 15) - 4
            if temps[temp] is None:
                raise ValueError("uninitialized register")
            temps[temp] = (temps[temp] + (second >> 4)) & 0xFFFF
        else:
            raise ValueError(f"unsupported encoding at byte {pc}")
        pc += 2
    raise ValueError("no terminal RET")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(encode(args.source.read_text()))
