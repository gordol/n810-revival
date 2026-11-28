"""Prepare the locally installed Puget Sound scenery database."""
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

from bake_region import build

SOURCE = 'https://download.geofabrik.de/north-america/us/washington-latest.osm.pbf'
BOUNDS = '-123.30,46.70,-121.50,48.15'


def prepare():
    data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    target = Path(os.environ.get('POCKET_REGION_SCENERY') or
                  data / 'pocket/rainier-walk/puget-sound-scenery.sqlite')
    if target.is_file():
        with sqlite3.connect(f'{target.resolve().as_uri()}?mode=ro', uri=True) as db:
            db.execute('SELECT tx,tz,model,data FROM features LIMIT 1').fetchone()
        print(f'Using regional scenery from {target}')
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as work:
        folder = Path(work)
        database = folder / 'region.sqlite'
        osmium = shutil.which('osmium')
        if not osmium and sys.platform == 'darwin':
            subprocess.run(['brew', 'install', 'osmium-tool'], check=True)
        elif not osmium and 'com.termux' in os.environ.get('PREFIX', ''):
            subprocess.run(['pkg', 'install', '-y', 'osmium-tool'], check=True)
        if not shutil.which('osmium'):
            raise SystemExit('Install osmium-tool and retry make regional-scenery.')
        state = folder / 'washington.osm.pbf'
        region = folder / 'region.osm.pbf'
        features = folder / 'features.osm.pbf'
        subprocess.run(['curl', '--fail', '--location', '--retry', '3', '--output',
                        state, os.environ.get('POCKET_WASHINGTON_PBF_URL') or SOURCE], check=True)
        subprocess.run(['osmium', 'extract', '-b', BOUNDS, state, '-o', region], check=True)
        state.unlink()
        subprocess.run(['osmium', 'tags-filter', region, 'w/building', 'n/shop', 'n/amenity',
                        'n/tourism', 'n/natural=tree', '-o', features], check=True)
        region.unlink()
        with subprocess.Popen(['osmium', 'export', features, '-f', 'geojsonseq'],
                              stdout=subprocess.PIPE) as export:
            try:
                counts = build([export.stdout], database)
            finally:
                export.stdout.close()
            if export.wait():
                raise SystemExit('Regional feature export failed.')
        if not all(counts[k] for k in ('building', 'place', 'tree')):
            raise SystemExit(f'Incomplete regional extract: {counts}')
        os.replace(database, target)
        print(f'Installed {target} ({dict(counts)})')


if __name__ == '__main__':
    prepare()
