"""Cheap tmux window visibility checks; missing state leaves rendering enabled."""
import os
from pathlib import Path
import subprocess
import time
STATE=Path('/dev/shm/n810-visible-panes')
_due=0;_visible=True

def visible():
    global _due,_visible
    now=time.monotonic()
    if now<_due:return _visible
    _due=now+.5
    pane=os.environ.get('TMUX_PANE');tmux=os.environ.get('TMUX','').split(',')
    if not pane or len(tmux)<2:_visible=True;return True
    try:
        lines=STATE.read_text().splitlines()
        _visible=(pane in lines[1:]) if lines and lines[0]==tmux[1] else True
    except OSError:_visible=True
    return _visible


def setup():
    script=Path(__file__).with_name('n810-visible-panes.sh')
    if os.environ.get('TMUX') and script.exists():
        try:subprocess.run(['/bin/sh',str(script),'--install'],timeout=15,check=True)
        except (OSError,subprocess.SubprocessError):pass
