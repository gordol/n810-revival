# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared fresh-image console, recovery access, and persistent diagnostics."""
from pathlib import Path
import shutil
import os


def configure_keyboard(root, binary=None):
    """Stage the source-backed internal-keyboard layer for every fresh image."""
    root = Path(root)
    platform = Path(__file__).resolve().parents[1]
    target = root / 'usr/local/sbin/n810-fn-remap'
    if binary is not None:
        source = Path(binary)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o755)
    if target.is_symlink() or not target.is_file():
        raise ValueError('Fresh root is missing the ARM n810-fn-remap helper')
    with target.open('rb') as stream:
        header = stream.read(20)
    if header[:5] != b'\x7fELF\x01' or header[18:20] != b'\x28\x00':
        raise ValueError('Keyboard remapper must be a 32-bit ARM ELF binary')
    for source, destination, mode in (
        (platform / 'scripts/n810-keyboard', root / 'usr/local/sbin/n810-keyboard', 0o755),
        (platform / 'device/n810-buttons.map', root / 'usr/local/share/n810/n810-console.map', 0o644),
        (platform / 'device/n810-fn-remap.service', root / 'etc/systemd/system/n810-fn-remap.service', 0o644),
        (platform / 'device/n810-keyboard.service', root / 'etc/systemd/system/n810-keyboard.service', 0o644),
    ):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(mode)
    wants = root / 'etc/systemd/system/multi-user.target.wants'
    wants.mkdir(parents=True, exist_ok=True)
    for name in ('n810-fn-remap.service', 'n810-keyboard.service'):
        link = wants / name
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to('../' + name)


def configure_power_indicators(root, backlight_binary=None, wake_binary=None):
    """Install the old tablet's source-backed battery, LED and key-light policy."""
    root = Path(root)
    platform = Path(__file__).resolve().parents[1]
    backlight = root / 'usr/local/sbin/n810-backlightd'
    if backlight_binary is not None:
        backlight.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(backlight_binary, backlight)
        backlight.chmod(0o755)
    if backlight.is_symlink() or not backlight.is_file():
        raise ValueError('Fresh root is missing the ARM n810-backlightd helper')
    with backlight.open('rb') as stream:
        header = stream.read(20)
    if header[:5] != b'\x7fELF\x01' or header[18:20] != b'\x28\x00':
        raise ValueError('Backlight helper must be a 32-bit ARM ELF binary')
    wake = root / 'usr/local/sbin/n810-wake'
    have_wake = wake_binary is not None or wake.is_file()
    if wake_binary is not None:
        wake.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(wake_binary, wake)
        wake.chmod(0o755)
    if have_wake:
        if wake.is_symlink() or not wake.is_file():
            raise ValueError('Fresh root is missing the ARM n810-wake helper')
        with wake.open('rb') as stream:
            header = stream.read(20)
        if header[:5] != b'\x7fELF\x01' or header[18:20] != b'\x28\x00':
            raise ValueError('Wake helper must be a 32-bit ARM ELF binary')
    for source, destination, mode in (
        (platform / 'scripts/n810-powerd', root / 'usr/local/sbin/n810-powerd', 0o755),
        (platform / 'scripts/n810-ledd', root / 'usr/local/sbin/n810-ledd', 0o755),
        (platform / 'scripts/n810-powerctl', root / 'usr/local/bin/n810-powerctl', 0o755),
        (platform / 'scripts/n810-ledctl', root / 'usr/local/bin/n810-ledctl', 0o755),
        (platform / 'scripts/n810-power', root / 'usr/local/bin/n810-power', 0o755),
        (platform / 'scripts/n810-screen', root / 'usr/local/sbin/n810-screen', 0o755),
        (platform / 'device/n810-backlight.conf', root / 'etc/n810-backlight.conf', 0o644),
        (platform / 'device/n810-display.conf', root / 'etc/n810-display.conf', 0o644),
        (platform / 'device/n810-led.conf', root / 'etc/n810-led.conf', 0o644),
        (platform / 'device/n810-backlightd.service', root / 'etc/systemd/system/n810-backlightd.service', 0o644),
        (platform / 'device/n810-powerd.service', root / 'etc/systemd/system/n810-powerd.service', 0o644),
        (platform / 'device/n810-ledd.service', root / 'etc/systemd/system/n810-ledd.service', 0o644),
        (platform / 'scripts/n810-display-keys.py', root / 'usr/local/sbin/n810-display-keys.py', 0o755),
        (platform / 'scripts/n810-power-overlay', root / 'usr/local/sbin/n810-power-overlay', 0o755),
        (platform / 'device/n810-display-keys.service', root / 'etc/systemd/system/n810-display-keys.service', 0o644),
    ):
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        destination.chmod(mode)
    if have_wake:
        for source, destination in (
            (platform / 'device/n810-debian-lock.conf', root / 'etc/n810-idle.conf'),
            (platform / 'device/n810-wake.service', root / 'etc/systemd/system/n810-wake.service'),
        ):
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            destination.chmod(0o644)
    wants = root / 'etc/systemd/system/multi-user.target.wants'
    wants.mkdir(parents=True, exist_ok=True)
    services = ['n810-backlightd.service', 'n810-powerd.service', 'n810-ledd.service',
                'n810-display-keys.service']
    if have_wake:
        services.append('n810-wake.service')
    for name in services:
        link = wants / name
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to('../' + name)


def configure_first_boot(root, keyboard_binary=None, backlight_binary=None, wake_binary=None):
    root = Path(root)
    here = Path(__file__).resolve().parent
    # Calibration describes one physical touchscreen. A reusable image must
    # collect it on the destination tablet, even when a staging root is reused.
    calibration = root / 'etc/n810/touch-calibration.json'
    if calibration.exists() or calibration.is_symlink():
        calibration.unlink()
    files = {
        'etc/systemd/system/ssh.service.d/10-generate-host-keys.conf':
            '[Service]\nExecStartPre=\nExecStartPre=/usr/bin/ssh-keygen -A\nExecStartPre=/usr/sbin/sshd -t\n',
        'etc/systemd/journald.conf.d/10-first-boot.conf':
            '[Journal]\nStorage=persistent\nSystemMaxUse=16M\nRuntimeMaxUse=8M\n',
        'etc/systemd/logind.conf.d/10-n810-power-key.conf':
            '[Login]\nHandlePowerKey=ignore\nHandlePowerKeyLongPress=ignore\n',
    }
    for name, contents in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
        path.chmod(0o644)
    for source, destination in (
        ('setup_touch.py', 'usr/local/lib/n810-touch/setup_touch.py'),
        ('n810-setup-touch.service', 'etc/systemd/system/n810-setup-touch.service'),
    ):
        target = root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(here / source, target)
        target.chmod(0o644)
    configure_keyboard(root, keyboard_binary)
    configure_power_indicators(root, backlight_binary, wake_binary)

    # These are Debian's standard privileged account tools. Staged copies must
    # retain ownership and setuid permissions before they enter an ext4 image.
    for name in ('sudo', 'su', 'passwd', 'chfn', 'chsh', 'gpasswd'):
        path = root / 'usr/bin' / name
        if path.is_file():
            os.chown(path, 0, 0)
            path.chmod(0o4755)
    launcher = root / 'usr/local/lib/pocket/bootstrap_desktop.py'
    if launcher.parent.is_dir():
        shutil.copyfile(here.parents[1] / 'pocket/platform/n810/bootstrap_desktop.py', launcher)
        launcher.chmod(0o644)
    led = root / 'etc/systemd/system/n810-first-boot-led.service'
    led.write_text('[Unit]\nDescription=Disable boot heartbeat after userspace starts\n'
                   'Before=n810-ledd.service\n'
                   'ConditionPathExists=/sys/class/leds/green/trigger\n[Service]\nType=oneshot\n'
                   "ExecStart=/bin/sh -c 'echo none > /sys/class/leds/green/trigger; echo 0 > /sys/class/leds/green/brightness'\n"
                   '[Install]\nWantedBy=multi-user.target\n')
    link = led.parent / 'multi-user.target.wants' / led.name
    link.parent.mkdir(exist_ok=True)
    if not link.is_symlink():
        link.symlink_to('../' + led.name)
