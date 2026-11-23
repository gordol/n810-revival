"""Push prepared runtime maps to the nokia account on an N810 over SSH."""
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import re
import subprocess
from pathlib import Path

from install_reference_data import inventory, stream

# Stage on persistent storage. A broken upload cannot start the installer.
REMOTE_INSTALL = """
set -eu
command -v n810-install-reference-data >/dev/null
umask 077
parent="$HOME/.local/share"
mkdir -p "$parent"
exec 9<"$parent"
flock -n 9 || { echo 'Another map transfer is active' >&2; exit 1; }
stage=$(mktemp -d "$parent/.pocket-maps.XXXXXXXX")
trap 'rm -rf "$stage"' EXIT
trap 'exit 1' HUP INT TERM
tar -xf - -C "$stage"
n810-install-reference-data --verify "$stage"
n810-install-reference-data --source "$stage" --target "$parent/pocket"
"""


def push(source, host, maps=None):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', host):
        raise ValueError('Enter an SSH host alias, hostname or IPv4 address')
    files = inventory(source, maps)
    command = ['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15',
               '-l', 'nokia', '--', host, REMOTE_INSTALL]
    with subprocess.Popen(command, stdin=subprocess.PIPE) as process:
        try:
            with process.stdin as output:
                stream(files, output)
        except BrokenPipeError:
            if process.wait():
                raise RuntimeError(f'SSH map transfer failed (exit {process.returncode})') from None
            raise
        if process.wait():
            raise RuntimeError(f'N810 map installation failed (exit {process.returncode})')
    print('Maps verified and installed. Restart Pocket on the N810 to load them.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('host', help='N810 hostname or configured SSH alias')
    parser.add_argument('--maps', type=Path, help='Separate prepared map views')
    args = parser.parse_args()
    try:
        push(args.source, args.host, args.maps)
    except (ValueError, OSError, RuntimeError) as error:
        parser.exit(1, f'{error}\n')
