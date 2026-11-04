"""Declared read-only Directory queries using the packaged station projection."""
import functools
import importlib.util
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from app_command import Argument, Command, normalize_commands
from app_registry import ServiceUse


@functools.lru_cache(maxsize=1)
def projection():
    path = Path(__file__).resolve().parent / 'vendor/packet-console/n810-directory-projection.py'
    spec = importlib.util.spec_from_file_location('app_cli_directory_projection', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReadOnlyDirectory:
    """Explicitly selected database; no schema initialization or background owner."""
    def __init__(self, database):
        if not isinstance(database, str) or not 1 <= len(database) <= 1024 or not database.isprintable():
            raise ValueError('Directory database must be a printable absolute path')
        path = Path(database)
        if not path.is_absolute():
            raise ValueError('Directory database must be an absolute path')
        if not path.is_file():
            raise ValueError('Directory database must be an existing regular file')
        self.database = database

    def list(self, values):
        try:
            return projection().list_stations(self.database, {
                'limit': values['limit'], 'offset': values['offset'], 'buddy_only': values['buddies']})
        except sqlite3.Error as error:
            raise ValueError('Directory query failed: ' + str(error)) from None

    def details(self, values):
        try:
            result = projection().station_details(self.database, values['call'],
                        relay_limit=values['relay-limit'], width=values['width'])
        except sqlite3.Error as error:
            raise ValueError('Directory query failed: ' + str(error)) from None
        if result is None:
            raise ValueError('Station not found: ' + values['call'])
        return result


def list_stations(context, values):
    return context.services['directory'].list(values)


def station_details(context, values):
    return context.services['directory'].details(values)


COMMANDS = normalize_commands((
    Command('list', 'List retained stations from the selected read-only database.', list_stations,
            (Argument('limit', 'int', 'Maximum stations.', default=50, minimum=1, maximum=200),
             Argument('offset', 'int', 'Stations to skip.', default=0, minimum=0, maximum=1000000),
             Argument('buddies', 'bool', 'Only saved buddies.', default=False)),
            capability='view_directory', manual_topic='aprs.heard'),
    Command('details', 'Inspect one retained station.', station_details,
            (Argument('call', 'call', 'Callsign and optional SSID.', required=True),
             Argument('relay-limit', 'int', 'Maximum relay records.', default=50, minimum=0, maximum=200),
             Argument('width', 'int', 'Readable detail width.', default=72, minimum=20, maximum=240)),
            capability='view_directory'),
))


def entry():
    """Metadata view for the CLI, not a fabricated window registration."""
    return SimpleNamespace(id='directory', title='Directory',
            description='Read-only station queries. Requires --directory-db ABSOLUTE.',
            commands=COMMANDS, uses=(ServiceUse('directory'),))
