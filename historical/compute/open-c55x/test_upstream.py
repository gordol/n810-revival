#!/usr/bin/env python3
"""Record upstream encoding and relocation results without hiding known faults."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path, help="workspace made by build.py")
    args = parser.parse_args()
    root = args.workspace.resolve()
    tests = root / "source/gas/testsuite/gas/tic55x"
    out = root / "upstream-tests"
    out.mkdir(exist_ok=True)
    rows = []
    # A text regex in the old .d fixtures mishandles literal || and uns(...).
    # Compare byte encodings and relocation rows as separate evidence instead.
    instruction = re.compile(r"^\s*([0-9a-f]+):\s+([0-9a-f]+)\s", re.M)
    relocation = re.compile(r"^\s*([0-9a-f]+): (R_\w+)\s+(\w+)", re.M)
    for expected in sorted(tests.glob("*.d")):
        name = expected.stem
        obj = out / (name + ".o")
        assembled = subprocess.run([str(root / "build/gas/as-new"), "-I", str(tests),
                                    str(tests / (name + ".s")), "-o", str(obj)],
                                   capture_output=True, text=True, timeout=30)
        row = {"name": name, "assemble_exit": assembled.returncode,
               "messages": assembled.stdout + assembled.stderr}
        if assembled.returncode == 0:
            actual = subprocess.check_output([str(root / "build/binutils/objdump"),
                                               "-d", "-r", str(obj)], text=True, timeout=30)
            (out / (name + ".dis")).write_text(actual)
            want = instruction.findall(expected.read_text())
            got = instruction.findall(actual)
            row.update(instructions_expected=len(want), instructions_actual=len(got),
                       encoding_match=want == got,
                       encoding_differences=[{"expected": x, "actual": y}
                                             for x, y in zip(want, got) if x != y],
                       expected_relocations=relocation.findall(expected.read_text()),
                       actual_relocations=relocation.findall(actual))
        rows.append(row)
    result = {"status": "LIMITED", "hardware_execution": False, "suites": rows,
              "interpretation": "Six data-operation suites match; program-control fixups/relocations fail. Do not use as a general linker or firmware toolchain."}
    (out / "upstream-validation.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if len(rows) != 7 or any(r["assemble_exit"] for r in rows):
        raise SystemExit("unexpected suite or assembly failure")
    for row in rows:
        if row["name"] != "program_control" and not row["encoding_match"]:
            raise SystemExit("unexpected data-operation encoding failure")
    control = next(r for r in rows if r["name"] == "program_control")
    if len(control["encoding_differences"]) != 4 or len(control["expected_relocations"]) != 4 or control["actual_relocations"]:
        raise SystemExit("program-control result changed: inspect before updating evidence")


if __name__ == "__main__":
    main()
