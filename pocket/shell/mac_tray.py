"""Cached Mac hardware observations for the Pocket panel."""
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

_enabled = sys.platform == 'darwin'
_lock = threading.Lock()
_deadline = 0
_state = ('?', 'unknown', 'unknown')


_connections = None


def bind_connections(connections):
    global _connections
    _connections = connections


def enabled():
    if not _enabled or _connections is None:
        return _enabled
    return _connections.local_selected


def _collect():
    global _state
    battery, source, power = '?', 'unknown', 'unknown'
    try:
        output = subprocess.check_output(['/usr/bin/pmset', '-g', 'batt'], text=True, timeout=4)
        match = re.search(r'(\d{1,3}%)', output)
        if match:
            battery = match[1]
        if "'AC Power'" in output:
            source = 'AC power'
        elif "'Battery Power'" in output:
            source = 'battery power'
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        helper = Path(__file__).resolve().parents[1] / 'bluetooth-macos/uvpro'
        power = subprocess.check_output([str(helper), '--power'], text=True, timeout=4).strip()
        if power not in ('on', 'off'):
            power = 'unknown'
    except (OSError, subprocess.SubprocessError):
        pass
    with _lock:
        _state = battery, source, power


def sample():
    global _deadline
    with _lock:
        if time.monotonic() >= _deadline:
            _deadline = time.monotonic() + 30
            threading.Thread(target=_collect, daemon=True).start()
        return _state
