#!/usr/bin/env python3
"""Bake a bounded, versioned Fixed v2 geographic pack from local source data."""
import argparse,hashlib,importlib.util,json,struct,sys,zlib
from pathlib import Path
HERE=Path(__file__).resolve().parent;TRIAL=HERE.parent;ROOT=TRIAL.parents[1];SOURCES=ROOT.parents[1]/'packet-console'
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(TRIAL))
from geographic_palette import engine_class,PALETTE_VERSION,BREAKPOINTS
from paint import ink
CELL=struct.Struct('<IQ')
CENTER=(47.21,-122.49);SPAN=40.

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path)
    regions={'lakewood':(CENTER,SPAN,(384,800),'pack'),
             'lakewood-lod':(CENTER,SPAN,(192,384,800),'lakewood-lod-pack'),
             'puget':((47.5,-122.5),400.,(192,800),'puget-pack'),
             'puget-lod':((47.5,-122.5),400.,(192,384,800),'puget-lod-pack'),
             'lakewood-fine':((5.5355,5.5655),8.,(800,),'lakewood-fine-pack'),
             'lakewood-fine-lod':((5.5355,5.5655),8.,(384,800),'lakewood-fine-lod-pack'),
             'rainier':((46.8523,-121.7603),40.,(384,),'rainier-pack'),
             'rainier-lod':((46.8523,-121.7603),40.,(192,384),'rainier-lod-pack')}
    parser.add_argument('--region',choices=tuple(regions),default='lakewood');args=parser.parse_args()
    center,span,widths,default_directory=regions[args.region]
    output=args.output or HERE/default_directory
    if output.exists() and any(output.iterdir()):parser.error('Output must be new or empty; existing packs are preserved')
    output.mkdir(parents=True,exist_ok=True)
    spec=importlib.util.spec_from_file_location('fixed_v2_bake_engine',SOURCES/'n810-map-next.py')
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
    engine=engine_class(module)(SOURCES/'maps','rgb');levels=[]
    for width in widths:
        height=width//2;view=module.Viewport(center,span,width,height)
        frame,legend=engine.prepare(view,True,True);tiles={};colors={}
        for ty in range((height+15)//16):
            for tx in range((width+31)//32):
                w,h=min(32,width-tx*32),min(16,height-ty*16);raw=bytearray()
                for y in range(h):
                    for x in range(w):
                        char,fg,bg=frame[(ty*16+y)*width+tx*32+x];key=fg,bg
                        if key not in colors:colors[key]=ink(*fg,background=bg)
                        raw.extend(CELL.pack(ord(char),colors[key]))
                data=zlib.compress(raw,6);name=f'{width}-{tx}-{ty}.tile';(output/name).write_bytes(data)
                tiles[f'{tx},{ty}']=dict(file=name,width=w,height=h,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data))
        levels.append(dict(id=str(width),width=width,height=height,span=span,center=list(center),bbox=list(view.bbox),spacing_m=1000*span/(width-1),legend=legend,tiles=tiles))
    inputs=[SOURCES/name for name in ('n810-map-next.py','n810-walk-map.py','n810-map.py','n810-map-rgb.py')]+sorted(p for p in (SOURCES/'maps').iterdir() if p.is_file())
    sources=[dict(file=str(p.relative_to(SOURCES)),sha256=digest(p)) for p in inputs]
    palette=dict(version=PALETTE_VERSION,breakpoints=BREAKPOINTS,sha256=digest(TRIAL/'geographic_palette.py'))
    identity=hashlib.sha256(json.dumps(dict(sources=sources,palette=palette,center=center,span=span,widths=list(widths),terrain=True,roads=True),sort_keys=True).encode()).hexdigest()
    manifest=dict(version=1,style=PALETTE_VERSION,identity=identity,palette=palette,terrain=True,roads=True,levels=levels,
        projection=dict(crs=f'EPSG:4326 coordinates; local equirectangular sampling at reference latitude {center[0]}',cell_aspect=2,rounding='nearest source character cell, ties to even'),
        tile_width=32,tile_height=16,sources=sources,default_enabled=False,
        coverage_notice='Fine measured terrain only inside Lakewood DEM extent; elsewhere Puget DEM/coarse classes. Intermediate road filtering and nearest-cell resampling differ from direct rendering.',
        source_resolution_notice='Lakewood measured DEM grid about 9.85x14.49 m; Puget/Rainier measured DEM grid about 329x487 m. Output character spacing is not measured terrain resolution.',
        attribution='OpenStreetMap contributors ODbL; USGS 3DEP; regional overview Natural Earth / NOAA ETOPO1; terrain context, not navigation')
    tile_bytes=sum(v['bytes'] for level in levels for v in level['tiles'].values())
    if tile_bytes>4*1024*1024:raise ValueError('Pack exceeds compressed tile budget; no manifest published')
    text=json.dumps(manifest,indent=2)+'\n'
    if len(text.encode())>1024*1024:raise ValueError('Pack manifest exceeds budget')
    (output/'manifest.json').write_text(text)
    print(json.dumps(dict(identity=identity,tiles=sum(len(l['tiles']) for l in levels),tile_bytes=tile_bytes,manifest_bytes=len(text.encode()),levels=[dict(width=l['width'],bbox=l['bbox'],spacing_m=l['spacing_m']) for l in levels])))

if __name__=='__main__':main()
