#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Handle the N810's LCD brightness keys and short Power press."""
import os
from pathlib import Path
import select
import struct
import subprocess
import time

EVENT = struct.Struct('=llHHi')  # 32-bit N810 input_event
EV_KEY = 1
KEY_POWER = 116
KEY_BRIGHTNESSDOWN = 224
KEY_BRIGHTNESSUP = 225
INPUT_NAMES = {'retu-pwrbutton', 'Internal keyboard', 'N810 internal keyboard'}


def brightness_change(backlight, code):
    maximum = int((backlight / 'max_brightness').read_text())
    value = int((backlight / 'brightness').read_text())
    if maximum < 1 or not 0 <= value <= maximum:
        raise ValueError('Invalid LCD brightness range')
    step = max(1, maximum // 10)
    value = min(maximum, max(1, value + (step if code == KEY_BRIGHTNESSUP else -step)))
    (backlight / 'brightness').write_text(str(value) + '\n')


def devices():
    found = {}
    for event in Path('/sys/class/input').glob('event*'):
        try:
            name = (event / 'device/name').read_text().strip()
        except OSError:
            continue
        if name in INPUT_NAMES:
            found[event.name] = (name, Path('/dev/input') / event.name)
    return found


def main():
    if os.geteuid() != 0 or struct.calcsize('P') != 4:
        raise SystemExit('Run as root on the 32-bit N810')
    backlights = [p for p in Path('/sys/class/backlight').iterdir()
                  if (p / 'brightness').exists() and (p / 'max_brightness').exists()]
    if len(backlights) != 1:
        raise SystemExit('Expected one LCD backlight')
    backlight = backlights[0]
    poller = select.poll()
    opened = {}
    menu = None
    pressed = None
    while True:
        for event, (name, path) in devices().items():
            if event in opened:
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC)
            except OSError:
                continue
            opened[event] = (fd, name)
            poller.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
        for fd, flags in poller.poll(1000):
            if flags & (select.POLLHUP | select.POLLERR) or not flags & select.POLLIN:
                for event, (current, _) in list(opened.items()):
                    if current == fd:
                        poller.unregister(fd)
                        os.close(fd)
                        del opened[event]
                        break
                continue
            try:
                data = os.read(fd, EVENT.size * 32)
            except OSError:
                data = b''
            if not data or len(data) % EVENT.size:
                continue
            name = next(name for current, name in opened.values() if current == fd)
            for offset in range(0, len(data), EVENT.size):
                _, _, kind, code, value = EVENT.unpack_from(data, offset)
                if kind != EV_KEY:
                    continue
                if name == 'retu-pwrbutton' and code == KEY_POWER:
                    if value == 1:
                        pressed = time.monotonic()
                    elif value == 0 and pressed is not None:
                        short = time.monotonic() - pressed < 1.5
                        pressed = None
                        if short and (menu is None or menu.poll() is not None):
                            menu = subprocess.Popen(['/usr/bin/openvt', '-s', '-w', '--',
                                                     '/usr/local/sbin/n810-power-overlay'],
                                                    stdin=subprocess.DEVNULL)
                elif name != 'retu-pwrbutton' and value == 1 and code in (KEY_BRIGHTNESSUP, KEY_BRIGHTNESSDOWN):
                    brightness_change(backlight, code)
        for event, (fd, _) in list(opened.items()):
            if not (Path('/dev/input') / event).exists():
                poller.unregister(fd)
                os.close(fd)
                del opened[event]


if __name__ == '__main__':
    main()
