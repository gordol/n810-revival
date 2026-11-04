#!/usr/bin/env python3
"""Laptop-only Natural Earth + NOAA ETOPO overview; Pillow/NumPy build deps only."""
import argparse,base64,datetime,gzip,json,pathlib,zlib
from PIL import Image,ImageDraw
import numpy as np


def build(folder,output):
    west,south,east,north=-128.,43.,-116.,52.
    width,height=1200,900
    image=Image.new('L',(width,height),1);draw=ImageDraw.Draw(image)
    def pixels(ring):return [((lon-west)/(east-west)*(width-1),(north-lat)/(north-south)*(height-1)) for lon,lat,*_ in ring]
    def paint(path,value,hole):
        data=json.loads(path.read_text())
        used=0
        for feature in data['features']:
            geom=feature['geometry']
            if not geom:continue
            polygons=[geom['coordinates']] if geom['type']=='Polygon' else geom['coordinates'] if geom['type']=='MultiPolygon' else []
            for rings in polygons:
                if not rings:continue
                xs,ys=zip(*[(p[0],p[1]) for p in rings[0]])
                if max(xs)<west or min(xs)>east or max(ys)<south or min(ys)>north:continue
                draw.polygon(pixels(rings[0]),fill=value)
                for ring in rings[1:]:draw.polygon(pixels(ring),fill=hole)
                used+=1
        return used
    land=paint(folder/'pnw-land.geojson',0,1)
    lakes=paint(folder/'pnw-lakes.geojson',2,0)
    table=json.loads((folder/'pnw-elevation.json').read_text())['table']
    indexes={name:i for i,name in enumerate(table['columnNames'])}
    rows=table['rows'];lat_i=indexes['latitude'];lon_i=indexes['longitude'];z_i=indexes['altitude']
    lats=sorted({r[lat_i] for r in rows},reverse=True);lons=sorted({r[lon_i] for r in rows})
    ys={lat:i for i,lat in enumerate(lats)};xs={lon:i for i,lon in enumerate(lons)}
    grid=np.zeros((len(lats),len(lons)),dtype=np.float32)
    for row in rows:grid[ys[row[lat_i]],xs[row[lon_i]]]=row[z_i] if row[z_i] is not None else 0
    elevation=np.array(Image.fromarray(grid).resize((width,height),Image.Resampling.BILINEAR))
    water=np.array(image);bands=np.zeros_like(water)
    for threshold in (200,500,1000,1800,2800):bands+=(elevation>=threshold).astype(np.uint8)
    raster=np.where(water==0,bands<<2,water).astype(np.uint8)
    pack=dict(version=1,name='Pacific Northwest overview',bbox=[west,south,east,north],
        generated=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        attribution='Natural Earth (public domain) / NOAA ETOPO1; detailed overlays retain their own attribution',
        license_url='https://www.naturalearthdata.com/about/terms-of-use/',labels=[],
        terrain=dict(source='NOAA ETOPO1',source_url='https://data.pmel.noaa.gov/socat/erddap/griddap/etopo180.html',bands_m=[200,500,1000,1800,2800]),
        water_classes={'1':'sea','2':'inland water'},layers=['land','water','elevation'],
        raster=dict(width=width,height=height,encoding='zlib-base64-u8',data=base64.b64encode(zlib.compress(raster.tobytes(),9)).decode()))
    places=folder/'pnw-places.geojson'
    if places.exists():
        for feature in json.loads(places.read_text())['features']:
            lon,lat=feature['geometry']['coordinates'];props=feature['properties']
            if west<=lon<=east and south<=lat<=north:
                population=int(props.get('pop_max') or 0)
                if population>=50000 or props['name'] in ('Victoria','Nanaimo','Bellingham','Olympia','Kamloops','Bend'):
                    pack['labels'].append(dict(name=props['name'],lon=lon,lat=lat,kind='city',population=population))
    with gzip.open(output,'wt') as f:json.dump(pack,f,separators=(',',':'))
    pathlib.Path(str(output)[:-8]+'.meta.json').write_text(json.dumps(pack,separators=(',',':')))
    colors=np.array([[20,47,39],[39,61,50],[59,70,53],[75,85,83],[109,120,123],[173,182,181]],dtype=np.uint8)
    preview=colors[bands];preview[water==1]=[25,63,89];preview[water==2]=[42,85,110]
    Image.fromarray(preview).save(folder/'pnw-overview-preview.png')
    print('Overview:',land,'land polygons,',lakes,'lakes;',output.stat().st_size,'bytes')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=pathlib.Path,default=pathlib.Path('packet-console/map-sources'));p.add_argument('--output',type=pathlib.Path,default=pathlib.Path('packet-console/maps/pnw-overview.json.gz'))
    a=p.parse_args();build(a.source,a.output)
