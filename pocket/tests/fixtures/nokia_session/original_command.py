"""Reviewed original command; fixture only, never a device launcher."""
import os
from pathlib import Path
import stat

ASSETS = Path('/usr/local/share/n810-pocket')

def command():
    result = ['/usr/bin/python3', '-I', str(ASSETS / 'demo.py'),
            '--native', str(ASSETS / 'native/build-host/Linux-armv6l-cpython-311/_cellengine.abi3.so'),
            '--device-radio', '--native-stations', '--station-db',
            '/home/nokia/.local/state/n810-aprs/directory.sqlite3',
            '--touch-device', '/dev/input/n810-touch', '--touch-calibration',
            '/home/nokia/.local/state/current-world/touch-calibration.json',
            '--touch-display', '800x480', '--touch-rotation', '0']
    inherited = os.environ.get('N810_KEYBOARD_FD')
    if inherited is not None:
        if not inherited.isascii() or not inherited.isdecimal() or not 3<=int(inherited)<=65535:
            raise ValueError('Invalid inherited keyboard descriptor')
        info=os.fstat(int(inherited))
        if not stat.S_ISCHR(info.st_mode) or os.major(info.st_rdev)!=13 or not 64<=os.minor(info.st_rdev)<=255:
            raise ValueError('Inherited descriptor is not a Linux input device')
        result+=['--keyboard-fd',inherited]
    return result
