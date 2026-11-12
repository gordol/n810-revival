#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Copy installed boot diagnostics through Maemo USB storage without disk writes."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from write_macos_internal import disk_info


def inspect(disk, location, debugfs):
    identity = disk_info(disk, location)
    print(f'Verified {disk}: N810 on USB port {location:08x}', flush=True)
    subprocess.run(['diskutil', 'unmountDisk', disk], check=True)
    if disk_info(disk, location)['DeviceTreePath'] != identity['DeviceTreePath']:
        raise ValueError('Disk identity changed after unmount; stopped')
    raw = '/dev/r' + disk[5:] + 's1'

    def read(command):
        result = subprocess.run([str(debugfs), '-R', command, raw],
                                capture_output=True, text=True, check=True)
        return result.stdout + result.stderr

    if 'id:2:initdefault:' not in read('cat /etc/inittab'):
        raise ValueError('Expected installed SysV root not found; stopped')
    output = Path(tempfile.mkdtemp(prefix='n810-installed-logs-', dir='/private/tmp'))
    output.chmod(0o700)
    (output / 'copy-log.txt').write_text(read('rdump /var/log ' + str(output)))
    if not (output / 'log').is_dir():
        raise RuntimeError('Boot log copy failed; see ' + str(output / 'copy-log.txt'))
    paths = ('/etc/inittab', '/etc/network/interfaces', '/etc/modules',
             '/etc/init.d/n810-console-ux', '/etc/init.d/n810-powerd',
             '/etc/init.d/n810-ledd', '/etc/init.d/n810-setup-touch',
             '/etc/init.d/pocket-desktop', '/etc/init.d/.depend.boot',
             '/etc/init.d/.depend.start', '/var/lib/n810-maintenance/keyboard-before.map')
    for path in paths:
        (output / path.strip('/').replace('/', '_')).write_text(read('cat ' + path))
    for name, command in (
        ('startup-links.txt', 'ls -l /etc/rc2.d'),
        ('ssh-files.txt', 'ls -l /etc/ssh'),
        ('calibration.txt', 'cat /etc/n810/touch-calibration.json'),
        ('keymap-state.txt', 'ls -l /var/lib/n810-maintenance'),
        ('boot-order.txt', 'stat /etc/init.d/.legacy-bootordering'),
    ):
        (output / name).write_text(read(command))
    owner = int(os.environ.get('SUDO_UID', str(os.getuid())))
    group = int(os.environ.get('SUDO_GID', str(os.getgid())))
    for path in [*output.rglob('*'), output]:
        if not path.is_symlink():
            os.chown(path, owner, group)
    subprocess.run(['diskutil', 'eject', disk], check=True)
    print('Logs copied to ' + str(output), flush=True)
    print('No filesystem write or kernel flash was performed.', flush=True)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk', required=True)
    parser.add_argument('--usb-location', required=True, type=lambda value: int(value, 0))
    parser.add_argument('--debugfs', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.error('Run with sudo to read the guarded raw partition')
    debugfs = args.debugfs or shutil.which('debugfs') or '/opt/homebrew/opt/e2fsprogs/sbin/debugfs'
    if not Path(debugfs).is_file():
        parser.error('Install e2fsprogs or supply --debugfs')
    inspect(args.disk, args.usb_location, debugfs)


if __name__ == '__main__':
    main()
