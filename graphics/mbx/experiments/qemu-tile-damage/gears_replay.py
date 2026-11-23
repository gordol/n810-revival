import argparse
import csv
import io
from pathlib import Path
import tempfile
import time
from PIL import Image, ImageDraw
from qtest_device import capture, render

import array
import math

def load_mesh(path):
    words = array.array('f')
    words.frombytes(path.read_bytes())
    vertices = []
    tiles = set()
    i = 0
    while i < len(words):
        token, count = words[i:i+2]
        assert token == 0x703 and int(count) >= 3
        i += 2
        polygon = []
        for _ in range(int(count)):
            x,y,z,r,g,b,a = words[i:i+7]
            i += 7
            color = sum(round(255*c) << (8*j) for j,c in enumerate((r,g,b,a)))
            polygon.append((x/200-1, y/200-1,z*2-1,color))
        for j in range(1,len(polygon)-1):
            tri = [polygon[0],polygon[j],polygon[j+1]]
            vertices.extend(tri)
            xs = [32 + 32*v[0] for v in tri]
            ys = [32 - 32*v[1] for v in tri]
            # Conservative box with a pixel margin for subpixel rounding.
            for tx in range(max(0,math.floor((min(xs)-1)/16)),min(3,math.floor((max(xs)+1)/16))+1):
                for ty in range(max(0,math.floor((min(ys)-1)/16)),min(3,math.floor((max(ys)+1)/16))+1):
                    tiles.add((tx,ty))
    return vertices,tiles

def measure(repo, qemu, folder, work):
    rows = []
    frames = []
    prior = None
    prior_tiles = set()
    for step in range(6):
        vertices, tiles = load_mesh(folder / f'live-{step+1}.float')
        trace, reference = capture(repo, work, (32, 32), vertices, scale=32)
        if prior is None:
            full, prior, _ = render(qemu, trace)
            assert full == reference
            damage = full
        else:
            selected = tiles | prior_tiles
            for trial in range(4):
                modes = ('full', 'damage') if (step+trial)%2 else ('damage', 'full')
                for mode in modes:
                    start = time.perf_counter()
                    if mode == 'full':
                        full, full_pixels, kick = render(qemu, trace)
                    else:
                        damage, damage_pixels, kick = render(qemu, trace, prior, selected)
                    rows.append((step, trial, mode, len(selected), kick, time.perf_counter()-start))
                assert full_pixels == damage_pixels and full_pixels != prior
                assert full == damage == reference
            prior = full_pixels
        prior_tiles = tiles
        image = Image.new('RGB', (400, 220), '#14171c')
        for i, (title, pixels) in enumerate((('Full redraw', full), ('Tile damage', damage))):
            with Image.open(io.BytesIO(pixels)) as src:
                image.paste(src.resize((192, 192), Image.Resampling.NEAREST), (4+i*200, 24))
            ImageDraw.Draw(image).text((5+i*200, 5), title, fill='white')
        frames.append(image)
    with (folder/'spinning-gears.csv').open('w', newline='') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(('step', 'trial', 'mode', 'selected_damage_tiles', 'kick_us', 'replay_seconds'))
        writer.writerows(rows)
    frames[0].save(folder/'spinning-gears.gif', save_all=True, append_images=frames[1:],
                   duration=400, loop=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Replay six glxgears feedback frames in N810 QEMU.')
    for name in ('repo', 'qemu', 'folder'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as work:
        measure(args.repo.resolve(), args.qemu.resolve(), args.folder.resolve(), Path(work))
