#!/usr/bin/env python3
"""Bounded RGB checks on an operator-selected disposable Linux VT."""
import argparse
from contextlib import contextmanager
import ctypes
import fcntl
import json
import os
from pathlib import Path
import signal
import statistics
import struct
import termios
import time

RELEASE = '5.15.86-n810-console-rgb1+'
BG, FG = (17, 57, 89), (245, 210, 104)


def rgb565(rgb):
    r, g, b = rgb
    return (r >> 3) << 11 | (g >> 2) << 5 | b >> 3


def sgr(rgb, background=True):
    return '\x1b[%d;2;%d;%d;%dm' % ((48 if background else 38,) + rgb)


class FontOp(ctypes.Structure):
    _fields_ = [(x, ctypes.c_uint) for x in
                ('op', 'flags', 'width', 'height', 'charcount')] + [('data', ctypes.c_void_p)]


class Console:
    def __init__(self, vt):
        self.vt = vt
        self.control = os.open('/dev/tty0', os.O_RDWR | os.O_NOCTTY)
        self.fd = os.open('/dev/tty%d' % vt, os.O_RDWR | os.O_NOCTTY)

    def close(self):
        os.close(self.fd)
        os.close(self.control)

    def active(self):
        return struct.unpack('HHH', fcntl.ioctl(self.control, 0x5603, b'\0'*6))[0]

    def switch(self, vt):
        fcntl.ioctl(self.control, 0x5606, vt)
        fcntl.ioctl(self.control, 0x5607, vt)

    def size(self):
        return struct.unpack('HHHH', fcntl.ioctl(self.fd, termios.TIOCGWINSZ, b'\0'*8))[:2]

    def font(self, saved=None, height=None):
        data = ctypes.create_string_buffer(saved['data'] if saved else b'\0'*65536)
        op = FontOp(0 if saved else 1, 0, saved['width'] if saved else 32,
                    height or (saved['height'] if saved else 32),
                    saved['charcount'] if saved else 512, ctypes.addressof(data))
        raw = bytearray(ctypes.string_at(ctypes.byref(op), ctypes.sizeof(op)))
        fcntl.ioctl(self.fd, 0x4B72, raw, True)
        ctypes.memmove(ctypes.byref(op), bytes(raw), len(raw))
        count = ((op.width+7)//8)*32*op.charcount
        return dict(width=op.width, height=op.height, charcount=op.charcount,
                    data=data.raw[:count])

    def write(self, text):
        if self.active() != self.vt:
            raise RuntimeError('Active VT changed; stopping test writes')
        data = text.encode('ascii')
        while data:
            data = data[os.write(self.fd, data):]

    def frame(self):
        time.sleep(.06)
        if self.active() != self.vt:
            raise RuntimeError('Foreground changed before framebuffer read')
        with open('/dev/fb0', 'rb', buffering=0) as stream:
            data = stream.read(800*480*2)
        if self.active() != self.vt:
            raise RuntimeError('Foreground changed during framebuffer read')
        if len(data) != 800*480*2:
            raise RuntimeError('Incomplete framebuffer read')
        return data

    def cell(self, row, col):
        rows, cols = self.size()
        font = self.font()
        w, h = font['width'], font['height']
        if not (0 <= row < rows and 0 <= col < cols and
                (col+1)*w <= 800 and (row+1)*h <= 480):
            raise RuntimeError('Cell outside visible framebuffer')
        frame = self.frame()
        return [struct.unpack_from('<H', frame, (y*800+x)*2)[0]
                for y in range(row*h, (row+1)*h) for x in range(col*w, (col+1)*w)]


@contextmanager
def isolated(console, original, saved):
    failure = []
    try:
        console.switch(console.vt)
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        for name, operation in (
            ('font', lambda: console.font(saved)),
            ('scratch reset', lambda: console.write('\x1b[0m\x1b[r\x1b[?25h')),
            ('original VT', lambda: console.switch(original)),
        ):
            try:
                operation()
            except BaseException as exc:
                failure.append(name+': '+str(exc))
        if failure:
            raise RuntimeError('Restore errors: '+'; '.join(failure))


def unused(vt):
    target = os.makedev(4, vt)
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = path.read_text().rsplit(')', 1)[1].split()
            if int(fields[4]) == target:
                raise RuntimeError('tty%d has a controlling process: %s' % (vt, path.parent.name))
        except (FileNotFoundError, ProcessLookupError):
            pass


def preflight(args):
    if os.uname().sysname != 'Linux' or os.uname().release != RELEASE:
        raise RuntimeError('Requires the reviewed RAM candidate kernel')
    if os.geteuid() != 0 or not 2 <= args.vt <= 12 or args.vt == args.expect_active:
        raise RuntimeError('Root and a separate scratch VT 2..12 required')
    if 'vt.rgb=1' not in Path('/proc/cmdline').read_text().split():
        raise RuntimeError('RGB-on kernel required; no reboot performed by this tool')
    fb = Path('/sys/class/graphics/fb0')
    for name, expected in (('virtual_size', '800,480'), ('bits_per_pixel', '16'), ('stride', '1600')):
        if (fb/name).read_text().strip() != expected:
            raise RuntimeError('Unexpected framebuffer '+name)
    if (fb/'blank').read_text().strip() != '0':
        raise RuntimeError('Display blanked; operator must arrange screen readiness')
    unused(args.vt)


def suite(c, result, resize, view_seconds=0):
    checks = result['checks']

    def check(name, actual, expected):
        checks.append(dict(name=name, actual=actual, expected=expected, passed=actual == expected))
        if actual != expected:
            raise RuntimeError('Failed: '+name)

    c.write('\x1b[0m\x1b[?6l\x1b[r\x1b[2J\x1b[H\x1b[?25l'+sgr(BG)+sgr(FG, False)+
            '\x1b[5;5H '+ '\x1b[5;5H')
    hidden = c.cell(4, 4)
    adjacent = c.cell(4, 5)
    check('hidden cursor background', set(hidden) == {rgb565(BG)}, True)
    c.write('\x1b[?25h')
    visible = hidden
    for _ in range(8):
        visible = c.cell(4, 4)
        if visible != hidden:
            break
    check('cursor changes only within RGB pair', visible != hidden and
          set(visible) <= {rgb565(BG), rgb565(FG)}, True)
    check('cursor preserves adjacent cell', c.cell(4, 5), adjacent)
    c.write('\x1b[?25l')
    check('cursor hide restores RGB cell', c.cell(4, 4), hidden)
    c.write('\x1b[2;4r\x1b[2;1H'+sgr((255, 0, 0))+' '*8+
            '\x1b[3;1H'+sgr((0, 255, 0))+' '*8+
            '\x1b[4;1H'+sgr((0, 0, 255))+' '*8+'\x1b[4;1H\x1bD')
    check('supported scroll moves green row', set(c.cell(1, 2)), {rgb565((0, 255, 0))})
    check('supported scroll moves blue row', set(c.cell(2, 2)), {rgb565((0, 0, 255))})
    c.write('\x1b[r')
    saved = c.font()
    if resize:
        height = 16 if saved['height'] != 16 else 12
        before = c.size()
        c.font(saved, height)
        after = c.size()
        check('font height applied on scratch VT', c.font()['height'], height)
        check('font change recalculates rows', after[0], 480//height)
        if before == after:
            raise RuntimeError('Font resize did not change geometry')
        c.write('\x1b[2J'+sgr(BG)+'\x1b[3;3H  ')
        check('RGB survives resized geometry', set(c.cell(2, 2)), {rgb565(BG)})
        c.font(saved)
        restored = c.font()
        check('font bitmap/geometry restored', restored == saved and c.size() == before, True)
    else:
        result['font_resize'] = 'not requested'
    rows, cols = c.size()
    timings = {}
    for mode in ('ANSI', 'RGB'):
        style = '\x1b[44;37m' if mode == 'ANSI' else sgr(BG)+sgr(FG, False)
        samples, scroll = [], []
        for _ in range(3):
            payload = '\x1b[0m\x1b[?25l\x1b[H'+style
            payload += ''.join('\x1b[%d;1H%s' % (r, 'X'*min(cols-1, 100))
                               for r in range(1, min(rows-1, 8)+1))
            start = time.monotonic_ns(); c.write(payload)
            samples.append((time.monotonic_ns()-start)/1e6)
            start = time.monotonic_ns()
            c.write(style+'\x1b[2;6r\x1b[6;1H'+'\x1bD'*8+'\x1b[r')
            scroll.append((time.monotonic_ns()-start)/1e6)
        timings[mode] = dict(write_ms=samples, median_write_ms=statistics.median(samples),
                             scroll_write_ms=scroll, median_scroll_write_ms=statistics.median(scroll))
    result['timings'] = timings
    result['selection'] = 'manual only; no shared clipboard change performed'
    if view_seconds:
        c.write('\x1b[0m\x1b[2J\x1b[H\x1b[?25l'+sgr(BG)+sgr(FG, False)+
                'RGB SELECTION CHECK 0123456789\r\n'+
                '\x1b[7mREVERSE SELECTION CHECK\x1b[27m\r\n'+
                '\x1b[0mManual view only; no clipboard operation from harness.')
        time.sleep(view_seconds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--vt', type=int)
    parser.add_argument('--expect-active', type=int)
    parser.add_argument('--font-resize', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--restore-from', type=Path)
    parser.add_argument('--view-seconds', type=int, choices=range(0, 11), default=0)
    args = parser.parse_args()
    if args.restore_from:
        if args.run or os.geteuid() != 0 or os.uname().release != RELEASE:
            parser.error('Restore requires root on reviewed kernel and no --run')
        state = json.loads((args.restore_from/'state.json').read_text())
        if state['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip():
            raise RuntimeError('Saved state belongs to a different boot')
        saved = {k: state[k] for k in ('width', 'height', 'charcount')}
        saved['data'] = (args.restore_from/'font.bin').read_bytes()
        if (not 2 <= state['vt'] <= 12 or not 1 <= state['original_vt'] <= 63 or
            state['vt'] == state['original_vt'] or
            not 1 <= saved['width'] <= 16 or not 1 <= saved['height'] <= 32 or
            saved['charcount'] not in (256, 512) or
            len(saved['data']) != ((saved['width']+7)//8)*32*saved['charcount']):
            raise RuntimeError('Invalid saved restoration state')
        c = Console(state['vt'])
        try:
            with isolated(c, state['original_vt'], saved):
                pass
            if c.font() != saved or c.active() != state['original_vt']:
                raise RuntimeError('Restoration verification failed')
        finally:
            c.close()
        print('Saved scratch font and original foreground VT restored.')
        return
    if not args.run:
        print('Plan only. Requires --run --vt N --expect-active M --output NEW_DIR; '
              'optional --font-resize. See OPERATOR-JOB.txt. No device opened.')
        return
    if args.vt is None or args.expect_active is None or args.output is None:
        parser.error('--run requires --vt, --expect-active and new --output')
    preflight(args)
    c = Console(args.vt)
    result = dict(scope='automated smoke checks only', checks=[], passed=False, restored=False)
    original, saved = None, None
    created_output = False
    try:
        original = c.active()
        if original != args.expect_active:
            raise RuntimeError('Foreground VT differs from approved operator state')
        saved = c.font()
        if saved['width'] > 16 or saved['height'] > 32 or min(c.size()) < 8:
            raise RuntimeError('Unexpected font/console geometry')
        args.output.mkdir()
        created_output = True
        (args.output/'font.bin').write_bytes(saved['data'])
        state = dict(vt=args.vt, original_vt=original, width=saved['width'],
                     height=saved['height'], charcount=saved['charcount'], rows_cols=c.size(),
                     boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        (args.output/'state.json').write_text(json.dumps(state, indent=2)+'\n')

        def stop(signum, frame):
            raise RuntimeError('Stopped by signal %d' % signum)

        for sig in (signal.SIGALRM, signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, stop)
        with isolated(c, original, saved):
            signal.setitimer(signal.ITIMER_REAL, 30)
            suite(c, result, args.font_resize, args.view_seconds)
        result['restored'] = c.active() == original and c.font() == saved
        result['passed'] = result['restored'] and all(x['passed'] for x in result['checks'])
    except BaseException as exc:
        result['error'] = str(exc)
        raise
    finally:
        if original is not None and saved is not None:
            try:
                result['restored'] = c.active() == original and c.font() == saved
            except BaseException as exc:
                result['restore_verification_error'] = str(exc)
        if created_output:
            result['passed'] = result['passed'] and result['restored']
            (args.output/'result.json').write_text(json.dumps(result, indent=2, default=list)+'\n')
        c.close()
    print(json.dumps(result, default=list))


if __name__ == '__main__':
    main()
