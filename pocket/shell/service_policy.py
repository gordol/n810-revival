"""Explicit per-user startup preferences; configuration alone never opts in."""
import json
import os
from pathlib import Path

SERVICES = ('receive', 'meshcore', 'reticulum')


def path(home=None):
    return Path(home or Path.home()) / '.config/pocket/services.json'


def validate(value):
    if not isinstance(value, dict) or set(value) - set(SERVICES):
        raise ValueError('Unknown startup service')
    if any(type(v) is not bool for v in value.values()):
        raise ValueError('Startup choices must be booleans')
    return {name: value.get(name, False) for name in SERVICES}


def load(home=None):
    source = path(home)
    try:
        with source.open('rb') as stream:
            raw = stream.read(4097)
    except FileNotFoundError:
        return validate({})
    if len(raw) > 4096:
        raise ValueError('Service preferences are too large')
    return validate(json.loads(raw))


def enabled(name, home=None):
    if name not in SERVICES:
        raise ValueError('Unknown startup service')
    return load(home)[name]


def save(value, home=None):
    value = validate(value)
    target = path(home)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    from peripheral_setup import write_private
    write_private(target, value)
    return value
