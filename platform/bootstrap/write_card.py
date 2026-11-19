#!/usr/bin/env python3
"""Write a verified N810 image to an explicitly selected removable macOS card."""
import argparse
import hashlib
import json
import plistlib
from pathlib import Path
import re
import subprocess
import sys


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def card_info(identifier):
    if not re.fullmatch(r'disk[0-9]+', identifier):
        raise ValueError('Select a whole disk such as disk4, not a partition or path.')
    info = plistlib.loads(run('diskutil', 'info', '-plist', identifier,
                             stdout=subprocess.PIPE).stdout)
    if not info.get('RemovableMedia') or info.get('WholeDisk') is not True:
        raise ValueError('The selected disk is not a removable whole disk.')
    if info.get('BusProtocol') != 'Secure Digital':
        raise ValueError('The selected disk is not an SD card.')
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kit', type=Path, help='Directory containing BUILD.json and n810-sd.img')
    parser.add_argument('disk', help='Current whole-disk identifier, such as disk4')
    parser.add_argument('--write', action='store_true', help='Erase the selected card after verification')
    args = parser.parse_args()
    if sys.platform != 'darwin':
        parser.error('This writer uses macOS diskutil. Use the Linux guide on Linux.')
    image = args.kit / 'n810-sd.img'
    report = json.loads((args.kit / 'BUILD.json').read_text())
    if digest(image) != report['sd_image_sha256']:
        parser.error('Image checksum does not match BUILD.json.')
    info = card_info(args.disk)
    if image.stat().st_size >= info['TotalSize']:
        parser.error('The image does not fit on the selected card.')
    print(f"Verified {image} ({image.stat().st_size} bytes)", flush=True)
    print(f"Target /dev/{args.disk}: {info.get('MediaName', 'SD card')} ({info['TotalSize']} bytes)", flush=True)
    if not args.write:
        print('Dry run only. Add --write to erase and write this card.', flush=True)
        return
    confirmation = input(f'Type ERASE {args.disk} to overwrite this card: ')
    if confirmation != f'ERASE {args.disk}':
        parser.error('Card write cancelled.')
    card_info(args.disk)
    run('diskutil', 'unmountDisk', '/dev/' + args.disk)
    run('sudo', 'dd', 'if=' + str(image), 'of=/dev/r' + args.disk, 'bs=4m')
    run('diskutil', 'eject', '/dev/' + args.disk)
    print('Card write complete. Reinsert it to verify the partition.', flush=True)


if __name__ == '__main__':
    main()
