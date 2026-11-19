"""User-owned optional services; startup preferences and Start now are independent."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

RADIO = Path('/usr/local/lib/n810-radio')


def supervisor():
    from peripheral_setup import receive_profile
    profile = receive_profile()
    root = Path.home() / '.local/state/n810-aprs'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root / 'supervisor.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        children = []
        def stop(*_):
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGHUP, stop)
        commands = [('n810-aprs-feed.py',), ('n810-aprs-directory.py', '--collect', '--call', profile['callsign'])]
        try:
            while True:
                for index, args in enumerate(commands):
                    if len(children) <= index:
                        children.append(None)
                    child = children[index]
                    if child is None or child.poll() is not None:
                        children[index] = subprocess.Popen([sys.executable, '-u', str(RADIO / args[0]), *args[1:]])
                time.sleep(5)
        finally:
            for child in children:
                if child is not None and child.poll() is None:
                    child.terminate()
            for child in children:
                if child is not None:
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        child.kill();child.wait()


def start(names):
    unknown = set(names) - {'receive', 'reticulum', 'meshcore'}
    if unknown:
        raise ValueError('Unknown optional service')
    results = []
    if 'receive' in names:
        from peripheral_setup import receive_profile
        receive_profile()  # Missing config fails before any process is spawned.
        root = Path.home() / '.local/state/n810-aprs'
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(root / 'service.log', os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'ab') as log:
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--receive'],
                             stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        results.append('APRS receive requested; inspect service.log and Connections for status')
    if set(names) & {'reticulum', 'meshcore'}:
        from device_services import ensure
        ensure()
        results.append('Device owner requested; Connections reports missing endpoints and runtime errors')
    return results


def boot():
    from service_policy import load
    choices = load()
    names = [name for name, selected in choices.items() if selected]
    if not names:
        return []
    # One unconfigured peripheral must not prevent the other selected services.
    results = []
    groups = [(['receive'] if 'receive' in names else []),
              [name for name in names if name != 'receive']]
    for selected in groups:
        if selected:
            try:
                results += start(selected)
            except (OSError, ValueError, RuntimeError, TimeoutError) as error:
                results.append(str(error))
    return results


if __name__ == '__main__':
    if sys.argv[1:] == ['--receive']:
        supervisor()
    elif sys.argv[1:] == ['--boot']:
        print('\n'.join(boot()))
    else:
        raise SystemExit('Usage: optional_services.py --boot|--receive')
