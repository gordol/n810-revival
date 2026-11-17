#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""N810 A/B control. The recovery config pins partitions; card files are data, never scripts."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

SCHEMA = 1
SLOTS = ('A', 'B')


def read(path):
    return json.loads(Path(path).read_text())


def atomic(path, value):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(name, path)
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        if os.path.exists(name): os.unlink(name)


def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()


def validate_state(state):
    if (state.get('version') != 1 or state.get('active') not in SLOTS or
            state.get('pending') not in (*SLOTS, None) or
            type(state.get('tries')) is not int or not 0 <= state['tries'] <= 3):
        raise ValueError('Invalid boot state; stay in recovery')
    return state


def choose(state):
    state = dict(validate_state(state))
    slot = state['active']
    if state['pending'] and state['tries']:
        slot = state['pending']; state['tries'] -= 1
    else:
        state.update(pending=None, tries=0)
    state['attempt'] = slot
    return slot, state


def confirm(state, slot):
    validate_state(state)
    if slot not in SLOTS or state.get('attempt') != slot:
        raise ValueError('Cannot confirm a slot that was not selected')
    return dict(state, active=slot, pending=None, tries=0)


def config(path):
    c = read(path)
    for key in ('sd_disk_id', 'recovery_disk_id'):
        if not re.fullmatch('[0-9a-f]{8}', c[key]): raise ValueError('Invalid disk ID')
    if c['sd_disk_id'] == c['recovery_disk_id']: raise ValueError('Disk IDs must differ')
    if c['data_schema'] != SCHEMA: raise ValueError('Unsupported data schema')
    return c


def device(c, part):
    return Path('/dev/disk/by-partuuid') / (c['sd_disk_id'] + '-%02d' % part)


def run(*args):
    subprocess.run(args, check=True)


def mounted(source, target, options):
    target = Path(target); target.mkdir(parents=True, exist_ok=True)
    run('mount', '-o', options, str(source), str(target))
    return target


def load_slot(c, slot, root):
    m = read(root / 'boot/n810-slot.json')
    if m['data_schema'] != c['data_schema']: raise ValueError('Data migration is required')
    for name in ('zImage', 'omap2420-n810.dtb'):
        if digest(root / 'boot' / name) != m['files'][name]: raise ValueError('Boot artifact checksum mismatch')
    # Recovered working N810 handoff: explicit DTB and 32 MiB image reservation.
    cmdline = ('root=PARTUUID=%s-%02d rootfstype=ext4 ro rootwait init=/sbin/n810-slot-init '
               'console=ttyS2,115200 console=tty0 omap2fb.auto_update=y loglevel=4 vt.rgb=1 '
               'n810.slot=%s n810.data=PARTUUID=%s-04' %
               (c['sd_disk_id'], 2 if slot == 'A' else 3, slot, c['sd_disk_id']))
    run('/usr/sbin/kexec', '--load', '--image-size=33554432', str(root / 'boot/zImage'),
        '--dtb=' + str(root / 'boot/omap2420-n810.dtb'), '--append=' + cmdline)
    if Path('/sys/kernel/kexec_loaded').read_text().strip() != '1': raise ValueError('Kernel was not loaded')


def wait_for_card(c, timeout=120):
    """Wait for the configured card and all partition devices, not just udev's first link."""
    deadline = time.monotonic() + timeout
    print('Waiting up to %d seconds for configured SD partitions' % timeout, flush=True)
    while True:
        if Path('/run/n810-stay-in-recovery').exists(): return 'held'
        try:
            if all(device(c, part).is_block_device() for part in (1, 2, 3, 4)):
                return 'ready'
        except OSError:
            pass  # Device removal or udev replacement during discovery.
        remaining = deadline - time.monotonic()
        if remaining <= 0: return 'timeout'
        time.sleep(min(1, remaining))


def boot(c):
    if not Path('/etc/n810-ab/recovery').exists(): raise ValueError('Boot selection runs only in recovery')
    if Path('/sys/kernel/kexec_loaded').read_text().strip() != '0': raise ValueError('Preserve already-loaded kernel')
    readiness = wait_for_card(c)
    if readiness == 'held': return 'Recovery requested locally'
    if readiness != 'ready': return 'Configured SD partitions did not become ready; recovery remains available'
    control = mounted(device(c, 1), '/run/n810-ab-control', 'rw,nosuid,nodev,noexec')
    try:
        if (control / 'stay-in-recovery').exists(): return 'Recovery requested on card'
        state = read(control / 'state.json')
        slot, next_state = choose(state)
        candidates = [slot] + ([state['active']] if slot != state['active'] else [])
        failure = None
        for candidate in candidates:
            if candidate != slot:
                next_state = dict(state, pending=None, tries=0, attempt=candidate)
            # Persist attempts even when the pending slot cannot be validated or loaded.
            atomic(control / 'state.json', next_state)
            root = None
            try:
                root = mounted(device(c, 2 if candidate == 'A' else 3), '/run/n810-ab-slot', 'ro,noload,nosuid,nodev,noexec')
                load_slot(c, candidate, root)
                failure = None
                break
            except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
                failure = error
                if Path('/sys/kernel/kexec_loaded').read_text().strip() == '1': run('/usr/sbin/kexec', '--unload')
                print('Slot ' + candidate + ' rejected: ' + str(error), flush=True)
            finally:
                if root is not None: run('umount', str(root))
        if failure is not None: raise failure
    finally: run('umount', str(control))
    run('sync')
    run('/sbin/shutdown', '-r', 'now')
    return 'Orderly kexec requested'


def mark_good(c):
    tokens = Path('/proc/cmdline').read_text().split()
    matches = [t.split('=', 1)[1] for t in tokens if t.startswith('n810.slot=')]
    if len(matches) != 1 or matches[0] not in SLOTS: raise ValueError('Not an A/B slot boot')
    slot = matches[0]
    expected = 'root=PARTUUID=%s-%02d' % (c['sd_disk_id'], 2 if slot == 'A' else 3)
    if expected not in tokens: raise ValueError('Root and slot disagree')
    if not os.path.ismount('/data') or not os.path.ismount('/home'): raise ValueError('Persistent data is not mounted')
    # A service PID alone is not a rendered desktop. The caller must verify UI health.
    control = mounted(device(c, 1), '/run/n810-ab-control', 'rw,nosuid,nodev,noexec')
    try: atomic(control / 'state.json', confirm(read(control / 'state.json'), slot))
    finally: run('umount', str(control))
    return 'Confirmed slot ' + slot


def update(c, bundle):
    """Update only the inactive slot. Data-schema changes require a separate migration."""
    bundle = Path(bundle).resolve(); m = read(bundle / 'UPDATE.json')
    if m['data_schema'] != c['data_schema']: raise ValueError('Refusing an incompatible data schema')
    image = bundle / 'slot.ext4'
    if m['bytes'] != image.stat().st_size or digest(image) != m['sha256']:
        raise ValueError('Update image checksum mismatch')
    control = mounted(device(c, 1), '/run/n810-ab-control', 'rw,nosuid,nodev,noexec')
    try:
        state = validate_state(read(control / 'state.json'))
        if state['pending']: raise ValueError('Confirm or cancel the pending update first')
        slot = 'B' if state['active'] == 'A' else 'A'
        target = device(c, 2 if slot == 'A' else 3).resolve(strict=True)
        # Require block device and reject any mounted alias, including the running root.
        import stat
        st = target.stat()
        if not stat.S_ISBLK(st.st_mode): raise ValueError('Slot target is not a block device')
        major_minor = '%d:%d' % (os.major(st.st_rdev), os.minor(st.st_rdev))
        if any(line.split()[2] == major_minor for line in Path('/proc/self/mountinfo').read_text().splitlines()):
            raise ValueError('Inactive slot is mounted; refusing overwrite')
        capacity = int(subprocess.check_output(['blockdev', '--getsize64', str(target)]))
        if not 0 < m['bytes'] <= capacity: raise ValueError('Update does not fit slot')
        with image.open('rb') as src, target.open('r+b', buffering=0) as dst:
            for block in iter(lambda: src.read(4 * 1024 * 1024), b''):
                view=memoryview(block)
                while view:
                    count=dst.write(view)
                    if not count: raise OSError('Short slot write')
                    view=view[count:]
            os.fsync(dst.fileno())
        h = hashlib.sha256()
        with target.open('rb', buffering=0) as src:
            remaining = m['bytes']
            while remaining:
                block = src.read(min(4 * 1024 * 1024, remaining))
                if not block: raise ValueError('Short slot readback')
                h.update(block); remaining -= len(block)
        if h.hexdigest() != m['sha256']: raise ValueError('Slot readback failed; boot selection unchanged')
        run('e2fsck', '-fn', str(target))
        atomic(control / 'state.json', dict(state, pending=slot, tries=3))
    finally: run('umount', str(control))
    return 'Verified update staged in slot ' + slot


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('boot', 'mark-good', 'update', 'status', 'try-slot', 'stay-recovery', 'resume-sd'))
    p.add_argument('--config', default='/etc/n810-ab/config.json')
    p.add_argument('--bundle')
    p.add_argument('--slot', choices=SLOTS)
    a = p.parse_args()
    if os.geteuid(): p.error('Root required')
    Path('/run/lock').mkdir(parents=True, exist_ok=True)
    with open('/run/lock/n810-ab.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        c = config(a.config)
        if a.action == 'boot': print(boot(c))
        elif a.action == 'mark-good': print(mark_good(c))
        elif a.action=='update':
            if not a.bundle:p.error('--bundle is required')
            print(update(c,a.bundle))
        else:
            control=mounted(device(c,1),'/run/n810-ab-control','rw,nosuid,nodev,noexec')
            try:
                state=validate_state(read(control/'state.json'))
                if a.action=='try-slot':
                    if not a.slot or a.slot==state['active']:raise ValueError('Choose the inactive slot')
                    atomic(control/'state.json',dict(state,pending=a.slot,tries=3))
                elif a.action=='stay-recovery':
                    with (control/'stay-in-recovery').open('w') as f:f.flush();os.fsync(f.fileno())
                    run('sync')
                elif a.action=='resume-sd':(control/'stay-in-recovery').unlink(missing_ok=True);run('sync')
                print(json.dumps(read(control/'state.json')))
            finally:run('umount',str(control))

if __name__ == '__main__': main()
