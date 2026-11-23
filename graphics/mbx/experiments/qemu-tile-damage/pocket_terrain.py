"""Time Pocket terrain lighting updates through ANSI generation on the host."""
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import zlib


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "pocket/shell"))
    from core import Host
    from model_scene import frame

    width, height = 80, 24
    size = 129
    with tempfile.TemporaryDirectory() as directory:
        # A generated hill gives every checkout the same terrain input.
        root = Path(directory)
        metadata = dict(nx=size, nz=size, latitude_first=46.6,
                        longitude_step=0.004, latitude_step=0.004)
        heights = [round(350 + 3250 * math.exp(-((x-64)**2 + (z-72)**2)/480))
                   for z in range(size) for x in range(size)]
        (root / "tahoma-3dep.json").write_text(json.dumps(metadata))
        (root / "tahoma-3dep.i16.zlib").write_bytes(
            zlib.compress(struct.pack(f"<{len(heights)}h", *heights)))
        os.environ["POCKET_DATA_ROOT"] = directory
        host = Host(width, height, [])

        def draw(age):
            scene = frame(width, height, age=age)
            host.background(host.scene_cells(scene))
            output, changed, _ = host.flush(width * height)
            return len(output.encode()), changed

        draw(35000)
        frames = 24
        start = time.perf_counter()
        updates = [draw(35000 + 120 * i) for i in range(1, frames + 1)]
        seconds = time.perf_counter() - start
        changed = sum(count > 0 for _, count in updates)
        print(json.dumps(dict(frames=frames, changed_frames=changed,
                              seconds=seconds, fps=frames/seconds,
                              ansi_bytes=sum(n for n, _ in updates))))
        if changed != frames:
            raise RuntimeError("some timed updates produced no changed cells")


if __name__ == "__main__":
    main()
