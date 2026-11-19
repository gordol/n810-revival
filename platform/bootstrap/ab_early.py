#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""PID 1 selects an SD userspace without restarting the flashed kernel."""
import os
from pathlib import Path
import subprocess
import time
from ab_runtime import atomic, choose, config, mounted, read, run, verify_kernel

ROOT = Path('/new-root')
CONTROL = Path('/run/n810-ab-control')


def discover(c):
    devices = {}
    for part in (1, 2, 3, 4):
        result = subprocess.run(['blkid', '-c', '/dev/null', '-t',
            'PARTUUID=%s-%02d' % (c['sd_disk_id'], part), '-o', 'device'],
            text=True, capture_output=True)
        names = result.stdout.splitlines()
        if len(names) != 1 or not Path(names[0]).is_block_device():
            return None
        devices[part] = names[0]
    return devices


def unmount_slot():
    if os.path.ismount(ROOT): run('umount', '-R', str(ROOT))


def prepare(c, devices, slot):
    mounted(devices[2 if slot == 'A' else 3], ROOT, 'ro,noload')
    manifest = read(ROOT/'boot/n810-slot.json')
    if manifest['data_schema'] != c['data_schema']:
        raise ValueError('Data migration required')
    verify_kernel(manifest)
    # Bind early virtual filesystems into the candidate; no services run yet.
    for name in ('proc', 'sys', 'dev', 'run'):
        run('mount', '--bind', '/'+name, str(ROOT/name))
    run('chroot', str(ROOT), '/sbin/n810-slot-init', '--prepare',
        'PARTUUID='+c['sd_disk_id']+'-04')
    atomic('/run/n810-ab-boot.json', dict(version=1, slot=slot,
        root_partuuid=c['sd_disk_id']+('-02' if slot == 'A' else '-03'),
        data_partuuid=c['sd_disk_id']+'-04', kernel_notes_sha256=manifest['kernel_notes_sha256']))


def select(c):
    print('N810: selecting SD root; one kernel, no kexec. Waiting up to 120 seconds for the card.', flush=True)
    devices = None
    deadline = time.monotonic() + 120
    while True:
        if Path('/etc/n810-ab/stay-in-recovery').exists(): return False
        devices = discover(c)
        if devices: break
        remaining = deadline - time.monotonic()
        if remaining <= 0: break
        time.sleep(min(1, remaining))
    if not devices:
        print('Configured SD card absent; starting internal recovery.', flush=True)
        return False
    mounted(devices[1], CONTROL, 'rw,nosuid,nodev,noexec')
    try:
        if (CONTROL/'stay-in-recovery').exists(): return False
        state = read(CONTROL/'state.json')
        slot, next_state = choose(state)
        candidates = [slot] + ([state['active']] if slot != state['active'] else [])
        for candidate in candidates:
            if candidate != slot:
                next_state = dict(state, pending=None, tries=0, attempt=candidate)
            atomic(CONTROL/'state.json', next_state)
            try:
                prepare(c, devices, candidate)
                return True
            except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
                print('Slot %s rejected: %s' % (candidate, error), flush=True)
                unmount_slot()
        return False
    finally:
        run('umount', str(CONTROL))


def main():
    if os.getpid() != 1: raise SystemExit('Early root selection must run as PID 1')
    os.environ['PATH'] = '/usr/sbin:/usr/bin:/sbin:/bin'
    for name, fs, options in (('proc','proc','defaults'), ('sys','sysfs','defaults'),
                             ('dev','devtmpfs','defaults'), ('run','tmpfs','mode=755,size=16m')):
        if not os.path.ismount('/'+name): run('mount','-t',fs,'-o',options,fs,'/'+name)
    run('mount', '--make-rprivate', '/')
    try:
        if select(config('/etc/n810-ab/config.json')):
            run('sync')
            os.chdir(ROOT)
            run('/bin/busybox', 'pivot_root', '.', 'old-root')
            os.chroot('.')
            os.chdir('/')
            # Exec releases Python mappings on the old root before unmounting it.
            os.execv('/sbin/n810-slot-init', ['/sbin/n810-slot-init', '--enter'])
    except Exception as error:
        print('SD selection failed; internal recovery: '+str(error), flush=True)
        if os.path.ismount(ROOT): unmount_slot()
    os.execv('/sbin/init', ['/sbin/init'])

if __name__ == '__main__': main()
