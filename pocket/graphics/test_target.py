# SPDX-License-Identifier: GPL-2.0-or-later
"""Build/run the shared-target pixel comparison; never contacts a device."""
import argparse
import os
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', required=True, type=Path,
                        help='directory containing renderer.so')
    parser.add_argument('--mesa-include', required=True, type=Path)
    parser.add_argument('--mesa-library', required=True, type=Path)
    parser.add_argument('--cc', default='cc', help='compiler and target flags')
    parser.add_argument('--runner', default='', help='optional emulator and flags')
    args = parser.parse_args()
    build = args.build.resolve()
    library = args.mesa_library.resolve()
    source = Path(__file__).resolve().parent / 'native/test_pixel_target.c'
    binary = build / 'test-pixel-target'
    subprocess.run([
        *shlex.split(args.cc), '-O2', '-std=c99', '-D_GNU_SOURCE',
        '-Wall', '-Wextra', '-Werror', '-I' + str(args.mesa_include.resolve()),
        str(source), str(build / 'renderer.so'), str(library), '-lm',
        '-Wl,-rpath,' + str(build), '-Wl,-rpath,' + str(library.parent),
        '-o', str(binary),
    ], check=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith('N810_MBX_')}
    env.update(GALLIUM_DRIVER='softpipe',
               LD_LIBRARY_PATH=str(build) + ':' + str(library.parent))
    subprocess.run([*shlex.split(args.runner), str(binary)], env=env,
                   check=True, timeout=180)


if __name__ == '__main__':
    main()
