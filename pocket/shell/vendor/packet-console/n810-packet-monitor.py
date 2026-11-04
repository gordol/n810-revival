#!/usr/bin/env python3
"""Receive-only KISS/AX.25 monitor; never writes to the TNC."""
import argparse
import datetime
import os
import select
import termios


def address(raw):
    call = bytes(x >> 1 for x in raw[:6]).decode('ascii', 'replace').strip()
    ssid = (raw[6] >> 1) & 15
    return call + ('-' + str(ssid) if ssid else '')


def describe(frame):
    if not frame or frame[0] & 15:
        return None  # Only KISS data, not configuration replies.
    packet = frame[1:]
    addresses = []
    offset = 0
    while offset + 7 <= len(packet) and len(addresses) < 10:
        raw = packet[offset:offset + 7]
        # Vendor notifications can share the serial stream with KISS frames.
        # AX.25 callsigns must be shifted uppercase letters/digits, space padded.
        name=bytes(x >> 1 for x in raw[:6]).rstrip(b' ')
        if not name or any(x & 1 for x in raw[:6]) or any(not (48<=x<=57 or 65<=x<=90) for x in name):
            return 'Malformed AX.25 address: ' + packet.hex()
        call = address(raw)
        # Bit 7 is a command/response bit on source/destination, but the
        # has-been-repeated (H) bit on digipeater addresses only.
        if len(addresses) >= 2 and raw[6] & 0x80:
            call += '*'
        addresses.append(call)
        offset += 7
        if raw[6] & 1:
            break
    else:
        return 'Malformed AX.25: ' + packet.hex()
    if len(addresses) < 2 or offset >= len(packet):
        return 'Short AX.25: ' + packet.hex()
    control = packet[offset]
    offset += 1
    # Basic AX.25 sequence numbering. Extended mode displayed as raw bytes.
    pid = None
    if control & 1 == 0 or control == 0x03 or control == 0x13:
        if offset < len(packet):
            pid = packet[offset]
            offset += 1
    route = addresses[1] + '>' + addresses[0]
    if len(addresses) > 2:
        route += ',' + ','.join(addresses[2:])
    body = packet[offset:]
    body = ''.join(chr(x) if 32 <= x < 127 else '\\x%02x' % x for x in body)
    return '%s ctl=%02x%s %s' % (route, control, '' if pid is None else ' pid=%02x' % pid, body)


def frames(chunks):
    frame = bytearray()
    escaped = False
    active = False
    for chunk in chunks:
        for byte in chunk:
            if byte == 0xc0:
                if active and frame:
                    yield bytes(frame)
                frame.clear()
                active = True
                escaped = False
            elif active:
                if escaped:
                    if byte not in (0xdc, 0xdd):
                        active = False
                        frame.clear()
                    else:
                        frame.append(0xc0 if byte == 0xdc else 0xdb)
                    escaped = False
                elif byte == 0xdb:
                    escaped = True
                else:
                    frame.append(byte)
                if len(frame) > 65536:
                    frame.clear()
                    active = False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('device', help='Paired RFCOMM TTY, e.g. /dev/rfcomm0')
    args = parser.parse_args()
    fd = os.open(args.device, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
    previous = termios.tcgetattr(fd)
    raw = termios.tcgetattr(fd)
    raw[0] = raw[1] = raw[3] = 0
    raw[2] = (raw[2] & ~(termios.CSIZE | termios.PARENB)) | termios.CS8 | termios.CREAD | termios.CLOCAL
    raw[6][termios.VMIN] = 1
    raw[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, raw)
    print('Receive only. Ctrl-C to exit.', flush=True)
    def chunks():
        while True:
            select.select([fd], [], [])
            data = os.read(fd, 4096)
            if not data:
                return
            yield data
    try:
        for frame in frames(chunks()):
            line = describe(frame)
            if line is not None:
                print(datetime.datetime.now().isoformat(timespec='seconds'), line, flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        termios.tcsetattr(fd, termios.TCSANOW, previous)
        os.close(fd)

if __name__ == '__main__':
    main()
