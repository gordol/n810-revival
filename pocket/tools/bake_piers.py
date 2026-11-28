"""Bake Seattle and Tacoma waterfront pier outlines from an OSM GeoJSON sequence."""
import json
import sys

from seattle_buildings import triangles

WATERFRONTS = ((-122.37, 47.57, -122.32, 47.635), (-122.48, 47.24, -122.36, 47.305))


def piers(features):
    for line in features:
        feature = json.loads(line.lstrip('\x1e'))
        if feature['properties'].get('man_made') != 'pier':
            continue
        geometry = feature['geometry']
        if geometry['type'] not in ('Polygon', 'MultiPolygon'):
            continue
        polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
        for polygon in polygons:
            lon, lat = polygon[0][0][:2]
            if len(polygon) != 1 or not any(w <= lon <= e and s <= lat <= n for w, s, e, n in WATERFRONTS):
                continue
            ring = [[round(x * 1e7), round(y * 1e7)] for x, y in polygon[0][:-1]]
            faces = triangles(ring)
            if faces:
                yield ring, faces


if __name__ == '__main__':
    print(json.dumps(list(piers(sys.stdin)), separators=(',', ':')))
