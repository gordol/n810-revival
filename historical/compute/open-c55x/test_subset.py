#!/usr/bin/env python3
"""Cross-check TI-derived encodings and functional models; no DSP execution."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from subset import encode, model


def run(command):
    return subprocess.run(list(map(str, command)), check=True, capture_output=True,
                          text=True, timeout=30).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, help="built c55x-binutils directory")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    rows = []
    for name, delta in (("copy8", 0), ("add1_8", 1)):
        source = (here / (name + ".s")).read_text()
        code = encode(source)
        (out / (name + ".bin")).write_bytes(code)
        row = {"kernel": name, "bytes": len(code),
               "sha256": hashlib.sha256(code).hexdigest()}
        if args.build:
            build = args.build.resolve()
            obj = out / (name + ".o")
            run([build / "gas/as-new", here / (name + ".s"), "-o", obj])
            run([build / "binutils/objcopy", "-O", "binary", "-j", ".text",
                 obj, out / (name + ".gnu.bin")])
            assert (out / (name + ".gnu.bin")).read_bytes() == code
            dis = run([build / "binutils/objdump", "-d", "-r", obj])
            (out / (name + ".dis")).write_text(dis)
            assert "RELOCATION RECORDS" not in run(
                [build / "binutils/objdump", "-r", obj])
            row["gnu_byte_match"] = True
        # Exhaust all 65536 input bit patterns, with guards and unchanged input.
        for base in range(0, 65536, 8):
            original = dict(zip(range(0x1000, 0x1008), range(base, base + 8)))
            original.update(dict.fromkeys(range(0x2000, 0x2008), 0xCAFE))
            original.update({0x0FFF: 0xA55A, 0x1008: 0xA55A,
                             0x1FFF: 0xA55A, 0x2008: 0xA55A})
            result, ar, stores = model(code, original.copy(), [0x1000, 0x2000] + [0] * 6)
            expected = original.copy()
            expected.update({0x2000 + i: (base + i + delta) % 65536 for i in range(8)})
            assert result == expected
            assert ar == [0x1008, 0x2008] + [0] * 6
            assert stores == list(range(0x2000, 0x2008))
        row["model_input_values"] = 65536
        rows.append(row)
    # Cover every register/immediate combination in the deliberately small ISA.
    coverage = ["NOP", "RET"]
    coverage += [f"MOV *AR{a}+,T{t}" for a in range(8) for t in range(4)]
    coverage += [f"MOV T{t},*AR{a}+" for a in range(8) for t in range(4)]
    coverage += [f"ADD #{k},T{t}" for k in range(16) for t in range(4)]
    source = " .text\n" + "\n".join(" " + x for x in coverage) + "\n"
    if args.build:
        (out / "coverage.s").write_text(source)
        run([build / "gas/as-new", out / "coverage.s", "-o", out / "coverage.o"])
        run([build / "binutils/objcopy", "-O", "binary", "-j", ".text",
             out / "coverage.o", out / "coverage.bin"])
        assert (out / "coverage.bin").read_bytes() == encode(source)
    rejected = ["B target", "CALL #0", "ADD #16,T0", "MOV *AR8+,T0",
                "MOV *AR0+,T4", "MOV T0,*AR1-", "RESET", ".word 0"]
    for source in rejected:
        try:
            encode(source)
        except ValueError:
            continue
        raise AssertionError(f"accepted unsupported syntax: {source}")
    result = {"status": "PASS", "hardware_execution": False,
              "scope": "byte encoding and restricted functional model only",
              "kernels": rows, "subset_encoding_cases": len(coverage),
              "unsupported_syntax_rejections": len(rejected)}
    (out / "subset-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
