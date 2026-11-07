#!/usr/bin/env python3
"""Open an isolated tmux demonstration using the APRS offline map fixture.

Usage: python3 tools/docs/tmux_preview.py --maps /path/to/public-map-packs
Requires tmux and the project's existing public geography packs. Use a terminal
at least 100 columns by 40 rows. Detach with Ctrl-B, d to finish. The private
server and temporary configuration are removed when the client exits.
"""
import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]


def prepare(directory, maps):
    directory=Path(directory)
    config=directory/'tmux.conf'
    lines=(ROOT/'platform/config/tmux-n810.conf').read_text().splitlines()
    # Keep the project's navigation and appearance, with private overrides and
    # device-specific helper commands excluded from this offline demonstration.
    lines=[s for s in lines if not any(x in s for x in ('source-file','run-shell','n810-tmux-battery'))]
    lines += ['set -g status-right " offline demo "',
              'set -g default-shell /bin/sh',
              'set -g default-command "env ENV=/dev/null /bin/sh -i"',
              'set -as terminal-overrides ",xterm-256color:Tc"',
              'set -g default-terminal "xterm-256color"']
    config.write_text('\n'.join(lines)+'\n')
    command=['tmux','-S',str(directory/'tmux.sock'),'-f',str(config)]
    env={k:os.environ[k] for k in ('PATH','LANG','TMPDIR') if k in os.environ}
    env.update(TERM='xterm-256color',COLORTERM='truecolor',PYTHONDONTWRITEBYTECODE='1',ENV='/dev/null',PS1='demo$ ')
    def tmux(*args):
        result=subprocess.run(command+list(args),env=env,capture_output=True,text=True)
        if result.returncode:raise RuntimeError(result.stderr.strip())
        return result
    mapcmd=shlex.join([sys.executable,str(ROOT/'tools/docs/aprs_map_preview.py'),'--maps',str(Path(maps).resolve()),'--packets'])
    try:
        tmux('new-session','-d','-s','aprs-demo','-n','Map','-x','120','-y','44','-c',str(ROOT),mapcmd)
        tmux('split-window','-v','-l','8','-t','aprs-demo:0','-c',str(ROOT),'/bin/sh -i')
        for _ in range(100):
            if tmux('capture-pane','-p','-t','aprs-demo:0.1').stdout.rstrip().endswith('$'):break
            time.sleep(.02)
        tmux('send-keys','-t','aprs-demo:0.1','C-l')
        tmux('send-keys','-t','aprs-demo:0.1','python3 tools/docs/aprs_map_preview.py --describe','Enter')
        tmux('new-window','-d','-t','aprs-demo:1','-n','Packets','-c',str(ROOT),shlex.join([sys.executable,str(ROOT/'tools/docs/aprs_preview.py')]))
        tmux('new-window','-d','-t','aprs-demo:2','-n','Shell','-c',str(ROOT),'/bin/sh -i')
        tmux('select-pane','-t','aprs-demo:0.0')
    except BaseException:
        subprocess.run(command+["kill-server"],env=env,capture_output=True)
        raise
    return command,env


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--maps',required=True,type=Path)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='n810-docs-tmux-') as directory:
        command,env=prepare(directory,args.maps)
        try:subprocess.run(command+['attach-session','-t','aprs-demo'],env=env,check=True)
        finally:subprocess.run(command+['kill-server'],env=env,capture_output=True)
