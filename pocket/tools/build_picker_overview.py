"""Convert Natural Earth's 1:50m land and populated places GeoJSON to a picker asset."""
import argparse
import json
from pathlib import Path


def build(land, cities):
    paths = []
    for feature in land['features']:
        geometry = feature['geometry']
        polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
        for polygon in polygons:
            for ring in polygon:
                points = [f'{x:.4f},{-y:.4f}' for x, y in ring[:-1]]
                paths.append('M'+' '.join(points)+'Z')
    places = []
    for feature in cities['features']:
        properties = feature['properties']
        x, y = feature['geometry']['coordinates']
        places.append([properties['name'], properties['adm0name'], round(x,4), round(y,4), properties['pop_max']])
    return dict(land=''.join(paths), places=sorted(places,key=lambda p:-p[-1]))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('land','cities','output'):
        parser.add_argument(name,type=Path)
    args = parser.parse_args()
    data = build(json.loads(args.land.read_text()),json.loads(args.cities.read_text()))
    args.output.write_text(json.dumps(data,separators=(',',':'),ensure_ascii=False)+'\n')
