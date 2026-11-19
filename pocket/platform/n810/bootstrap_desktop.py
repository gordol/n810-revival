#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Own one foreground VT and run the first-install desktop as the local user."""
import argparse
from array import array
import fcntl
import os
from pathlib import Path
import pwd
import signal
import subprocess
import termios


def command(root, assets, state, framebuffer):
    argv=['/usr/bin/python3','-I',str(root/'graphics/nokia.py'),
          '--framebuffer-fd',str(framebuffer),'--font',str(assets/'console-font.psf'),
          '--renderer-library',str(assets/'renderer.so'),'--display-library',str(assets/'window.so'),
          '--native-library',str(assets/'_cellengine.abi3.so'),'--state',str(state),
          '--cell-renderer','cpu','--allow-software']
    calibration=Path('/etc/n810/touch-calibration.json')
    if calibration.is_file() and Path('/dev/input/n810-touch').exists():
        argv+=['--touch-device','/dev/input/n810-touch','--touch-calibration',str(calibration),
               '--touch-display','800x480','--touch-rotation','0']
    return argv


def restore_display(framebuffer, tty, console, old_kd, active_vt, mode, previous):
    """Attempt every VT restoration step even if the framebuffer rejects one."""
    errors=[]
    actions=(
        lambda: fcntl.ioctl(framebuffer,0x4f25),
        lambda: fcntl.ioctl(tty,0x4b3a,old_kd),
        lambda: fcntl.ioctl(console,0x5606,active_vt),
        lambda: fcntl.ioctl(console,0x5607,active_vt),
        lambda: mode.write_text(previous),
    )
    try:
        for action in actions:
            try:action()
            except OSError as error:errors.append(error)
    finally:
        for fd in (framebuffer,tty,console):os.close(fd)
    if errors:raise RuntimeError('Display restoration failed') from errors[0]


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--user',default='nokia');a=p.parse_args()
    if os.geteuid()!=0:raise SystemExit('The system display service must own the VT')
    account=pwd.getpwnam(a.user)
    if account.pw_uid==0:raise SystemExit('Pocket must run as a normal user')
    root=Path('/usr/local/share/pocket');assets=root/'build/graphics'
    console=os.open('/dev/tty0',os.O_RDWR|os.O_NOCTTY|os.O_CLOEXEC)
    active=array('H',[0,0,0]);fcntl.ioctl(console,0x5603,active,True)
    free=array('i',[0]);fcntl.ioctl(console,0x5600,free,True)
    if not 1<=free[0]<=63:raise SystemExit('No free virtual terminal')
    tty=os.open('/dev/tty'+str(free[0]),os.O_RDWR|os.O_NOCTTY|os.O_CLOEXEC)
    framebuffer=os.open('/dev/fb0',os.O_RDWR|os.O_CLOEXEC)
    mode=Path('/sys/class/graphics/fb0/update_mode');previous=mode.read_text()
    old_kd=array('i',[0]);fcntl.ioctl(tty,0x4b3b,old_kd,True)
    child=None
    def session():
        os.setsid();fcntl.ioctl(0,termios.TIOCSCTTY,0)
        os.initgroups(account.pw_name,account.pw_gid);os.setgid(account.pw_gid);os.setuid(account.pw_uid)
    def stop(*unused):
        if child is not None and child.poll() is None:child.send_signal(signal.SIGTERM)
    env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':account.pw_dir,'USER':account.pw_name,
         'LOGNAME':account.pw_name,'TERM':'linux','LANG':'C.UTF-8','LD_LIBRARY_PATH':str(assets),'LD_PRELOAD':str(assets/'libOSMesa.so.8')}
    try:
        fcntl.ioctl(framebuffer,0x4f25);mode.write_text('2\n')
        fcntl.ioctl(tty,0x4b3a,1);fcntl.ioctl(console,0x5606,free[0]);fcntl.ioctl(console,0x5607,free[0])
        for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
        state=Path(account.pw_dir)/'.local/state/pocket/default'
        child=subprocess.Popen(command(root,assets,state,framebuffer),stdin=tty,
                               pass_fds=(framebuffer,),env=env,preexec_fn=session)
        result=child.wait()
    finally:
        restore_display(framebuffer,tty,console,old_kd[0],active[0],mode,previous)
    raise SystemExit(result)

if __name__=='__main__':main()
