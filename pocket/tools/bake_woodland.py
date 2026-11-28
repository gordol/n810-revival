"""Store sparse canopy samples inside OpenStreetMap woodland polygons and outside holes."""
from collections import defaultdict
import json
import math
import sqlite3
import subprocess
import zlib

from pnw.terrain import location


def add_woodland(region,folder,database):
    woods=folder/'woodland.pbf'
    subprocess.run(['osmium','tags-filter',region,'wr/natural=wood','wr/landuse=forest','-o',woods],check=True)
    tiles=defaultdict(set)
    spacing=46.
    with subprocess.Popen(['osmium','export',woods,'-f','geojsonseq'],stdout=subprocess.PIPE) as source:
        for line in source.stdout:
            feature=json.loads(line.lstrip(b'\x1e'))
            shape=feature['geometry']
            if shape['type'] not in ('Polygon','MultiPolygon'):continue
            polygons=[shape['coordinates']] if shape['type']=='Polygon' else shape['coordinates']
            for polygon in polygons:
                rows=defaultdict(list)
                for ring in polygon:
                    points=[location('sound',lat,lon) for lon,lat in ring]
                    for (x,z),(u,v) in zip(points,points[1:]):
                        for j in range(math.ceil(min(z,v)/spacing),math.ceil(max(z,v)/spacing)):
                            rows[j].append(x+(u-x)*(j*spacing-z)/(v-z))
                for j,cuts in rows.items():
                    cuts.sort()
                    for left,right in zip(cuts[::2],cuts[1::2]):
                        for i in range(math.floor(left/spacing),math.ceil(right/spacing)):
                            seed=(i*73856093 ^ j*19349663)&65535
                            u=round((i+.12+.76*seed/65535)*spacing)
                            v=round(j*spacing)
                            if left<=u<right:tiles[u//512,v//512].add((u,v))
        if source.wait():raise SystemExit('Woodland export failed.')
    with sqlite3.connect(database) as db:
        db.executemany('INSERT INTO features VALUES (?,?,?,?)',(
            (tx,tz,'woodland',zlib.compress(json.dumps(sorted(points),separators=(',',':')).encode(),2))
            for (tx,tz),points in tiles.items()))
        db.execute('PRAGMA user_version=5')
    print(f'Prepared mapped woodland canopy in {len(tiles):,} tiles',flush=True)
