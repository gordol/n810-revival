"""Private per-device radio choices. Saving never pairs, flashes or transmits."""
import json
import os
from pathlib import Path
import re
import tempfile


def directory(home=None):
    return Path(home or Path.home()) / '.config/pocket'


def write_private(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write('\n')
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate_receive(value):
    if not isinstance(value, dict) or set(value) != {'address', 'callsign'}:
        raise ValueError('Set the UV-Pro Bluetooth address and station callsign')
    if not isinstance(value['address'], str) or not re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', value['address']):
        raise ValueError('Enter the paired UV-Pro Bluetooth address')
    if not isinstance(value['callsign'], str) or not re.fullmatch(r'[A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?', value['callsign']):
        raise ValueError('Enter an AX.25 station callsign, optionally with SSID 0–15')
    return dict(address=value['address'].upper(), callsign=value['callsign'])


def receive_profile(home=None):
    path = directory(home) / 'receive.json'
    with path.open('rb') as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError('Radio profile exceeds limit')
    return validate_receive(json.loads(raw))


def save_receive(value, home=None):
    write_private(directory(home) / 'receive.json', validate_receive(value))


def save_endpoints(callsign, receive='', meshcore='', reticulum='', home=None, tx_min=None, tx_max=None):
    """Create explicit owner profiles only for endpoints the user supplies."""
    home = Path(home or Path.home())
    state = home / '.local/state/current-world'
    receive_value = validate_receive(dict(address=receive, callsign=callsign)) if receive else None
    if reticulum:
        if tx_min is None or tx_max is None:raise ValueError('Enter the allowed RNode transmit-power bounds for your radio')
        tx_min,tx_max=int(tx_min),int(tx_max)
        from app_registry import validate_reticulum_selection
        validate_reticulum_selection(dict(mode='local',state=str(home / '.local/state/pocket-reticulum'),
            interpreter='/opt/n810-mesh/bin/python', station=callsign, radio_id='n810-rnode',
            connection='hub' if reticulum.startswith('hub://') else 'bluetooth' if reticulum.startswith('/dev/rfcomm') else 'usb',
            port=reticulum, minimum_txpower=tx_min, maximum_txpower=tx_max,
            prepare_nokia_spp=reticulum=='/dev/rfcomm0'))
    if meshcore:
        from meshcore_service import validate_selection
        profile = validate_selection(dict(state=str(home / '.local/state/pocket-meshcore'),
            interpreter='/opt/pocket-htit/bin/python', station=callsign,
            port=meshcore, trusted_peripheral=True))
        # Requiring an explicit address is separate from trusting an unpaired device.
        profile.pop('mode')
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = state / 'meshcore-owner.toml'
        text = '\n'.join(k + ' = ' + ('true' if v is True else json.dumps(v)) for k, v in profile.items()) + '\n'
        import tempfile
        fd, name = tempfile.mkstemp(prefix='.meshcore-', dir=state)
        try:
            with os.fdopen(fd, 'w') as stream:stream.write(text)
            os.replace(name, path)
        finally:
            if os.path.exists(name):os.unlink(name)
    if reticulum:
        from app_registry import validate_reticulum_selection
        from runtime_codec import atomic_write
        profile = validate_reticulum_selection(dict(mode='local',state=str(home / '.local/state/pocket-reticulum'),
            interpreter='/opt/n810-mesh/bin/python', station=callsign, radio_id='n810-rnode',
            connection='hub' if reticulum.startswith('hub://') else 'bluetooth' if reticulum.startswith('/dev/rfcomm') else 'usb',
            port=reticulum, minimum_txpower=tx_min, maximum_txpower=tx_max,
            prepare_nokia_spp=reticulum=='/dev/rfcomm0'))
        state.mkdir(parents=True, exist_ok=True, mode=0o700)
        atomic_write(state / 'reticulum-owner.msgpack', profile)
    if receive_value:
        save_receive(receive_value, home)


def identity_transfer(action, filename, home=None):
    """Copy a 64-byte RNS private identity, preserving every existing destination."""
    import socket
    import stat
    home = Path(home or Path.home())
    state = home / '.local/state/pocket-reticulum'
    identity = state / 'identity'
    selected = Path(filename).expanduser()
    if not selected.is_absolute():raise ValueError('Choose an absolute identity file path')
    if action == 'import':
        for runtime in ('management-runtime', 'session-runtime', 'carrier-runtime'):
            endpoint = state / runtime / 'owner.sock'
            probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            probe.settimeout(.5)
            try:probe.connect(str(endpoint))
            except (FileNotFoundError, ConnectionRefusedError):pass
            else:raise ValueError('Stop Reticulum before importing an identity; disable startup and reboot if needed')
            finally:probe.close()
        source, destination = selected, identity
    elif action == 'export':source, destination = identity, selected
    else:raise ValueError('Choose identity import or export')
    fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):raise ValueError('Choose a regular private identity file')
        raw = stream.read(65)
    if len(raw) != 64:raise ValueError('Expected a 64-byte Reticulum private identity file')
    if action == 'import':state.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'wb') as stream:stream.write(raw)
    except BaseException:
        destination.unlink();raise
    return 'Private identity copied to ' + str(destination)
