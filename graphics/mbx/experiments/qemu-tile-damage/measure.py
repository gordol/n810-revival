"""Run on Linux with a pinned revive-n8x0 checkout, patched QEMU and Pillow."""
import argparse
import csv
import io
from pathlib import Path
import struct
import tempfile

from PIL import Image, ImageDraw
from qtest_device import capture, render


def viewport_word(value):
    bits, = struct.unpack('<I', struct.pack('<f', value))
    return f'w 50008000 {bits:x}'


def demo_frame(ppm, dirty):
    with Image.open(io.BytesIO(ppm)) as image:
        rgb = image.convert('RGB').resize((192, 192), Image.Resampling.NEAREST)
    frame = Image.new('RGB', (408, 232), '#121820')
    frame.paste(rgb, (8, 32))
    frame.paste(rgb, (208, 32))
    pen = ImageDraw.Draw(frame)
    pen.text((8, 9), 'QEMU framebuffer', fill='white')
    pen.text((208, 9), f'Selected tiles: {len(dirty)} / 16', fill='white')
    for x, y in dirty:
        left, top = 208 + 48*x, 32 + 48*y
        pen.rectangle((left, top, left+47, top+47), outline='#67d8cd', width=2)
    return frame


DRAG_CENTERS = [(8,8), (12,8), (16,12), (20,16), (28,24), (44,40), (56,56), (8,8)]


def measure(repo, qemu, out):
    previous = None
    animation = []
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for frame, (x,y) in enumerate(DRAG_CENTERS):
            trace, reference = capture(repo, Path(directory), (x,y))
            lines = trace.splitlines()
            header = lines.index('w 50008000 53')
            start = next(i for i,line in enumerate(lines) if line.startswith('w 50008000 '))
            end = next(i for i in range(header,len(lines)) if lines[i].startswith('r 5000012c'))
            if previous is None:
                template = lines[start:end]
            else:
                template[header+2-start] = viewport_word(x)
                template[header+3-start] = viewport_word(y)
            assert template == lines[start:end]
            replay = '\n'.join(lines[:start]+template+lines[end:])
            tiles = {(px//16,py//16) for px in range(x-8,x+8) for py in range(y-8,y+8)}
            if previous is None:
                image, full, _ = render(qemu,trace)
                assert image == reference
                selected = {(col,row) for col in range(4) for row in range(4)}
            else:
                selected = tiles | last_tiles
                for repeat in range(4):
                    for mode in ((0,1) if (frame+repeat)%2 else (1,0)):
                        if mode:
                            image, partial, dirty_us = render(qemu,replay,previous,selected)
                        else:
                            full_image, full, full_us = render(qemu,trace)
                    assert image == full_image == reference
                    assert partial == full and full != previous
                    rows.append((frame,repeat,x,y,len(selected),len(template),full_us,dirty_us))
            animation.append(demo_frame(image,selected))
            previous,last_tiles = full,tiles
    out.mkdir(parents=True,exist_ok=True)
    with (out/'measurements.csv').open('w',newline='') as f:
        writer = csv.writer(f,lineterminator='\n')
        writer.writerow(('move','repeat','x','y','selected_tiles','stream_words','full_us','damage_us'))
        writer.writerows(rows)
    animation[0].save(out/'drag.gif',save_all=True,append_images=animation[1:],duration=450,loop=0)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo','qemu','out'):
        parser.add_argument(name,type=Path)
    args = parser.parse_args()
    measure(args.repo.resolve(),args.qemu.resolve(),args.out)
