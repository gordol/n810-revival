"""Prepare the locally installed Puget Sound scenery database."""
import json
import math
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


AIRPORTS = ((47.1039, -122.2871), (47.268, -122.578), (47.451, -122.310))
STREETS = ('primary', 'secondary', 'tertiary', 'residential', 'unclassified', 'service')


def add_airport_roads(state, folder, database):
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE airport_roads (way INTEGER PRIMARY KEY, name TEXT, kind TEXT, points TEXT)')
        for index, (lat, lon) in enumerate(AIRPORTS):
            delta = .032
            west = delta / math.cos(math.radians(lat))
            bbox = f'{lon-west},{lat-delta},{lon+west},{lat+delta}'
            crop = folder / f'airport-{index}.osm.pbf'
            streets = folder / f'streets-{index}.osm.pbf'
            subprocess.run(['osmium', 'extract', '-b', bbox, state, '-o', crop], check=True)
            subprocess.run(['osmium', 'tags-filter', crop, 'w/highway='+','.join(STREETS),
                            '-o', streets], check=True)
            with subprocess.Popen(['osmium', 'export', streets, '-f', 'geojsonseq',
                                   '--add-unique-id=type_id'], stdout=subprocess.PIPE) as export:
                for line in export.stdout:
                    row=json.loads(line.lstrip(b'\x1e'))
                    tags=row['properties']
                    if row['geometry']['type']!='LineString' or tags.get('bridge') or tags.get('tunnel'):
                        continue
                    coords=[[round(x*1e7),round(y*1e7)] for x,y in row['geometry']['coordinates']]
                    db.execute('INSERT OR IGNORE INTO airport_roads VALUES (?,?,?,?)',
                               (int(row['id'][1:]),tags.get('name',''),tags['highway'],json.dumps(coords)))
                if export.wait():raise SystemExit('Airport road export failed.')
        db.execute('PRAGMA user_version=2')


def prepare():
    data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    target = Path(os.environ.get('POCKET_REGION_SCENERY') or
                  data / 'pocket/rainier-walk/puget-sound-scenery.sqlite')
    if target.is_file():
        with sqlite3.connect(f'{target.resolve().as_uri()}?mode=ro', uri=True) as db:
            db.execute('SELECT tx,tz,model,data FROM features LIMIT 1').fetchone()
            if db.execute('PRAGMA user_version').fetchone()[0]>=2 or os.environ.get('POCKET_REGION_SCENERY'):
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
        add_airport_roads(state, folder, database)
        os.replace(database, target)
        print(f'Installed {target} ({dict(counts)})')


if __name__ == '__main__':
    prepare()
