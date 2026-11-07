#!/usr/bin/python3 -I
"""Prepare the fixed bonded Nokia RNode mapping without opening its radio."""
import os
import sys
import stat
import fcntl
import grp
import pwd

ADDRESS = '02:00:00:00:00:16'
CONTROLLER = '02:00:00:00:00:15'
DEVICE = '/dev/rfcomm0'


def _capture(args):
    """Bounded native read-only probes without importing subprocess."""
    reader, writer = os.pipe()
    try:
        actions = [(os.POSIX_SPAWN_DUP2, writer, 1),
                   (os.POSIX_SPAWN_DUP2, writer, 2),
                   (os.POSIX_SPAWN_CLOSE, reader)]
        if writer not in (1, 2): actions.append((os.POSIX_SPAWN_CLOSE, writer))
        argv = ['/usr/bin/timeout', '-k', '1', '3', *args]
        pid = os.posix_spawn(argv[0], argv, {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}, file_actions=actions)
        os.close(writer); writer = None
        raw = bytearray(); oversize = False
        while True:
            chunk = os.read(reader, 4096)
            if not chunk: break
            if len(raw) + len(chunk) > 4096: oversize = True
            if not oversize: raw.extend(chunk)
        _, status = os.waitpid(pid, 0)
        if oversize: raise ValueError('Oversize controller probe')
        return os.waitstatus_to_exitcode(status), raw.decode('ascii')
    finally:
        os.close(reader)
        if writer is not None: os.close(writer)


def _bonded_spp(text):
    section = ''; fields = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('[') and line.endswith(']'): section = line[1:-1]
        elif '=' in line:
            name, value = line.split('=', 1)
            if (section, name) in fields: return False
            fields[section, name] = value
    key = fields.get(('LinkKey', 'Key'), '')
    return (len(key) == 32 and all(c in '0123456789abcdefABCDEF' for c in key)
            and '00001101-0000-1000-8000-00805f9b34fb' in fields.get(('General', 'Services'), '').lower())


def _existing_mapping_ready():
    """Accept only an unchanged, bonded, unused mapping; make no changes."""
    if os.geteuid() != 0 or len(sys.argv) != 1: return False
    lock = bond = None
    try:
        uid = pwd.getpwnam('nokia').pw_uid
        node = os.stat(DEVICE, follow_symlinks=False)
        if (not stat.S_ISCHR(node.st_mode) or (os.major(node.st_rdev), os.minor(node.st_rdev)) != (216, 0)
                or stat.S_IMODE(node.st_mode) != 0o660 or node.st_uid != uid
                or node.st_gid != grp.getgrnam('dialout').gr_gid): return False
        with open('/proc/self/status', encoding='ascii') as stream:
            cap = next((line.split(':', 1)[1].strip() for line in stream if line.startswith('CapEff:')), '')
        if not cap or not int(cap, 16) & (1 << 19): return False
        os.listdir('/proc/self/fd'); os.listdir('/proc/1/fd')
        lock = os.open('/run/lock/n810-rnode-spp.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        info = os.fstat(lock)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o077: return False
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        bond = os.open('/var/lib/bluetooth/' + CONTROLLER + '/' + ADDRESS + '/info', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        info = os.fstat(bond)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o077 or info.st_size > 16384: return False
        if not _bonded_spp(os.read(bond, 16385).decode('utf-8')): return False
        code, controller = _capture(['/usr/bin/hciconfig', 'hci0'])
        if code or 'BD Address: ' + CONTROLLER not in controller or 'UP RUNNING' not in controller: return False
        code, mapping = _capture(['/usr/bin/rfcomm', 'show', '0'])
        if code or mapping.split()[:6] != ['rfcomm0:', CONTROLLER, '->', ADDRESS, 'channel', '1']: return False
        code, busy = _capture(['/usr/bin/fuser', DEVICE])
        after = os.stat(DEVICE, follow_symlinks=False)
        return (code == 1 and not busy.strip()
                and (after.st_dev, after.st_ino, after.st_rdev, after.st_uid, after.st_gid, after.st_mode)
                == (node.st_dev, node.st_ino, node.st_rdev, node.st_uid, node.st_gid, node.st_mode))
    except (OSError, ValueError, KeyError):
        return False
    finally:
        if bond is not None: os.close(bond)
        if lock is not None: os.close(lock)


if __name__ == '__main__' and _existing_mapping_ready():
    print('{"ok":true,"device":"/dev/rfcomm0","address":"02:00:00:00:00:16","channel":1,"mapping_created":false,"owner_changed":false,"radio_opened":false,"rf_enabled":false,"fast_path":true}')
    raise SystemExit(0)

# Creation, ownership changes and ambiguous state use the original full checks.
import fcntl
import grp
import json
import os
from pathlib import Path
import pwd
import re
import signal
import stat
import subprocess
import sys

NODE = Path(DEVICE)


def command(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=8,
                          env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'})


def require_process_visibility():
    status = Path('/proc/self/status').read_text()
    capabilities = re.search(r'^CapEff:\s*([0-9a-fA-F]+)$', status, re.M)
    if not capabilities or not int(capabilities.group(1), 16) & (1 << 19):
        raise ValueError('Process inspection capability is unavailable; not modified')
    os.listdir('/proc/self/fd')
    os.listdir('/proc/1/fd')


def unused_port(result):
    return result.returncode == 1 and not result.stdout.strip() and not result.stderr.strip()


def mapping(text):
    return re.match(r'^rfcomm0:\s+' + CONTROLLER + r'\s+->\s+' + ADDRESS +
                    r'\s+channel 1(?:\s|$)', text.strip()) is not None


def serial_service(text):
    return re.search(r'^[ \t]*UUID:[ \t]+[^\r\n]*\(00001101-0000-1000-8000-00805f9b34fb\)[ \t]*$',
                     text, re.M) is not None


def node_info():
    info = NODE.lstat()
    if not stat.S_ISCHR(info.st_mode) or (os.major(info.st_rdev), os.minor(info.st_rdev)) != (216, 0):
        raise ValueError('rfcomm0 is not the expected character device')
    if info.st_gid != grp.getgrnam('dialout').gr_gid or stat.S_IMODE(info.st_mode) != 0o660:
        raise ValueError('Unexpected rfcomm0 group or permissions; no changes made')
    if info.st_uid not in (0, pwd.getpwnam('nokia').pw_uid):
        raise ValueError('Unexpected rfcomm0 owner; no changes made')
    return info


def prepare():
    if os.geteuid() != 0 or len(sys.argv) != 1:
        raise ValueError('This fixed helper requires root and accepts no arguments')
    require_process_visibility()
    flags = os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open('/run/lock/n810-rnode-spp.lock', flags, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o077:
            raise ValueError('Unsafe helper lock')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        controller = command(['/usr/bin/bluetoothctl', 'show', CONTROLLER])
        if controller.returncode or not re.search(r'^Controller ' + CONTROLLER + r'(?:\s|$)', controller.stdout):
            raise ValueError('The expected local Bluetooth controller is unavailable')
        default = command(['/usr/bin/bluetoothctl', 'show'])
        if default.returncode or not re.search(r'^Controller ' + CONTROLLER + r'(?:\s|$)', default.stdout):
            raise ValueError('The default Bluetooth controller is not the expected controller')
        bond = command(['/usr/bin/bluetoothctl', 'info', ADDRESS])
        if bond.returncode or not re.search(r'^\s*Paired: yes\s*$', bond.stdout, re.M):
            raise ValueError('The expected RNode bond is unavailable')
        if not re.search(r'^Device ' + ADDRESS + r'(?:\s|$)', bond.stdout) or not serial_service(bond.stdout):
            raise ValueError('The expected bonded serial service is unavailable')
        current = command(['/usr/bin/rfcomm', 'show', '0'])
        created = False
        if current.returncode == 0:
            if not mapping(current.stdout):
                raise ValueError('rfcomm0 is mapped to a different endpoint; not modified')
        else:
            if os.path.lexists(NODE) or 'No such device' not in current.stderr:
                raise ValueError('Cannot establish that rfcomm0 is unused; not modified')
            bind = command(['/usr/bin/rfcomm', '-i', CONTROLLER, 'bind', '0', ADDRESS, '1'])
            if bind.returncode:
                raise ValueError('The fixed lazy bind failed: ' + bind.stderr.strip()[:200])
            created = True
            settle = command(['/usr/bin/udevadm', 'settle', '--timeout=5'])
            if settle.returncode:
                raise ValueError('Device-node setup did not settle within its bound')
        current = command(['/usr/bin/rfcomm', 'show', '0'])
        if current.returncode or not mapping(current.stdout):
            raise ValueError('The expected mapping could not be verified')
        before = node_info()
        busy = command(['/usr/bin/fuser', str(NODE)])
        if not unused_port(busy):
            raise ValueError('The serial node is occupied or ownership cannot be checked; not modified')
        uid = pwd.getpwnam('nokia').pw_uid
        if before.st_uid != uid:
            os.chown(NODE, uid, -1, follow_symlinks=False)
        after = node_info()
        if after.st_ino != before.st_ino or after.st_rdev != before.st_rdev or after.st_uid != uid:
            raise ValueError('Serial node identity changed; operator inspection required')
        return {'ok': True, 'device': str(NODE), 'address': ADDRESS, 'channel': 1,
                'mapping_created': created, 'owner_changed': before.st_uid != uid,
                'radio_opened': False, 'rf_enabled': False}


if __name__ == '__main__':
    def deadline(signum, frame):
        raise TimeoutError('Serial mapping preparation exceeded 25 seconds')
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(25)
    try:
        print(json.dumps(prepare()))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)[:400]}))
        raise SystemExit(1)
