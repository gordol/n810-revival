"""Prepare the locally installed Puget Sound scenery database."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zlib

from bake_region import build
from bake_woodland import add_woodland

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
                    if not line.strip():
                        continue
                    row=json.loads(line.lstrip(b'\x1e'))
                    tags=row['properties']
                    if row['geometry']['type']!='LineString' or tags.get('bridge') or tags.get('tunnel'):
                        continue
                    coords=[[round(x*1e7),round(y*1e7)] for x,y in row['geometry']['coordinates']]
                    db.execute('INSERT OR IGNORE INTO airport_roads VALUES (?,?,?,?)',
                               (int(row['id'][1:]),tags.get('name',''),tags['highway'],json.dumps(coords)))
                if export.wait():raise SystemExit('Airport road export failed.')
        db.execute('PRAGMA user_version=3')


def add_regional_roads(region,folder,database):
    from pnw.regional_roads import SEGMENT,WIDTHS
    from pnw.terrain import location
    from collections import defaultdict
    assets=Path(__file__).resolve().parents[1]/'graphics/assets/seattle'
    known=set()
    for name in ('streets','tacoma-streets','overpasses'):
        known.update(map(int,json.loads((assets/(name+'.json')).read_text())))
    freeway=json.loads((assets/'freeway.json').read_text())['roads']
    known.update(row[0] for row in freeway if int(row[2].get('layer',0))>=0)
    known.update(row[0] for row in json.loads((assets/'eastside-highways.json').read_text()))
    kinds=list(WIDTHS)+[k+'_link' for k in ('motorway','trunk','primary','secondary','tertiary')]
    streets=folder/'regional-roads.pbf'
    subprocess.run(['osmium','tags-filter',region,'w/highway='+','.join(kinds),'-o',streets],check=True)
    with sqlite3.connect(database) as db:
        known.update(r[0] for r in db.execute('SELECT way FROM airport_roads'))
        tiles=defaultdict(bytearray)
        ways=0
        with subprocess.Popen(['osmium','export',streets,'-f','geojsonseq','--add-unique-id=type_id'],stdout=subprocess.PIPE) as export:
            for line in export.stdout:
                row=json.loads(line.lstrip(b'\x1e'));props=row['properties']
                if row['geometry']['type']!='LineString' or not row['id'].startswith('w'):continue
                if int(row['id'][1:]) in known or props.get('area')=='yes':continue
                kind=props.get('highway')
                if kind not in kinds:continue
                width=2.9 if kind.endswith('_link') else WIDTHS[kind]
                points=[location('sound',lat,lon) for lon,lat in row['geometry']['coordinates']]
                ways+=1
                for (x,z),(u,v) in zip(points,points[1:]):
                    steps=max(1,math.ceil(math.hypot(u-x,v-z)/48))
                    ax,az=round(10*x),round(10*z)
                    for i in range(1,steps+1):
                        bx,bz=round(10*(x+(u-x)*i/steps)),round(10*(z+(v-z)*i/steps))
                        if (ax,az)!=(bx,bz):
                            tiles[(ax+bx)//10240,(az+bz)//10240].extend(SEGMENT.pack(ax,az,bx,bz,round(width*10)))
                        ax,az=bx,bz
            if export.wait():raise SystemExit('Regional road export failed.')
        if not ways:raise SystemExit('No regional roads exported.')
        db.execute('CREATE TABLE road_tiles(tx INTEGER,tz INTEGER,data BLOB,PRIMARY KEY(tx,tz)) WITHOUT ROWID')
        db.executemany('INSERT INTO road_tiles VALUES (?,?,?)',((x,z,zlib.compress(data,3)) for (x,z),data in tiles.items()))
        db.execute('PRAGMA user_version=4')
        print(f'Indexed {ways:,} additional mapped road ways in {len(tiles):,} tiles',flush=True)


def cached_region():
    source = os.environ.get('POCKET_WASHINGTON_PBF_URL') or SOURCE
    cache = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache')
    cache = cache / 'pocket/rainier-walk'
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(f'{source} {BOUNDS}'.encode()).hexdigest()[:16]
    region = cache / f'puget-sound-{key}.osm.pbf'
    with (cache / f'{key}.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if region.is_file():
            print(f'Reusing cached OpenStreetMap extract from {region}', flush=True)
            return region
        with tempfile.TemporaryDirectory(dir=cache) as work:
            state = Path(work) / 'washington.osm.pbf'
            clipped = Path(work) / 'region.osm.pbf'
            print('Downloading Washington OpenStreetMap source for the regional cache', flush=True)
            subprocess.run(['curl', '--fail', '--location', '--retry', '3', '--output',
                            state, source], check=True)
            subprocess.run(['osmium', 'extract', '-b', BOUNDS, state, '-o', clipped], check=True)
            os.replace(clipped, region)
    return region


def prepare(launch=False):
    data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
    target = Path(os.environ.get('POCKET_REGION_SCENERY') or
                  data / 'pocket/rainier-walk/puget-sound-scenery.sqlite')
    target.parent.mkdir(parents=True, exist_ok=True)
    def ready():
        if not target.is_file():
            return False
        with sqlite3.connect(f'{target.resolve().as_uri()}?mode=ro', uri=True) as db:
            db.execute('SELECT tx,tz,model,data FROM features LIMIT 1').fetchone()
            version = db.execute('PRAGMA user_version').fetchone()[0]
        if launch or version >= 5 or os.environ.get('POCKET_REGION_SCENERY'):
            print(f'Using installed regional scenery from {target}')
            return True
        return False

    if ready():
        return
    with (target.parent / (target.name + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if ready():
            return
        install(target)


def install(target):
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
        region = cached_region()
        features = folder / 'features.osm.pbf'
        subprocess.run(['osmium', 'tags-filter', region, 'w/building', 'n/shop', 'n/amenity',
                        'n/tourism', 'n/natural=tree', 'n/highway=traffic_signals', 'w/parking=multi-storey', '-o', features], check=True)
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
        add_airport_roads(region, folder, database)
        add_regional_roads(region,folder,database)
        add_woodland(region,folder,database)
        os.replace(database, target)
        print(f'Installed {target} ({dict(counts)})')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--launch', action='store_true', help='reuse an installed pack of any supported version')
    prepare(parser.parse_args().launch)
