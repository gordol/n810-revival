"""Catch one RX-44 bootloader enumeration at the port saved during RAM boot."""
import errno
import os
from pathlib import Path
import plistlib
import re
import subprocess
import sys
import time


def port_from_receipt(receipt):
    if sys.platform == 'darwin':
        port = receipt.get('usb_location')
        if type(port) is int and 0 < port <= 0xffffffff:
            return port
    elif sys.platform.startswith('linux'):
        port = receipt.get('usb_port', '')
        if isinstance(port, str) and re.fullmatch(r'[0-9]+-[0-9]+(?:\.[0-9]+)*', port):
            return port
    raise ValueError('A USB port recorded on this host is required for automatic capture')


def mac_instance(nodes, port):
    for node in nodes:
        if (node.get('locationID') == port and node.get('idVendor') == 0x0421
                and node.get('idProduct') == 0x0105):
            session = node.get('sessionID')
            if type(session) is not int or session <= 0:
                raise ValueError('Missing USB enumeration identity at the recorded location')
            return str(session)
        found = mac_instance(node.get('IORegistryEntryChildren', ()), port)
        if found:
            return found
    return None


def linux_instance(device):
    # Anchor all attributes to the same sysfs directory across disconnects.
    try:
        fd = os.open(device, os.O_DIRECTORY)
    except FileNotFoundError:
        return None
    try:
        def attr(name):
            with os.fdopen(os.open(name, os.O_RDONLY, dir_fd=fd)) as stream:
                return stream.read().strip()
        if attr('idVendor') == '0421' and attr('idProduct') == '0105':
            return f"{int(attr('busnum'))}:{int(attr('devnum'))}"
    except OSError as error:
        if error.errno not in (errno.ENOENT, errno.ENODEV, errno.ENOTDIR):
            raise
    finally:
        os.close(fd)
    return None


def current_instance(port):
    if sys.platform == 'darwin':
        tree = subprocess.check_output(['ioreg', '-a', '-p', 'IOUSB', '-l'], timeout=5)
        return mac_instance(plistlib.loads(tree), port)
    return linux_instance(Path('/sys/bus/usb/devices') / port)


FALLBACK = ('Hold Home/Swap while powering on the same N810 on the recorded USB port, '
            'then run the flash step again.')


def capture(port, reboot, *, timeout=45):
    # Start sampling before dispatching SSH. An already-held bootloader needs no reboot.
    instance = current_instance(port)
    if instance:
        return instance
    print('Listening on USB port ' + str(port) + ' before requesting the installer reboot.', flush=True)
    with reboot() as process:
        deadline = time.monotonic() + timeout
        try:
            while time.monotonic() < deadline:
                instance = current_instance(port)
                if instance:
                    return instance
                # SSH commonly exits 255 when the kernel takes USB down.
                if process.poll() not in (None, 0, 255):
                    raise RuntimeError('Installer refused the reboot. ' + FALLBACK)
                time.sleep(0.03)
            raise RuntimeError('Missed the USB update-mode window. ' + FALLBACK)
        finally:
            if process.poll() is None:
                process.kill()
