"""Time a continuous MBX animation submitted by an emulated ARM1136."""
import argparse
import csv
from pathlib import Path
import struct
import subprocess
import tempfile
import time
from threading import Timer


from gears_mesh import load_mesh
from measure import DRAG_CENTERS
from qtest_device import capture


TRACE_BASE = 0x83000000
REFERENCE_BASE = 0x86000000
RECORD = struct.Struct('<III')


def encode(lines, size, dirty=None):
    region_start = (0x80010000 + 4*size*size + 0xffff) & ~0xffff
    padded = ((size//16 + 3)//4)*4
    region_end = region_start + padded*padded*8
    stream = bytearray()
    # The page table, MMU and initial surface clear precede free-list setup.
    # A flat background clears each rendered tile; skipped tiles retain RAM.
    for line in lines:
        op, address, value = line.split()
        address, value = int(address, 16), int(value, 16)
        if (dirty is not None and op == 'm' and region_start <= address < region_end
                and address % 8 == 0 and value & (1 << 30)):
            if (value & 255, (value >> 8) & 255) not in dirty:
                value |= 1 << 25
        stream.extend(RECORD.pack(int(op == 'r'), address, value))
    return stream


def run_guest(qemu, player, trace, references):
    args = [qemu, '-M', 'n810', '-display', 'none', '-serial', 'none',
            '-monitor', 'none', '-semihosting-config', 'enable=on,target=native']
    for path, address in ((player, 0x82000000), (trace, TRACE_BASE),
                          (references, REFERENCE_BASE)):
        if path is not None:
            loader = f'loader,file={path},addr={address:#x},force-raw=on'
            args.extend(['-device', loader + (',cpu-num=0' if path == player else '')])
    begin = end = None
    with subprocess.Popen(args, stderr=subprocess.PIPE, text=True) as proc:
        deadline = Timer(120, proc.kill)
        deadline.start()
        try:
            for line in proc.stderr:
                if line.strip() == 'MBX_BEGIN':
                    begin = time.perf_counter()
                elif line.strip() == 'MBX_END':
                    end = time.perf_counter()
                elif line.strip() == 'MBX_FAILED':
                    raise RuntimeError('guest register or framebuffer mismatch')
            if proc.wait() or begin is None or end is None or begin >= end:
                raise RuntimeError('guest did not complete the animation')
        finally:
            deadline.cancel()
    return end - begin


def scene_frames(args, work, size):
    if args.scene == 'triangle':
        for x, y in DRAG_CENTERS:
            selected = {(px//16, py//16) for px in range(x-8, x+8) for py in range(y-8, y+8)}
            trace, ppm = capture(args.repo, work, (x,y), flat_background=True)
            yield trace, ppm, selected
        return
    files = sorted(args.folder.glob('live-*.float'), key=lambda p: int(p.stem.split('-')[-1]))
    if not 2 <= len(files) <= 48:
        raise ValueError('need 2 to 48 consecutive captured frames')
    if [p.name for p in files] != [f'live-{i}.float' for i in range(1, len(files)+1)]:
        raise ValueError('missing frame in capture sequence')
    for path in files:
        vertices, tiles = load_mesh(path, size)
        trace, ppm = capture(args.repo, work, (size//2, size//2), vertices, scale=size//2,
                             size=size, flat_background=True)
        yield trace, ppm, tiles


def measure(args, work):
    obj, player = work/'player.o', work/'player.bin'
    subprocess.run(['arm-linux-gnueabi-as', Path(__file__).with_name('animation_player.S'),
                    '-o', obj], check=True)
    subprocess.run(['arm-linux-gnueabi-objcopy', '-O', 'binary', '-j', '.text', obj, player], check=True)
    refs = work/'references.bin'
    size = 64 if args.scene == 'triangle' else getattr(args, 'size', 400)
    pixels = size*size
    streams = {mode: [] for mode in ('full', 'damage')}
    previous_tiles = set()
    with refs.open('wb') as output:
        for i, (trace, ppm, tiles) in enumerate(scene_frames(args, work, size)):
            setup, marker, frame = trace.partition('w 50000824 ')
            if not marker:
                raise ValueError('trace missing free-list setup')
            if i == 0:
                board_setup = encode(setup.splitlines(), size)
            lines = (marker + frame).splitlines()
            full = encode(lines, size)
            streams['full'].append(full)
            streams['damage'].append(encode(lines, size, tiles | previous_tiles) if i else full)
            previous_tiles = tiles
            rgb = ppm.split(b'\n', 3)[3]
            if len(rgb) != pixels*3:
                raise ValueError('invalid reference size')
            bgrx = bytearray(pixels*4)
            for channel in range(3):
                bgrx[channel::4] = rgb[2-channel::3]
            output.write(bgrx)
    repeats = 32 if args.scene == 'triangle' else 1
    traces = {}
    for mode, frames in streams.items():
        for validate in (True, False):
            path = work/f'{mode}-{validate}.bin'
            with path.open('wb') as output:
                output.write(board_setup)
                output.write(RECORD.pack(2, 0, 1 if validate else repeats))
                for i, frame in enumerate(frames):
                    output.write(frame)
                    if validate:
                        output.write(RECORD.pack(4, REFERENCE_BASE + i*pixels*4, pixels))
                output.write(RECORD.pack(3, 0, 0))
                output.write(RECORD.pack(5, 0, 0))
            if TRACE_BASE+path.stat().st_size > REFERENCE_BASE:
                raise ValueError('trace exceeds guest memory')
            if validate:
                run_guest(args.qemu, player, path, refs)
            else:
                traces[mode] = path
    with (args.folder/'animation.csv').open('w', newline='') as output:
        writer = csv.writer(output, lineterminator='\n')
        writer.writerow(('pair', 'mode', 'frames', 'wall_seconds', 'fps'))
        count = len(streams['full'])*repeats
        for trial in range(4):
            for mode in (('full','damage') if trial%2 == 0 else ('damage','full')):
                duration = run_guest(args.qemu, player, traces[mode], None)
                writer.writerow((trial, mode, count, duration, count/duration))
                output.flush()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('repo', 'qemu', 'folder'):
        parser.add_argument(name, type=lambda value: Path(value).resolve())
    parser.add_argument('--scene', choices=('gears','triangle'), default='gears')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        measure(args, Path(directory))
