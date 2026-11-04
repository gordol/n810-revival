#!/usr/bin/python3 -I
"""Upgrade the fixed session entry while stopped; retain original rollback bytes."""
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile

STAGE = Path('/tmp/pocket-session-startup-upgrade')
BACKUP = Path('/var/backups/n810-pocket-console/session-startup-20261025')
ENTRY = Path('/usr/local/libexec/n810-pocket-session')
SELECTOR = Path('/usr/local/lib/n810-pocket/version_selector.py')
HELPER = Path('/usr/local/sbin/n810-pocket-console')
SUPERVISOR = Path('/usr/local/lib/n810-pocket/console_helper.py')
LOCKS = (Path('/run/n810-pocket-console/upgrade.lock'),
         Path('/run/n810-gui/launch.lock'), Path('/run/n810-pocket-console/session.lock'))
OLD_ENTRY = 'bb0efaa3160060c67af307133ed6e250bc670daa76c171dfca3f7411a9b6a9de'
NEW_ENTRY = '44810f2369cfbf8908a6a590b83e875ece59c4e5825ebe91ef8c37a5f51931f8'
OLD_SELECTOR = 'e435f02faa766a199dc8fa6fb14a3f483894e34936e9b9942a69d1b7fe5a9e3d'
NEW_SELECTOR = 'cb6d69e258652312702745f7e3b09c83e64873506f7e9e300d6fb833d13db270'
CURRENT_SELECTOR = None
HELPER_SHA = '3541fdee15f048339ea45bf534a3274d95fc940c6748d8b195bec51aea29e445'
SUPERVISOR_SHA = 'e92248ae39ac4d93abaf313e61268ff9e25b879466b11322b8734fb616db3538'
LIMIT = 262144


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def trusted(path, directory=False):
    path = Path(path)
    if not path.is_absolute():
        raise ValueError('Installed path must be absolute')
    for part in reversed((path, *path.parents)):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise PermissionError('Untrusted path: ' + str(part))
        expected = stat.S_ISDIR if part != path or directory else stat.S_ISREG
        if not expected(info.st_mode):
            raise PermissionError('Unexpected path type: ' + str(part))


def read(path, hashes):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > LIMIT:
            raise ValueError('Unexpected file: ' + str(path))
        raw = stream.read(LIMIT + 1)
    if len(raw) > LIMIT or digest(raw) not in hashes:
        raise ValueError('Unexpected hash: ' + str(path))
    return raw


def write(path, raw, mode):
    fd, name = tempfile.mkstemp(prefix='.session-upgrade-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def selector_bytes(original):
    if digest(original) != OLD_SELECTOR or original.count(OLD_ENTRY.encode()) != 1:
        raise ValueError('Unexpected selector transformation input')
    result = original.replace(OLD_ENTRY.encode(), NEW_ENTRY.encode())
    if digest(result) != NEW_SELECTOR:
        raise ValueError('Unexpected selector transformation result')
    return result


def acquire(path):
    trusted(path.parent, directory=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, 0o600)
    stream = os.fdopen(fd, 'r+b')
    try:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise PermissionError('Untrusted lock: ' + str(path))
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stream
    except BaseException:
        stream.close()
        raise


def stopped():
    result = json.loads(subprocess.check_output([str(HELPER), 'status'], text=True, timeout=120))
    if result.get('state') != 'stopped' or result.get('restored') is not True:
        raise RuntimeError('Stop the console through its supervisor and verify restoration before upgrading')


def install_files(new_entry):
    """Called under supervisor locks; preserve originals even after partial installation."""
    if CURRENT_SELECTOR is not None:
        # A separately reviewed capacity upgrade follows the session upgrade.
        # Verify both installed files without reconstructing/downgrading its
        # selector or altering the original session rollback backups.
        if digest(new_entry) != NEW_ENTRY:
            raise ValueError('Unexpected entry payload')
        read(ENTRY, {NEW_ENTRY})
        read(SELECTOR, {CURRENT_SELECTOR})
        return False
    before = {ENTRY: read(ENTRY, {OLD_ENTRY, NEW_ENTRY}),
              SELECTOR: read(SELECTOR, {OLD_SELECTOR, NEW_SELECTOR})}
    trusted(BACKUP.parent, directory=True)
    if BACKUP.exists() or BACKUP.is_symlink():
        trusted(BACKUP, directory=True)
    else:
        BACKUP.mkdir(mode=0o700)
    originals = {}
    specs = ((ENTRY, 'session_entry.py.before', OLD_ENTRY, NEW_ENTRY, 0o755),
             (SELECTOR, 'version_selector.py.before', OLD_SELECTOR, NEW_SELECTOR, 0o644))
    # Finish all original backups before touching either installed file.
    for path, name, old_hash, new_hash, mode in specs:
        saved = BACKUP / name
        if saved.exists() or saved.is_symlink():
            trusted(saved)
            originals[path] = read(saved, {old_hash})
        else:
            if digest(before[path]) != old_hash:
                raise ValueError('Original rollback file missing: ' + str(saved))
            write(saved, before[path], mode)
            originals[path] = read(saved, {old_hash})
    after = {ENTRY: new_entry, SELECTOR: selector_bytes(originals[SELECTOR])}
    if digest(new_entry) != NEW_ENTRY:
        raise ValueError('Unexpected entry payload')
    changed = []
    try:
        for path, name, old_hash, new_hash, mode in specs:
            if read(path, {old_hash, new_hash}) != before[path]:
                raise ValueError('Installed file changed during upgrade')
            if before[path] != after[path]:
                changed.append(path)
                write(path, after[path], mode)
            read(path, {new_hash})
        receipt = dict(completed=True, restarted=False, files={str(path):
                       dict(before=digest(originals[path]), after=digest(after[path])) for path in before})
        receipt_path = BACKUP / 'receipt.json'
        if receipt_path.exists() or receipt_path.is_symlink():
            trusted(receipt_path)
        write(receipt_path, (json.dumps(receipt, indent=2) + '\n').encode(), 0o600)
    except BaseException as failure:
        errors = []
        for path in reversed(changed):
            mode = 0o755 if path == ENTRY else 0o644
            try:
                read(path, {digest(before[path]), digest(after[path])})
                write(path, before[path], mode)
                read(path, {digest(before[path])})
            except BaseException as error:
                errors.append(str(path) + ': ' + str(error))
        if errors:
            raise RuntimeError('Upgrade failed; recovery errors: ' + '; '.join(errors)) from failure
        raise
    return bool(changed)


def main():
    if os.geteuid() != 0 or os.getegid() != 0 or len(sys.argv) != 1:
        raise SystemExit('Administrator invocation without arguments required')
    os.umask(0o077)
    for path in (HELPER, SUPERVISOR, ENTRY, SELECTOR):
        trusted(path)
    read(HELPER, {HELPER_SHA})
    read(SUPERVISOR, {SUPERVISOR_SHA})
    # Stage is pinned data, never imported/executed. /tmp itself remains shared.
    info = STAGE.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise PermissionError('Stage must be a root-owned non-writable directory')
    payload = STAGE / 'session_entry.py'
    info = payload.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise PermissionError('Untrusted staged payload')
    new_entry = read(payload, {NEW_ENTRY})
    with ExitStack() as stack:
        for path in LOCKS:
            stack.enter_context(acquire(path))
        stopped()
        for path in (ENTRY, SELECTOR):
            trusted(path)
        changed = install_files(new_entry)
    print('Session entry ' + ('upgraded' if changed else 'already current') +
          '; console remains stopped; rollback originals: ' + str(BACKUP))


if __name__ == '__main__':
    main()
