"""One-shot Directory CLI. Queries require an explicit --directory-db ABSOLUTE.

Example: python3 app_cli.py --directory-db /absolute/directory.db directory list
No database is guessed, created, migrated or opened by discovery/help.
"""
import argparse
from pathlib import Path
import sys
from types import MappingProxyType, SimpleNamespace

import app_command_cli
from directory_commands import ReadOnlyDirectory, entry


def selected_context(database):
    service = ReadOnlyDirectory(database)
    return SimpleNamespace(capabilities=frozenset({'view_directory'}),
                           services=MappingProxyType({'directory': service}))


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    bootstrap = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    bootstrap.add_argument('--directory-db', metavar='ABSOLUTE')
    options, remaining = bootstrap.parse_known_args(arguments)
    entries = (entry(),)
    discovery = any(flag in remaining for flag in ('--list-apps', '--list-commands', '--complete', '--help', '-h'))
    if discovery or not remaining:
        return app_command_cli.run(entries, None, remaining)
    if options.directory_db is None:
        bootstrap.error('Queries require --directory-db ABSOLUTE; no database is selected automatically')
    if not Path(options.directory_db).is_absolute():
        bootstrap.error('--directory-db must be an absolute path')
    return app_command_cli.run(entries, selected_context(options.directory_db), remaining)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print('Error: ' + app_command_cli.printable(error), file=sys.stderr)
        raise SystemExit(1)
