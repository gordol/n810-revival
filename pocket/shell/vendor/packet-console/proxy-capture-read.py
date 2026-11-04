#!/usr/bin/env python3
"""Decode a saved proxy capture without connecting to Bluetooth."""
import argparse
import importlib.util
import json
from pathlib import Path
spec = importlib.util.spec_from_file_location('stream', Path(__file__).with_name('uvpro-stream.py'))
stream = importlib.util.module_from_spec(spec); spec.loader.exec_module(stream)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('capture', nargs='?', default=str(Path.home()/'.local/state/n810-aprs/proxy-traffic.jsonl'))
args = parser.parse_args()
context = ['']
observers = {}
for direction in ('phone_to_radio', 'radio_to_phone'):
    observers[direction] = stream.Observer(command=lambda text: print(context[0], text))
with open(args.capture) as f:
    for line in f:
        row = json.loads(line); direction = row['direction']
        if direction not in observers: continue
        context[0] = row['time'] + ' ' + ('PHONE → RADIO' if direction == 'phone_to_radio' else 'RADIO → PHONE')
        observers[direction].feed(bytes.fromhex(row['hex']))
