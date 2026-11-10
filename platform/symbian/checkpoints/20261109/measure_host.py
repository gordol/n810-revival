"""Run inside the Linux host VM; measure one private ChessGenius control.

No device access. The framebuffer sink is CPU-rendered RGBA, not LCD proof.
"""
import argparse
import json
import mmap
import os
from pathlib import Path
import struct
import time

p = argparse.ArgumentParser()
p.add_argument("root", type=Path)
p.add_argument("pid", type=int)
p.add_argument("key", choices=["down", "up", "select"])
p.add_argument("x", type=int)
p.add_argument("y", type=int)
a = p.parse_args()
proc = Path("/proc") / str(a.pid)
argv = (proc / "cmdline").read_bytes().split(b"\0")
assert Path(os.fsdecode(argv[0])).name == "symbian-host-runtime"
assert Path(os.fsdecode(argv[1])).resolve() == a.root.resolve()
hz = os.sysconf("SC_CLK_TCK")

def sample():
    fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
    return dict(cpu_ticks=int(fields[11]) + int(fields[12]),
                minor_faults=int(fields[7]), major_faults=int(fields[9]),
                rss_kib=int(fields[21]) * os.sysconf("SC_PAGE_SIZE") // 1024,
                start_ticks=int(fields[19]))

with (a.root / "host-frame.rgba").open("rb") as f:
    with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as frame:
        def pixel():
            generation, w, h, _ = struct.unpack_from("4I", frame)
            if generation & 1:
                return None
            assert 0 <= a.x < w and 0 <= a.y < h
            offset = 16 + 4 * (a.y * w + a.x)
            value = frame[offset:offset + 4]
            return value if struct.unpack_from("I", frame)[0] == generation else None

        before = pixel()
        assert before is not None
        first = sample()
        control = a.root / "control-keys"
        temporary = a.root / ("control-key-tmp-" + str(os.getpid()))
        start = time.monotonic()
        with temporary.open("x") as out:
            out.write(a.key + "\n")
        try:
            os.link(temporary, control)
        finally:
            temporary.unlink()
        changed = consumed = None
        while time.monotonic() - start < 8:
            if consumed is None and not control.exists():
                consumed = time.monotonic() - start
            value = pixel()
            if changed is None and value is not None and value != before:
                changed = time.monotonic() - start
            time.sleep(.025)
        after = sample()
        assert first["start_ticks"] == after["start_ticks"]
        print(json.dumps(dict(key=a.key, pixel=[a.x, a.y],
              first_pixel_change_s=changed, queue_consumed_s=consumed,
              window_s=time.monotonic() - start,
              parent_cpu_s=(after["cpu_ticks"] - first["cpu_ticks"]) / hz,
              before=first, after=after,
              presentation="CPU RGBA memory sink; not physical LCD")))
