#!/usr/bin/env python3
"""UV-Pro receiver and local KISS bridge. No RF transmissions without a duplex client."""
import importlib.util
import datetime
import json
from pathlib import Path
import re
import signal
import selectors
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
    bridge = live = reads = loop = changes = None
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
        live = module('radio_live', 'n810-radio-live.py').Telemetry(bridge.telemetry_request,bandwidth_send=bridge.bandwidth_request)
        try:
            reads = module('radio_read_owner', 'n810-radio-read-owner.py').Endpoint(
                submit=live.start_read, status=live.read_progress, cancel=live.cancel_read,
                radio_live=live.read_state,tune=live.tune_repeater)
        except (OSError, ValueError) as exc:
            status('Radio read endpoint unavailable: '+str(exc))
        from control_changes import ControlChanges
        paths={live.control,live.gps_control}
        if live.bandwidth is not None:paths.add(live.bandwidth.request_path)
        changes=ControlChanges(paths)
        loop=selectors.DefaultSelector()
        loop.register(bridge.selector.fileno(),selectors.EVENT_READ,'radio')
        if reads:loop.register(reads.selector.fileno(),selectors.EVENT_READ,'commands')
        loop.register(changes.fd,selectors.EVENT_READ,'controls')
        live.refresh_controls();live.tick()
        while True:
            now=time.monotonic()
            deadlines=[value for value in (live.next_deadline(now),reads.next_deadline() if reads else None) if value is not None]
            timeout=max(0,min(deadlines)-now) if deadlines else None
            for key,_mask in loop.select(timeout):
                if key.data=='radio':
                    data=bridge.poll(0)
                    if data:total+=len(data);live.feed(data)
                elif key.data=='commands':reads.poll()
                elif key.data=='controls':live.refresh_controls(changes.drain())
            now=time.monotonic()
            if reads and reads.next_deadline() is not None and reads.next_deadline()<=now:reads.poll(now)
            live.tick(now)
    except KeyboardInterrupt:
        print('\nStopped.', flush=True)
    finally:
        if loop:loop.close()
        if changes:changes.close()
        if reads: reads.close()
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
