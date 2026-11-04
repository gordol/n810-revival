"""Launch an independent shell; service attachments are explicit UI actions."""
import argparse
import os
from pathlib import Path
import re
import sys


def command(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--instance', default='default', help='independent local state namespace')
    parser.add_argument('--state', type=Path, help='explicit instance state directory')
    args, rest = parser.parse_known_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.instance):
        parser.error('instance must contain 1–64 letters, digits, underscores or hyphens')
    state = (args.state or Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'pocket'/args.instance).expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    return [sys.executable, str(Path(__file__).with_name('demo.py')), '--shell',
            '--session', str(state/'desktop.json'), '--app-state', str(state),
            '--station-db', str(state/'directory.sqlite3'), *rest]


def main():
    argv = command()
    # Keep the already initialized interpreter and standard-library modules.
    sys.argv = argv[1:]
    directory=str(Path(__file__).resolve().parent)
    if not sys.path or sys.path[0]!=directory:sys.path.insert(0,directory)
    from desktop import main as desktop_main
    desktop_main()


if __name__ == '__main__':
    main()
