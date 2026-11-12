#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compose the ARM Pocket frontend from the pinned Mesa and Python headers."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys


REPO = Path(__file__).resolve().parents[2]


def build(mesa, headers, output):
    if output.exists():
        raise ValueError('Use a new frontend output directory')
    if not (mesa / 'libOSMesa.so.8').is_file() or not (mesa / 'include/GL/osmesa.h').is_file():
        raise ValueError('Mesa package needs OSMesa library and headers')
    output.mkdir(parents=True)
    native = output / 'native'
    subprocess.run([sys.executable, str(REPO / 'pocket/tools/build_native.py'),
                    '--arm-headers', str(headers), '--arm-vfp', '--output', str(native)], check=True)
    subprocess.run([sys.executable, str(REPO / 'pocket/graphics/build_nokia.py'),
                    '--output', str(output), '--mesa-include', str(mesa / 'include'),
                    '--mesa-library', str(mesa / 'libOSMesa.so.8'), '--scene-gl'], check=True)
    shutil.copyfile(native / '_cellengine.abi3.so', output / '_cellengine.abi3.so')
    shutil.copyfile(native / 'provenance.json', output / 'provenance.json')
    shutil.copyfile(mesa / 'libOSMesa.so.8', output / 'libOSMesa.so.8')
    config = {'graphics_path': str(REPO / 'pocket/graphics'),
              'font': str(output / 'console-font.psf'),
              'gpu_library': str(output / 'renderer.so'),
              'display_library': str(output / 'window.so'),
              'native_library': str(output / '_cellengine.abi3.so')}
    (output / 'frontend.json').write_text(json.dumps(config, indent=2) + '\n')
    return output / 'frontend.json'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-package', type=Path, required=True)
    parser.add_argument('--arm-headers', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(build(args.mesa_package.resolve(), args.arm_headers.resolve(), args.output.resolve()))


if __name__ == '__main__':
    main()
