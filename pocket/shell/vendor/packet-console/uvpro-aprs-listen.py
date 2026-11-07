#!/usr/bin/env python3
"""UV-Pro receiver and local KISS bridge. No RF transmissions without a duplex client."""
import importlib.util
import datetime
import json
from pathlib import Path
import re
import signal
import socket
import subprocess
import sys
import time


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    loaded = importlib.util.module_from_spec(spec); spec.loader.exec_module(loaded)
    return loaded


def main():
    def stop(signum, frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGHUP, stop)
    print('KISS bridge enabled; raw sockets open after radio connection', flush=True)
    addr = '02:00:00:00:00:13'
    sdp = subprocess.check_output(['sdptool','search','--bdaddr',addr,'SP'], timeout=25, text=True)
    match = re.search(r'Channel: (\d+)', sdp)
    if not match: raise ConnectionError('UV-PRO serial service unavailable')
    radio = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    bridge = live = None
    count = total = 0
    def status(text): print(text, flush=True)
    def capture(direction, frame, **metadata):
        row=dict(time=datetime.datetime.now().astimezone().isoformat(timespec='milliseconds'),direction=direction,frame=frame.hex())
        row.update(metadata)
        print('@KISS '+json.dumps(row,separators=(',',':')),flush=True)
    def packet(text):
        nonlocal count
        count += 1; print(time.strftime('%H:%M:%S'), text, flush=True)
    try:
        radio.settimeout(10); radio.connect((addr, int(match.group(1))))
        bridge_module = module('bridge', 'n810-kiss-bridge.py')
        print('UV-PRO connected | APRS receive monitor | Ctrl-C stops', flush=True)
        print('Radio settings unchanged. Waiting for RF packet data...', flush=True)
        bridge = bridge_module.Bridge(radio, status=status, capture=capture, packet=packet)
        live = module('radio_live', 'n810-radio-live.py').Telemetry(bridge.telemetry_request)
        checked = time.monotonic()
        while True:
            data = bridge.poll(1)
            if data:
                total += len(data); live.feed(data)
            live.tick()
            if time.monotonic() - checked >= 10:
                info = subprocess.run(['bluetoothctl','info',addr], capture_output=True, text=True, timeout=8)
                if info.returncode or 'Connected: yes' not in info.stdout:
                    raise ConnectionError('Bluetooth disconnected')
                status(time.strftime('%H:%M:%S')+' Listening | packets: '+str(count)+' | Bluetooth bytes: '+str(total))
                checked = time.monotonic()
    except KeyboardInterrupt:
        print('\nStopped.', flush=True)
    finally:
        if live: live.close()
        if bridge: bridge.close()
        radio.close()


def run(retry=False):
    """Keep the radio adapter resident across transient connection failures."""
    while True:
        try:
            main()
            return 0
        except KeyboardInterrupt:
            print('Stopped.', flush=True)
            return 0
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            print('UV-PRO connection unavailable: '+str(exc), flush=True)
            if not retry:return 1
        try:time.sleep(10)
        except KeyboardInterrupt:
            print('Stopped.', flush=True)
            return 0


if __name__ == '__main__':
    if sys.argv[1:] not in ([],['--retry']):raise SystemExit('Usage: uvpro-aprs-listen.py [--retry]')
    sys.exit(run(retry=sys.argv[1:]==['--retry']))
