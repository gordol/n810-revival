import argparse
import csv
import io
from pathlib import Path
import tempfile
import time
from PIL import Image, ImageDraw
from qtest_device import capture, render

from gears_mesh import load_mesh

def measure(repo, qemu, folder, work, size):
    rows = []
    frames = []
    prior = None
    prior_tiles = set()
    for step in range(6):
        vertices, tiles = load_mesh(folder / f'live-{step+1}.float', size)
        trace, reference = capture(repo, work, (size//2, size//2), vertices, scale=size//2, size=size)
        if prior is None:
            full, prior, _ = render(qemu, trace, size=size)
            assert full == reference
            damage = full
        else:
            selected = tiles | prior_tiles
            for trial in range(4):
                modes = ('full', 'damage') if (step+trial)%2 else ('damage', 'full')
                for mode in modes:
                    start = time.perf_counter()
                    if mode == 'full':
                        full, full_pixels, kick = render(qemu, trace, size=size)
                    else:
                        damage, damage_pixels, kick = render(qemu, trace, prior, selected, size=size)
                    rows.append((step, trial, mode, len(selected), kick, time.perf_counter()-start))
                assert full_pixels == damage_pixels and full_pixels != prior
                assert full == damage == reference
            prior = full_pixels
        prior_tiles = tiles
        panel = 192 if size == 64 else size
        image = Image.new('RGB', (2*(panel+8), panel+28), '#14171c')
        for i, (title, pixels) in enumerate((('Full redraw', full), ('Tile damage', damage))):
            with Image.open(io.BytesIO(pixels)) as src:
                image.paste(src.resize((panel, panel), Image.Resampling.NEAREST), (4+i*(panel+8), 24))
            ImageDraw.Draw(image).text((5+i*(panel+8), 5), title, fill='white')
        frames.append(image)
    with (folder/f'spinning-gears-{size}.csv').open('w', newline='') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(('step', 'trial', 'mode', 'selected_damage_tiles', 'kick_us', 'replay_seconds'))
        writer.writerows(rows)
    frames[0].save(folder/f'spinning-gears-{size}.gif', save_all=True, append_images=frames[1:],
                   duration=400, loop=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Replay six glxgears feedback frames in N810 QEMU.')
    for name in ('repo', 'qemu', 'folder'):
        parser.add_argument(name, type=Path)
    parser.add_argument('--size', type=int, choices=(64, 400), default=400)
    parser.add_argument('--isolated', action='store_true', help='run the historical per-frame GIF and timing probe')
    args = parser.parse_args()
    args.scene = 'gears'
    with tempfile.TemporaryDirectory() as work:
        if args.isolated:
            measure(args.repo.resolve(), args.qemu.resolve(), args.folder.resolve(), Path(work), args.size)
        else:
            from animation import measure as measure_animation
            measure_animation(args, Path(work))
