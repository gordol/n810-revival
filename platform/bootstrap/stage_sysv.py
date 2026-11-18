#!/usr/bin/env python3
"""Select the original N810's SysV boot order for an internal Pocket image."""
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
from pathlib import Path
import re


DEVICE = Path(__file__).resolve().parents[1] / 'device'
START = {
    'n810-ssh-hostkeys': (0, 'n810-ssh-hostkeys.init'),
    'n810-bluetooth-address': (1, 'n810-bluetooth-address.init'),
    'n810-zram': (1, 'n810-zram.init'),
    'pocket-expand-internal-root': (1, 'pocket-expand-internal-root.init'),
    'n810-backlightd': (2, 'n810-backlightd.init'),
    'n810-console-ux': (2, 'n810-console-ux.init'),
    'n810-powerd': (2, 'n810-powerd.init'),
    'n810-audio': (3, 'n810-audio.init'),
    'n810-wifi': (2, 'n810-wifi.init'),
    'n810-displayd': (3, 'n810-displayd.init'),
    'n810-boot-mode': (4, 'n810-boot-mode.init'),
    'n810-ledd': (3, 'n810-ledd.init'),
    'n810-wake': (3, 'n810-wake.init'),
    'n810-setup-touch': (4, 'n810-setup-touch.init'),
    'pocket-desktop': (5, 'pocket-desktop.init'),
    'pocket-services': (6, 'pocket-services.init'),
}


def stage(root, disk_id):
    root = Path(root)
    if not re.fullmatch(r'[0-9a-f]{8}', disk_id):
        raise ValueError('Invalid internal disk identity')
    status = (root / 'var/lib/dpkg/status').read_text()
    if not re.search(r'(?m)^Package: sysvinit-core\n(?:.*\n)*?Status: install ok installed$', status):
        raise ValueError('Internal root must install sysvinit-core')
    if re.search(r'(?m)^Package: systemd-sysv\n(?:.*\n)*?Status: install ok installed$', status):
        raise ValueError('Internal root must not select systemd as PID 1')
    if not (root / 'etc/init.d/ssh').is_file():
        raise ValueError('Debian SSH init script is missing')
    # Debian rc otherwise uses startpar's package-generated .depend files,
    # which do not contain the platform scripts staged below. Select the
    # sequential S/K link order explicitly, including host keys before ssh.
    (root / 'etc/init.d/.legacy-bootordering').touch()
    installed = root / 'etc/init.d'
    for directory in root.glob('etc/rc?.d'):
        for link in directory.glob('[SK]??n810-display-keys'):
            link.unlink()
    (installed / 'n810-display-keys').unlink(missing_ok=True)
    for runlevel in (2, 3, 4, 5):
        directory = root / f'etc/rc{runlevel}.d'
        directory.mkdir(parents=True, exist_ok=True)
        for old_link in directory.glob('S??ssh'):
            old_link.unlink()
        (directory / 'S01ssh').symlink_to('../init.d/ssh')
    for name, (priority, source_name) in START.items():
        source = DEVICE / source_name
        text = source.read_text()
        if name == 'pocket-expand-internal-root':
            text = text.replace('BOOTSTRAP_DISK_ID', disk_id)
        target = installed / name
        target.write_text(text)
        target.chmod(0o755)
        for runlevel in (2, 3, 4, 5):
            link = root / f'etc/rc{runlevel}.d/S{priority:02d}{name}'
            link.parent.mkdir(parents=True, exist_ok=True)
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to('../init.d/' + name)
        if name not in ('n810-ssh-hostkeys', 'n810-bluetooth-address', 'n810-setup-touch', 'pocket-expand-internal-root', 'pocket-services'):
            for runlevel in (0, 1, 6):
                link = root / f'etc/rc{runlevel}.d/K{99-priority:02d}{name}'
                link.parent.mkdir(parents=True, exist_ok=True)
                if link.exists() or link.is_symlink():
                    link.unlink()
                link.symlink_to('../init.d/' + name)
    # The first boot must not spend minutes generating RSA/DSS host keys.
    ssh = root / 'etc/ssh/sshd_config.d/10-n810-first-install.conf'
    ssh.write_text(ssh.read_text() + 'HostKey /etc/ssh/ssh_host_ed25519_key\n')
    modules = root / 'etc/modules'
    entries = modules.read_text().splitlines() if modules.exists() else []
    for module in ('tsc2005', 'p54spi', 'hci_uart', 'hci_nokia'):
        if module not in entries:
            entries.append(module)
    modules.write_text('\n'.join(entries) + '\n')
    systemd = root / 'etc/systemd/system'
    if systemd.is_dir():
        for path in systemd.glob('*.service'):
            if path.name.startswith(('n810-', 'pocket-')):
                path.unlink()
        wants = systemd / 'multi-user.target.wants'
        if wants.is_dir():
            for path in wants.iterdir():
                if path.name.startswith(('n810-', 'pocket-')):
                    path.unlink()
        for name in ('ssh.service.d/99-n810-host-key.conf',
                     'bluetooth.service.d/10-n810-address.conf'):
            (systemd / name).unlink(missing_ok=True)
    for name in ('journald.conf.d/10-first-boot.conf',
                 'logind.conf.d/10-n810-power-key.conf'):
        (root / 'etc/systemd' / name).unlink(missing_ok=True)
    return sorted(START)
