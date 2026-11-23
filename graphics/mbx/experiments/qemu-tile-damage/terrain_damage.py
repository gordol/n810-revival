"""Compare full and damage redraws of a synthetic Gaussian hill in N810 QEMU."""
import argparse
import csv
import io
import math
from pathlib import Path
import sys
import tempfile
import time

from PIL import Image

from qtest_device import capture, render

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'pocket/shell'))
from geometry import HeightField, Vec


def projected_mesh(mesh, angle):
    vertices = []
    for x, height, z in mesh.vertices:
        side = x * math.cos(angle) - z * math.sin(angle)
        depth = x * math.sin(angle) + z * math.cos(angle)
        green = round(70 + 150 * height)
        color = int.from_bytes(bytes((45, green, 48, 255)), 'little')
        vertices.append((side * .68, depth * .32 + height * .65 - .2,
                         .5 - depth * .20, color))
    return [vertices[i] for triangle in mesh.triangles for i in triangle[:3]]


def measure(repo, qemu, output):
    heights = tuple(math.exp(-((x-3)**2 + (z-4)**2)/4) for z in range(9) for x in range(9))
    mesh = HeightField(9, 9, Vec(-1, 0, -1), .25, .25, heights).mesh()
    # Every projected vertex stays inside [16,48) squared for every camera angle.
    tiles = {(x, y) for y in (1, 2) for x in (1, 2)}
    images = []
    with tempfile.TemporaryDirectory() as tmp, output.open('w') as file:
        writer = csv.writer(file, lineterminator='\n')
        writer.writerow(('frame', 'pair', 'mode', 'kick_cpu_us', 'replay_wall_ms'))
        previous = None
        for frame in range(5):
            trace, reference = capture(repo, Path(tmp), (32, 32),
                                       projected_mesh(mesh, frame * .21), scale=16)
            if previous is None:
                image, previous, _ = render(qemu, trace)
                assert image == reference
                images.append(Image.open(io.BytesIO(image)).convert("RGB"))
                continue
            for pair in range(4):
                modes = ('full', 'damage') if (frame + pair)%2 else ('damage', 'full')
                for mode in modes:
                    start = time.perf_counter_ns()
                    image, surface, kick = (render(qemu, trace) if mode == 'full'
                                            else render(qemu, trace, previous, tiles))
                    elapsed = (time.perf_counter_ns() - start) / 1e6
                    assert image == reference and surface != previous
                    if mode == modes[0]:
                        first_surface = surface
                    else:
                        assert surface == first_surface
                    writer.writerow((frame, pair, mode, kick, elapsed))
            previous = surface
            images.append(Image.open(io.BytesIO(image)).convert("RGB"))
    frames = [im.resize((256, 256), Image.Resampling.NEAREST) for im in images]
    frames[0].save(output.with_suffix(".gif"), save_all=True, append_images=frames[1:],
                   duration=350, loop=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'qemu', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    measure(args.repo.resolve(), args.qemu.resolve(), args.output)
