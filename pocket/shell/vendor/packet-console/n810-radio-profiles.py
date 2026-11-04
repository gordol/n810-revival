"""Local saved-profile domain API. No terminal, transport or radio dependencies."""
import json
import math
import os
from pathlib import Path
import tempfile

STORE=Path('~/.local/state/n810-radio/profiles.json').expanduser()
FIELDS=[('channel','Memory index'),('rx_mhz','Receive MHz'),('tx_mhz','Transmit MHz'),
        ('rx_ctcss','RX CTCSS Hz'),('tx_ctcss','TX CTCSS Hz'),('digital','Digital mode'),
        ('digital_channel','Digital memory'),('digital_mute','Digital mute'),
        ('beacon_seconds','Beacon interval s'),('audio_rx','Bluetooth listen'),('audio_tx','Bluetooth mic')]


def defaults():
    base=dict(channel=0,rx_mhz=144.390,tx_mhz=144.390,rx_ctcss=None,tx_ctcss=None,
              digital=True,digital_channel=0,digital_mute=True,beacon_seconds=0,audio_rx=False,audio_tx=False)
    return {'APRS':dict(base),'Voice Alert test':dict(base,rx_ctcss=100.0,digital_mute=False),
            'Voice':dict(base,channel=1,rx_mhz=146.520,tx_mhz=146.520,digital=False,digital_mute=False),
            'Packet':dict(base)}


def validate(key,value):
    if key in ('digital','digital_mute','audio_rx','audio_tx'):
        if not isinstance(value,bool):raise ValueError('Expected on/off')
        return value
    if key in ('rx_ctcss','tx_ctcss') and (value is None or str(value).lower() in ('off','none','0')):return None
    if key=='digital_channel':
        if str(value) not in ('0','0.0'):raise ValueError('Digital memory is fixed at 0')
        return 0
    if key in ('channel','beacon_seconds'):
        number=int(str(value))
        limit=1800 if key=='beacon_seconds' else 179
        if not 0<=number<=limit:raise ValueError('Use 0–%d'%limit)
        return number
    number=float(value)
    if not math.isfinite(number):raise ValueError("Use a finite number")
    if key in ('rx_mhz','tx_mhz'):
        if not (136<=number<=174 or 400<=number<=520):raise ValueError('Use a VHF/UHF radio frequency')
    elif not 60<=number<=260:raise ValueError('Use a CTCSS tone in Hz, or off')
    return number


def load(path):
    profiles=defaults()
    try:
        saved=json.loads(Path(path).read_text())
        for name,fields in saved['profiles'].items():
            if name not in profiles:continue
            for key,_ in FIELDS:
                if key in fields:profiles[name][key]=validate(key,fields[key])
    except (OSError,ValueError,KeyError,TypeError,AttributeError):pass
    return profiles


def save(path,profiles):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.profiles-')
    try:
        with os.fdopen(fd,'w') as f:json.dump({'version':1,'profiles':profiles},f,indent=2);f.write('\n')
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)



def read_saved(path):
    """Read actual saved profiles without overlaying editor defaults."""
    path=Path(path)
    if not path.exists():return None
    data=json.loads(path.read_text())
    if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('profiles'),dict):raise ValueError('Unsupported profiles')
    for name,fields in data['profiles'].items():
        if not isinstance(name,str) or not name.strip() or not isinstance(fields,dict):raise ValueError('Invalid saved profile')
        for key,_ in FIELDS:
            if key in fields:validate(key,fields[key])
    return data


def get_profile(data,profile_id):
    if profile_id not in data['profiles']:raise ValueError('Saved profile identity is missing')
    return data['profiles'][profile_id]


def edit_profile(profiles,profile_id,changes):
    """Validate one in-memory saved-profile edit without saving or applying it."""
    import copy
    if profile_id not in profiles:raise ValueError('Saved profile identity is missing')
    result=copy.deepcopy(profiles)
    for key,value in changes.items():
        if key not in dict(FIELDS):raise ValueError('Unsupported profile field: '+key)
        result[profile_id][key]=validate(key,value)
    return result
