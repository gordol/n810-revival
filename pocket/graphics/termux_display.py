"""Connect Pocket to an existing X display or bring up a local Termux:X11 server."""
import ctypes
import os
from pathlib import Path
import re
import subprocess
import time


def ensure_display():
    display = os.environ.get('DISPLAY') or ':1'
    os.environ['DISPLAY'] = display
    # SDL uses this same X11 connection. A stale socket alone is insufficient.
    try:
        x11 = ctypes.CDLL('libX11.so')
    except OSError as error:
        raise SystemExit(f'Cannot load the X11 client library: {error}') from error
    x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x11.XOpenDisplay.restype = ctypes.c_void_p
    x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

    def ready():
        connection = x11.XOpenDisplay(os.fsencode(display))
        if connection:
            x11.XCloseDisplay(connection)
        return bool(connection)

    if ready():
        return
    if not re.fullmatch(r':\d+(?:\.\d+)?', display):
        raise SystemExit(f'Cannot connect to DISPLAY={display}. Set DISPLAY=:1 to start Termux:X11 locally.')
    log = Path.home() / 'pocket-x11.log'
    with log.open('ab') as output:
        try:
            subprocess.Popen(['termux-x11', display.split('.')[0]], stdin=subprocess.DEVNULL,
                             stdout=output, stderr=output, start_new_session=True)
        except FileNotFoundError:
            raise SystemExit('Install the Termux:X11 Android app and run pkg install x11-repo && pkg install termux-x11-nightly.')
    for _ in range(60):
        if ready():
            return
        time.sleep(.25)
    raise SystemExit(f'Cannot connect to {display}. Open the Termux:X11 Android app and check {log}.')
