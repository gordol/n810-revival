"""Offline acquisition reuse, conservative display LOD, and shared reader contracts."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'));sys.path.insert(0,str(ROOT/'shell'))
import elevation_pipeline as pipeline
from elevation_pyramid import build,read_grid
from prepare_elevation_tiles import prepare
import local_elevation


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.data=self.root/'data';self.downloads=self.data/'downloads/usgs'
        self.addCleanup(self.reset_catalogue)

    @staticmethod
    def reset_catalogue():
        local_elevation._checked=0;local_elevation._signature=();local_elevation._catalogue=();local_elevation._buckets={}
        local_elevation.tile.cache_clear();local_elevation.read_index.cache_clear()

    def raw(self,folder=None,bbox=(1,1,1.0064,1.0064)):
        import numpy as np
        from PIL import Image
        folder=folder or self.downloads/'prior-request'
        folder.mkdir(parents=True,exist_ok=True)
        values=np.full((64,64),100,dtype=np.float32);values[31,32]=3000
        Image.fromarray(values).save(folder/'raw.tif')
        export=dict(width=64,height=64,extent=dict(zip(('xmin','ymin','xmax','ymax'),bbox),spatialReference={'wkid':4326}))
        record=dict(request_url='https://example.invalid/fixture',response=export)
        (folder/'export.json').write_text(json.dumps(record))
        return folder,export

    def pack(self,bbox=(1,1,1.0064,1.0064),name='fixture-guarded'):
        folder,export=self.raw(bbox=bbox)
        target=self.data/'elevation-fine'/name
        prepare(folder/'raw.tif',folder/'export.json',target)
        return target/'index.json'

    def test_cached_fine_data_builds_overviews_once_without_network_or_copies(self):
        index=self.pack()
        bbox=(1,1,1.0064,1.0064)
        with patch('urllib.request.urlopen',side_effect=AssertionError('Unexpected download')):
            first=pipeline.run(bbox,self.data,self.downloads,offline=True)
            stamps={p:p.stat().st_mtime_ns for p in self.data.rglob('*') if p.is_file()}
            second=pipeline.run(bbox,self.data,self.downloads,offline=True)
        self.assertEqual(first['downloads'],0);self.assertEqual(first['overview_rebuilds'],1)
        self.assertEqual(second['overview_rebuilds'],0)
        self.assertEqual(stamps,{p:p.stat().st_mtime_ns for p in self.data.rglob('*') if p.is_file()})
        self.assertFalse((self.data/'elevation-lakewood').exists())
        self.assertFalse(list(self.data.rglob('terrain-next.n8t')))
        self.assertEqual(json.loads((self.data/'elevation.json').read_text())['packs'],['elevation-fine/fixture-guarded/index.json'])

    def test_existing_raw_export_is_reused_for_a_smaller_area_without_downloading(self):
        self.raw()
        with patch('urllib.request.urlopen',side_effect=AssertionError('Unexpected download')):
            report=pipeline.run((1.001,1.001,1.005,1.005),self.data,self.downloads,offline=True)
        self.assertEqual(report['downloads'],0);self.assertEqual(report['cached_raw_exports'],1)
        self.assertEqual(report['packs'],1)

    def test_one_network_export_serves_fine_and_all_display_levels_then_resumes_offline(self):
        import io
        folder,response=self.raw(self.root/'upstream')
        image=(folder/'raw.tif').read_bytes();response['href']='https://example.invalid/raw.tif'
        bbox=(1,1,1.0064,1.0064)
        request=pipeline.plan(bbox,self.data)['requests'][0]
        # The fake server returns the requested raster dimensions and extent.
        from PIL import Image
        import numpy as np
        stream=io.BytesIO();Image.fromarray(np.full((request['height'],request['width']),123,dtype=np.float32)).save(stream,format='TIFF')
        response.update(width=request['width'],height=request['height'])
        responses=[io.BytesIO(json.dumps(response).encode()),io.BytesIO(stream.getvalue())]
        with patch('urllib.request.urlopen',side_effect=responses) as opened:
            first=pipeline.run(bbox,self.data,self.downloads)
        self.assertEqual(opened.call_count,2)  # Metadata + one fine raster, no coarse request.
        self.assertEqual(first['downloads'],1)
        with patch('urllib.request.urlopen',side_effect=AssertionError('Duplicate download')):
            second=pipeline.run(bbox,self.data,self.downloads,offline=True)
        self.assertEqual(second['downloads'],0);self.assertEqual(second['overview_rebuilds'],0)

    def test_reference_package_contains_only_selected_packs_and_no_raw_or_coarse_copy(self):
        import importlib.util,tarfile
        index=self.pack();build(index)
        (self.data/'elevation.json').write_text(json.dumps(dict(version=1,packs=[str(index.relative_to(self.data))])))
        other=self.data/'elevation-fine/unselected-guarded/unused.i16.zlib';other.parent.mkdir();other.write_bytes(b'not selected')
        for name in ('geography/index.json','hydrography/index.json','repeaters/repeaters.json','uls.sqlite'):
            path=self.data/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')
        old=self.root/'shell/data/elevation-lakewood/old.i16.zlib';old.parent.mkdir(parents=True);old.write_bytes(b'legacy')
        (self.root/'VERSION').write_text('0.1.0')
        spec=importlib.util.spec_from_file_location('selected_reference_package',ROOT/'tools/package_reference_data.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with patch.object(module,'ROOT',self.root):module.package(self.root/'reference.tar.gz')
        with tarfile.open(self.root/'reference.tar.gz') as archive:names=archive.getnames()
        self.assertIn('data/elevation.json',names)
        self.assertTrue(any('/overviews/' in name for name in names))
        self.assertFalse(any('unselected' in name or 'lakewood' in name or 'raw.tif' in name for name in names))

    def test_adjacent_cached_packs_cover_an_area_without_overlapping_exports(self):
        self.pack(name='left-guarded')
        self.pack(bbox=(1.0064,1,1.0128,1.0064),name='right-guarded')
        result=pipeline.plan((1.001,1.001,1.012,1.005),self.data)
        self.assertEqual(len(result['cached']),2);self.assertEqual(result['requests'],[])

    def test_missing_area_has_bounded_requests_and_offline_derivation_does_not_fetch(self):
        bbox=(1,1,2,2)
        result=pipeline.plan(bbox,self.data)
        self.assertGreater(len(result['requests']),1)
        for request in result['requests']:
            self.assertLessEqual(request['width'],4096);self.assertLessEqual(request['height'],4096)
            self.assertGreaterEqual(request['width'],2);self.assertGreaterEqual(request['height'],2)
        with patch('urllib.request.urlopen',side_effect=AssertionError('Unexpected download')):
            with self.assertRaisesRegex(ValueError,'Missing fine elevation'):pipeline.run(bbox,self.data,self.downloads,offline=True)
        self.assertFalse(self.data.exists())

    def test_display_overview_never_replaces_fine_analysis_heights(self):
        import numpy as np
        import desktop_elevation,elevation_display
        index=self.pack();build(index)
        m=json.loads(index.read_text());level=index.parent/m['overviews'][0]['index'];overview=json.loads(level.read_text())
        values=read_grid(level,overview)
        self.assertLess(int(values.max()),3000)
        (self.data/'elevation.json').write_text(json.dumps(dict(version=1,packs=[str(index.relative_to(self.data))])))
        with patch('local_elevation.data_root',return_value=self.data),patch('data_paths.data_root',return_value=self.data):
            self.assertEqual(local_elevation.sources(),[index])
            self.assertEqual(local_elevation.display_sources(100),[level,index])
            lat=m['latitude_first']+32*m['latitude_step'];lon=m['longitude_first']+32*m['longitude_step']
            height,_=local_elevation.sample(lat,lon)
            self.assertAlmostEqual(height,3000,places=5)
            view=SimpleNamespace(center=(lat,lon),span=0,width=1,height=1,cell_aspect=2)
            scalar=elevation_display.sample(view)
            vector,_=desktop_elevation.sample(view)
            self.assertAlmostEqual(scalar[0][0],float(vector[0,0]),places=5)
            self.assertAlmostEqual(float(vector[0,0]),3000,places=5)

    def test_portable_renderer_reads_catalogue_without_numpy_or_terminal_terrain_pack(self):
        import builtins
        import elevation_display
        index=self.pack();build(index)
        (self.data/'elevation.json').write_text(json.dumps(dict(version=1,packs=[str(index.relative_to(self.data))])))
        calls=[]
        palette=SimpleNamespace(band_color=lambda *args:(20,100,30))
        engine=SimpleNamespace(cache={},prepared=None,palette=palette,
            _rgb_terrain=lambda view,terrain:(calls.append(terrain) or [(' ',(1,2,3),(1,2,3))]*(view.width*view.height),'flat'),
            atlas=SimpleNamespace(raster=lambda center,span,w,h:([[1]*w for _ in range(h*2)],None,{})))
        original=builtins.__import__
        def portable(name,*args,**kwargs):
            if name.split('.')[0] in ('numpy','PIL','osgeo'):raise AssertionError('Portable display imported '+name)
            return original(name,*args,**kwargs)
        view=SimpleNamespace(center=(1.0032,1.0032),span=.3,width=10,height=4,cell_aspect=2)
        with patch('local_elevation.data_root',return_value=self.data),patch('data_paths.data_root',return_value=self.data),patch('builtins.__import__',side_effect=portable):
            elevation_display.configure(engine)
            cells,legend=engine._rgb_terrain(view,True)
        self.assertEqual(calls,[False])
        self.assertEqual(len(cells),40)
        self.assertIn('local overviews',legend)
        self.assertTrue(any(cell[1]==(20,100,30) for cell in cells))

    def test_3d_geometry_uses_the_same_catalogue_without_a_legacy_terrain_pack(self):
        from offline_map import Renderer
        index=self.pack();build(index)
        (self.data/'elevation.json').write_text(json.dumps(dict(version=1,packs=[str(index.relative_to(self.data))])))
        renderer=Renderer();self.addCleanup(renderer.close)
        renderer.module=SimpleNamespace(Viewport=lambda center,span,width,height:SimpleNamespace(center=center,span=span,width=width,height=height,cell_aspect=2))
        renderer.engine=SimpleNamespace(atlas=SimpleNamespace(raster=lambda center,span,w,h:([[1]*w for _ in range(h*2)],[[255]*w for _ in range(h*2)],{})))
        models=[]
        def render(model,width,height,**kwargs):
            models.append(model);return {(x,y):(' ',0) for y in range(height) for x in range(width)},{}
        with patch('local_elevation.data_root',return_value=self.data),patch('data_paths.data_root',return_value=self.data),patch('geometry.render',side_effect=render):
            image=renderer._render3d(((1.0032,1.0032),.5,10,5,8,4,0,.75,1,1))
        self.assertEqual(len(image.cells),32)
        self.assertTrue(models[0].mesh.triangles)
        self.assertGreater(max(models[0].terrain.values),99)

    def test_revision_does_not_construct_the_analysis_catalogue_for_display(self):
        index=self.pack()
        (self.data/'elevation.json').write_text(json.dumps(dict(version=1,packs=[str(index.relative_to(self.data))])))
        with patch('local_elevation.data_root',return_value=self.data),patch('local_elevation.catalogue',side_effect=AssertionError('Display loaded analysis grids')):
            self.assertTrue(local_elevation.revision())

    def test_display_tile_edges_do_not_create_seams_or_change_analysis_coverage(self):
        import desktop_elevation,elevation_display
        index=self.pack()
        (self.data/'elevation.json').write_text(json.dumps(dict(version=1,packs=[str(index.relative_to(self.data))])))
        view=SimpleNamespace(center=(1.0032,1.0064),span=0,width=1,height=1,cell_aspect=2)
        with patch('local_elevation.data_root',return_value=self.data),patch('data_paths.data_root',return_value=self.data):
            local_elevation.catalogue(force=True)
            self.assertIsNone(local_elevation.sample(*view.center)[0])
            self.assertEqual(elevation_display.sample(view)[0][0],100)
            self.assertEqual(float(desktop_elevation.sample(view)[0][0,0]),100)

    def test_nodata_does_not_become_known_when_reduced(self):
        index=self.pack();m=json.loads(index.read_text());item=m['tiles']['0,0']
        import numpy as np
        values=read_grid(index,m);values[10,10]=m['nodata']
        raw=zlib.compress(values.astype('<i2').tobytes());(index.parent/item['file']).write_bytes(raw)
        item['sha256']=hashlib.sha256(raw).hexdigest();item['bytes']=len(raw)
        index.write_text(json.dumps(m));build(index)
        m=json.loads(index.read_text());level=index.parent/m['overviews'][0]['index'];lm=json.loads(level.read_text())
        self.assertEqual(int(read_grid(level,lm)[5,5]),m['nodata'])

    def test_partial_cache_requests_only_uncovered_rectangle(self):
        self.pack()
        result=pipeline.plan((1,1,1.0128,1.0064),self.data)
        self.assertTrue(result['requests'])
        self.assertTrue(all(r['bbox'][0]>=1.0064-1e-9 for r in result['requests']))

    def test_area_required_and_invalid_bounds_rejected(self):
        for bbox in ((2,1,1,2),(0,0,float('nan'),1),(0,-90,1,0)):
            with self.assertRaises(ValueError):pipeline.plan(bbox,self.data)
        with self.assertRaises(SystemExit):pipeline.main(['--output',str(self.data),'--plan'])

if __name__=='__main__':unittest.main()
