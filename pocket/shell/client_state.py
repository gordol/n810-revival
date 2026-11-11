"""One saved workspace for Pocket's graphical and terminal clients."""
import os
from pathlib import Path
import re


def state_directory(state=None, instance='default'):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', instance):
        raise ValueError('instance must contain 1–64 letters, digits, underscores or hyphens')
    return (state or Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'pocket'/instance).expanduser().resolve()


def prepare_station_database(state, arguments):
    """Create the GUI-owned empty catalogue on first launch."""
    path=state/'directory.sqlite3'
    if any(arg=='--station-db' or arg.startswith('--station-db=') for arg in arguments):
        return path
    if not path.exists():
        import importlib.util
        source=Path(__file__).resolve().parent/'vendor/packet-console/n810-directory-model.py'
        spec=importlib.util.spec_from_file_location('gui_station_schema',source)
        model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
        connection=model.database(path)
        connection.close()
    return path
