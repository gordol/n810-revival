#!/usr/bin/python3
"""Apply the accepted raw-to-pixel calibration as Xorg's normalized matrix."""
import fcntl
import json
import math
import os
from pathlib import Path
import struct
import sys

def matrix(calibration, x_range, y_range):
    width, height = calibration['screen_width'], calibration['screen_height']
    if calibration['version'] != 1 or width != 800 or height != 480:
        raise ValueError('Unsupported touch calibration')
    xmin, xmax = x_range
    ymin, ymax = y_range
    if xmax <= xmin or ymax <= ymin:
        raise ValueError('Invalid input coordinate range')
    a, b, c = calibration['x']
    d, e, f = calibration['y']
    values = [a*(xmax-xmin)/width, b*(ymax-ymin)/width, (a*xmin+b*ymin+c)/width,
              d*(xmax-xmin)/height, e*(ymax-ymin)/height, (d*xmin+e*ymin+f)/height,
              0, 0, 1]
    if not all(math.isfinite(v) for v in values):
        raise ValueError('Non-finite touch calibration')
    return values

def device(name):
    for event in Path('/sys/class/input').glob('event*'):
        if (event/'device/name').read_text().strip() == name:
            return '/dev/input/'+event.name
    raise ValueError(name+' input device not found')

def ranges():
    fd = os.open(device('TSC2005 touchscreen'), os.O_RDONLY | os.O_NONBLOCK)
    try:
        result = []
        for axis in (0, 1):
            data = bytearray(24)
            fcntl.ioctl(fd, 0x80184540+axis, data, True)
            _, low, high, _, _, _ = struct.unpack('6i', data)
            result.append((low, high))
        return result
    finally:
        os.close(fd)

if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit('Usage: xorg-config.py TEMPLATE CALIBRATION.json')
    calibration = json.loads(Path(sys.argv[2]).read_text())
    values = matrix(calibration, *ranges())
    template = Path(sys.argv[1]).read_text()
    replacements = {
        '@KEYBOARD_DEVICE@': device('N810 internal keyboard'),
        '@TOUCH_DEVICE@': device('TSC2005 touchscreen'),
        '@TOUCH_MATRIX@': ' '.join(f'{v:.12g}' for v in values),
    }
    for token, value in replacements.items():
        if template.count(token) != 1:
            raise ValueError('Missing unique template token: '+token)
        template = template.replace(token, value)
    print(template)
