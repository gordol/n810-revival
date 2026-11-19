"""Private installer choices: optional Wi-Fi credentials and service startup."""
import hashlib
import json
import os
from pathlib import Path
import re

SERVICES = ('receive', 'meshcore', 'reticulum')


def validate(value):
    if not isinstance(value, dict) or set(value) - {'startup', 'wifi', 'storage_target'}:
        raise ValueError('Setup profile supports startup and wifi only')
    startup = value.get('startup', {})
    if not isinstance(startup, dict) or set(startup) - set(SERVICES) or any(type(v) is not bool for v in startup.values()):
        raise ValueError('Choose boolean startup options for receive, meshcore and reticulum')
    result = {'startup': {name: startup.get(name, False) for name in SERVICES}}
    if 'storage_target' in value:
        if value['storage_target'] not in ('internal','sd'):raise ValueError('Choose internal or sd storage')
        result['storage_target']=value['storage_target']
    wifi = value.get('wifi')
    if wifi is not None:
        if not isinstance(wifi, dict) or set(wifi) - {'ssid', 'passphrase', 'country', 'open'}:
            raise ValueError('Invalid Wi-Fi profile fields')
        ssid, password = wifi.get('ssid', ''), wifi.get('passphrase', '')
        country = wifi.get('country', 'US')
        opened = wifi.get('open', False)
        if not isinstance(ssid, str) or not 1 <= len(ssid.encode()) <= 32 or '\x00' in ssid or '\n' in ssid:
            raise ValueError('Wi-Fi SSID must be 1–32 bytes without NUL or newline')
        if not isinstance(country, str) or not re.fullmatch('[A-Z]{2}', country):
            raise ValueError('Wi-Fi country must be two uppercase letters')
        if type(opened) is not bool or not isinstance(password, str):
            raise ValueError('Invalid Wi-Fi security settings')
        if opened and password:
            raise ValueError('Open networks must not have a passphrase')
        if not opened and not 8 <= len(password.encode()) <= 63:
            raise ValueError('WPA passphrase must be 8–63 bytes')
        result['wifi'] = dict(ssid=ssid, passphrase=password, country=country, open=opened)
    return result


def wpa_config(wifi):
    wifi = validate({'wifi': wifi})['wifi']
    # Encode SSID as bytes, so quotes/backslashes cannot inject configuration.
    lines = ['ctrl_interface=/run/wpa_supplicant', 'update_config=0',
             'country=' + wifi['country'], 'network={', '    ssid=' + wifi['ssid'].encode().hex()]
    if wifi['open']:
        lines.append('    key_mgmt=NONE')
    else:
        key = hashlib.pbkdf2_hmac('sha1', wifi['passphrase'].encode(), wifi['ssid'].encode(), 4096, 32).hex()
        lines += ['    psk=' + key, '    proto=RSN', '    pairwise=CCMP', '    group=CCMP']
    return '\n'.join(lines + ['}', ''])


def stage(root, value):
    value = validate(value)
    root = Path(root)
    home = root / 'home/nokia'
    owner = home.stat()
    parent = home / '.config/pocket'
    parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = parent / 'services.json'
    target.write_text(json.dumps(value['startup'], sort_keys=True) + '\n')
    target.chmod(0o600)
    for p in (home / '.config', parent, target):
        os.chown(p, owner.st_uid, owner.st_gid)
    if 'wifi' in value:
        target = root / 'etc/wpa_supplicant/wpa_supplicant-wlan0.conf'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(wpa_config(value['wifi']))
        target.chmod(0o600)
    # This record deliberately contains no Wi-Fi password or derived key.
    summary = {'startup': value['startup'], 'wifi_configured': 'wifi' in value,
               'peripheral_setup': 'after-first-boot'}
    record = root / 'usr/local/share/pocket/SETUP.json'
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def read_stdin(stream):
    line = stream.readline(8193)
    if len(line.encode()) > 8192:
        raise ValueError('Private setup profile exceeds 8 KiB')
    return validate(json.loads(line))
