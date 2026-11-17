#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Confirm a trial only after persistent data and a fault-free rendered desktop are ready."""
import json
import os
from pathlib import Path
import subprocess
import time


def healthy():
    if not os.path.ismount('/data') or not os.path.ismount('/home'):return False
    mounts=Path('/proc/self/mountinfo').read_text().splitlines()
    if not any(l.split()[4]=='/' and 'ro' in l.split()[5].split(',') for l in mounts):return False
    active=json.loads(Path('/run/n810-pocket-native/active.json').read_text())
    for key in ('owner_pid','child_pid'):os.kill(active[key],0)
    if active.get('application')!='pocket':return False
    params=Path('/sys/module/n810_mbx_gpu_probe/parameters')
    if any(int((params/n).read_text()) for n in ('gpu_service_failed','resident_fault','cleanup_error','gpu_error')):return False
    return int((params/'gpu_service_jobs').read_text())>0


def main():
    success=0
    for _ in range(60):
        try: success=success+1 if healthy() else 0
        except (OSError,ValueError,KeyError):success=0
        if success>=3:
            subprocess.run(['/usr/local/sbin/n810-ab','mark-good'],check=True);return
        time.sleep(5)
    # Do not interrupt a user calibration session or charging mode merely because
    # no desktop has launched. Leave the trial unconfirmed; next restart retries.
    print('A/B boot remains unconfirmed: desktop/data health was not established',flush=True)

if __name__=='__main__':main()
