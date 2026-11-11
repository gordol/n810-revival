#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run Pocket pixels on an owner-provided Nokia framebuffer and foreground VT.

The caller owns service/module and VT lifetime. This process never changes VTs,
loads a driver, changes display mode, or opens a framebuffer by pathname.
"""
from pathlib import Path
import argparse,json,os,signal,sys,termios,time,tty
DEVELOPMENT = True  # Removed by the release exporter.
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent/'shell'))
from full import Platform
from window import Window

class NokiaPlatform(Platform):
    terminal_input=True
    def __init__(self,*args,seconds=None,**kwargs):
        super().__init__(*args,**kwargs);self.seconds=seconds;self.deadline=None
    def events(self):
        if self.seconds is not None:
            if self.deadline is None:self.deadline=time.monotonic()+self.seconds
            if time.monotonic()>=self.deadline:self.closed=True
        return super().events()
    def wait_timeout(self,timeout):
        # VT keys, touch, services and worker completions share the model's
        # selector. There is no SDL queue to pump and no idle frame polling.
        if self.actions:return 0
        if self.deadline is not None:
            remaining=max(0,self.deadline-time.monotonic())
            return remaining if timeout is None else min(timeout,remaining)
        return timeout

def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--framebuffer-fd',type=int,required=True)
    p.add_argument('--font',type=Path,required=True)
    p.add_argument('--renderer-library',type=Path,required=True)
    p.add_argument('--display-library',type=Path,required=True)
    p.add_argument('--native-library',type=Path,required=True)
    p.add_argument('--state',type=Path,required=True)
    p.add_argument('--font-mode',choices=('console','crisp','smooth'),default='console')
    p.add_argument('--allow-software',action='store_true',help='admit software GL for input/display diagnostics; does not enable or load a GPU service')
    p.add_argument('--cell-renderer',choices=('cpu','gpu'),default='gpu',help='desktop cell renderer (default: verified GPU; cpu is an explicit override)')
    p.add_argument('--seconds',type=float)
    if DEVELOPMENT:
        p.add_argument('--actions',type=Path)
    if DEVELOPMENT:
        p.add_argument('--output',type=Path)
    if DEVELOPMENT:
        p.add_argument('--report',type=Path)
    p.set_defaults(actions=None,output=None,report=None)
    a,rest=p.parse_known_args()
    if not 3<=a.framebuffer_fd<=65535:p.error('framebuffer descriptor must be inherited in 3..65535')
    if a.seconds is not None and not 0<a.seconds<=86400:p.error('seconds must be in (0,86400]')
    from keyboard_runtime import console_foreground
    if not console_foreground(sys.stdin.fileno()):p.error('An owned foreground Linux VT is required for input')
    a.state.mkdir(parents=True,exist_ok=True)
    display=Window(a.display_library,fd=a.framebuffer_fd)
    platform=NokiaPlatform(a.font,a.renderer_library,display,output=a.output,
        actions=json.loads(a.actions.read_text()) if a.actions else (),seconds=a.seconds,
        font_mode=a.font_mode,require_gpu=not a.allow_software,cell_renderer=a.cell_renderer,diagnostics=a.report is not None)
    previous={};old=termios.tcgetattr(sys.stdin)
    def stop(signum,frame):
        platform.closed=True
        # The desktop installs a TERM handler that writes its selector wakeup.
        # Delegate INT to it too; a flag alone cannot stop a blocked selector.
        wake=signal.getsignal(signal.SIGTERM)
        if callable(wake) and wake is not stop:wake(signum,frame)
    for sig in (signal.SIGTERM,signal.SIGINT):previous[sig]=signal.signal(sig,stop)
    try:
        tty.setraw(sys.stdin,when=termios.TCSANOW)
        return platform.run(['--shell','--session',str(a.state/'desktop.json'),
            '--app-state',str(a.state),'--station-db',str(a.state/'directory.sqlite3'),
            '--native',str(a.native_library),'--touch-acquisition','process',*rest])
    finally:
        try:platform.close()
        finally:
            termios.tcsetattr(sys.stdin,termios.TCSANOW,old)
            for sig,handler in previous.items():signal.signal(sig,handler)
            platform.report.update(platform='nokia-framebuffer',desktop_ansi=False,
                desktop_pty=False,desktop_cells=platform.size)
            if DEVELOPMENT and (a.report):a.report.write_text(json.dumps(platform.report,indent=2)+'\n')
if __name__=='__main__':main()
