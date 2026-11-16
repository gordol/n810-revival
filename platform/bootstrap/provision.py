#!/usr/bin/env python3
"""Use a prebuilt kit to provision another N810 from a Linux host or tablet."""
import argparse
from pathlib import Path
from internal_installer import verify_local_kit, identify_device, flash_kernel
from linux_storage import install


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'identify', 'write', 'flash'))
    parser.add_argument('--kit', type=Path)
    parser.add_argument('--disk')
    parser.add_argument('--usb-port')
    parser.add_argument('--erase', action='store_true')
    parser.add_argument('--flasher', type=Path, default=Path(__file__).resolve().parents[1]/'flasher/0xFFFF')
    args = parser.parse_args()
    if args.action == 'identify': print(identify_device(args.flasher)); return
    if not args.kit: parser.error('--kit is required')
    if args.action == 'check':
        verify_local_kit(args.kit); print('Kit files and expanded root verified; no device accessed')
    elif args.action == 'write':
        if not args.disk or not args.usb_port: parser.error('--disk and --usb-port are required')
        install(args.kit, args.disk, args.usb_port, args.erase)
    else: print(flash_kernel(args.kit, args.flasher, print))


if __name__ == '__main__': main()
