# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Geometry, layer isolation and output invalidation for the opt-in engine."""
import importlib.util, unittest
from array import array
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).parent
s=importlib.util.spec_from_file_location('map_next_tests',ROOT/'n810-map-next.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class Screen:
    def __init__(self):self.calls=[]
    def addnstr(self,*args):self.calls.append(args)

class Tests(unittest.TestCase):
    def test_view_bounds_projection_and_scale(self):
        v=m.Viewport([47,-122],2,101,25)
        self.assertEqual(v.project(-122,47),(50,12));self.assertEqual(v.ground_m_per_halfcell,20)
        west,south,east,north=v.bounds()
        for lon,lat,expected in ((west,north,(0,0)),(east,south,(100,24))):
            x,y=v.project(lon,lat);self.assertAlmostEqual(x,expected[0]);self.assertAlmostEqual(y,expected[1])
        self.assertEqual(v,m.Viewport((47,-122),2,101,25));hash(v.key)
        with self.assertRaises(ValueError):m.Viewport((47,-122),0,101,25)
        with self.assertRaises(ValueError):m.Viewport((float('nan'),-122),2,101,25)
    def test_overlay_priority_clipping_and_restoration(self):
        o=m.Overlay(3,1);o.put(1,0,('@',9),20);o.put(1,0,('*',2),1)
        self.assertFalse(o.put(4,0,('x',0)));self.assertEqual(o[1,0],('@',9))
        frame=((' ',1),)*3;screen=Screen();surface=m.CellSurface()
        surface.draw(screen,frame,o,0,0,3,1);self.assertEqual(surface.previous[1],('@',9))
        screen.calls.clear();surface.draw(screen,frame,o,0,0,3,1);self.assertEqual(screen.calls,[])
        surface.draw(screen,frame,{},0,0,3,1);self.assertEqual(screen.calls,[(0,1,' ',1,1)])
        screen.calls.clear();surface.invalidate();surface.draw(screen,frame,{},0,0,3,1);self.assertEqual(len(screen.calls),1)
    def test_rgb_overlay_retains_terrain_background(self):
        self.assertEqual(m.composite((('▀',(1,2,3),(4,5,6)),),{(0,0):('@',(9,9,9))},1,1),[('@',(9,9,9),(4,5,6))])
    def test_engine_cache_excludes_overlays_and_layer_changes(self):
        e=m.Engine(ROOT/'maps','rgb');v=m.Viewport((5.5355,5.5655),2,80,20)
        a,_=e.prepare(v,True,True);self.assertEqual(e.stats['cache'],'cold')
        b,_=e.prepare(v,True,True);self.assertIs(a,b);self.assertEqual(e.stats['cache'],'ram')
        flat,_=e.prepare(v,False,True);self.assertIsNot(flat,a)
        e.prepare(v,True,False);self.assertEqual(e.stats['road_cells'],0);self.assertGreater(e.stats['stream_cells'],0)
        for span in range(1,12):e.prepare(m.Viewport(v.center,span,80,20))
        self.assertEqual(len(e.cache),8)
    def test_no_roads_background_matches_accepted_close_rgb_heights(self):
        e=m.Engine(ROOT/'maps','rgb');v=m.Viewport((5.5355,5.5655),1,100,23)
        frame,_=e._rgb_terrain(v,True)
        old,_=e.rgb.background(e.atlas,v.center,v.span,v.width,v.height,False,True)
        self.assertEqual([c[2] for c in frame],[c[2] for c in old])
        stream_cells,_=e.atlas.road_cells(v.center,v.span,v.width,v.height,streams=True)
        self.assertTrue(all(c==old[i] for i,c in enumerate(frame) if (i%v.width,i//v.width) not in stream_cells))
    def test_default_palette_matches_explicit_default_and_cached_frame(self):
        default=m.Engine(ROOT/'maps','rgb')
        explicit=m.Engine(ROOT/'maps','rgb',palette=default.rgb)
        self.assertIs(default.palette,default.rgb)
        for span,terrain in ((1,True),(24,True),(24,False)):
            view=m.Viewport((5.5355,5.5655),span,30,8)
            frame,legend=default.prepare(view,terrain,False)
            self.assertEqual(explicit.prepare(view,terrain,False),(frame,legend))
            cached,_=default.prepare(view,terrain,False)
            self.assertIs(cached,frame)
    def test_custom_background_palette_is_isolated_from_codec_features_and_other_engines(self):
        default=m.Engine(ROOT/'maps','rgb')
        view=m.Viewport((5.5355,5.5655),2,30,8)
        original,_=default.prepare(view,True,True)
        palette=SimpleNamespace(LOW=(1,2,3),HIGH=(4,5,6),LAND=(7,8,9),WATER=(10,11,12),
                                REGIONAL=tuple((i,i+1,i+2) for i in range(8)),
                                blend=default.rgb.blend,band_color=lambda height,low,high:(13,14,15))
        themed=m.Engine(ROOT/'maps','rgb',palette=palette)
        frame,_=themed.prepare(view,True,True)
        self.assertNotEqual(frame,original)
        flat,_=themed._rgb_terrain(view,False)
        self.assertTrue(all(c[1] in (palette.LAND,palette.WATER) and c[2] in (palette.LAND,palette.WATER) for c in flat))
        self.assertEqual(themed.stats['road_cells'],default.stats['road_cells'])
        self.assertEqual(themed.stats['stream_cells'],default.stats['stream_cells'])
        self.assertIsInstance(themed.surface,themed.rgb.Surface)
        self.assertIs(default.prepare(view,True,True)[0],original)
        with self.assertRaises(AttributeError):themed.palette=default.rgb
    def test_world_query_and_offline_coverage_are_bounded(self):
        e=m.Engine(ROOT/'maps','rgb');frame,_=e.prepare(m.Viewport((47,-122),48000,100,23))
        self.assertEqual(len(frame),2300);self.assertEqual(e.stats['candidates'],0)
        _,legend=e.prepare(m.Viewport((0,0),1,100,23));self.assertEqual(e.stats['unknown'],4600)
        self.assertIn('No offline elevation coverage',legend)
    def test_ansi_palette_is_explicit_and_does_not_auto_enable_rgb(self):
        seen=[]
        def attr(kind,terrain):seen.append((kind,terrain));return 17 if terrain else 3
        e=m.Engine(ROOT/'maps','ansi',attr);v=m.Viewport((5.5355,5.5655),2,30,10)
        frame,_=e.prepare(v,True,False);self.assertTrue(seen);self.assertTrue(all(len(c)==2 for c in frame))
        screen=Screen();e.draw({},win=screen);self.assertTrue(screen.calls)
    def test_new_terrain_does_not_call_legacy_viewport_renderer(self):
        e=m.Engine(ROOT/'maps','ansi',lambda kind,terrain:0)
        with patch.object(e.legacy,'background',side_effect=AssertionError('legacy raster must not render next view')):
            e.prepare(m.Viewport((5.5355,5.5655),8,100,23),True,False)
        self.assertTrue(e.stats['height_levels'])
    def test_filtered_heights_retain_lowland_variation(self):
        e=m.Engine(ROOT/'maps','rgb');view=m.Viewport((5.5355,5.5655),16,100,23)
        heights,shades,levels=e.terrain.sample(view)
        lowland={v for row in heights for v in row if 0<=v<200}
        self.assertGreater(len(lowland),20);self.assertTrue(levels)
        e.prepare(view,True,False);self.assertTrue(e.stats['height_levels'])
    def test_navigation_batches_stop_at_controls_and_restore_input_timeout(self):
        trial=m.load('trial_navigation_test','n810-map-trial.py')
        class Input:
            def __init__(self):self.keys=iter([ord('+'),ord('-'),ord('t'),ord('+')]);self.timeouts=[]
            def getch(self):return next(self.keys,-1)
            def timeout(self,n):self.timeouts.append(n)
        win=Input();self.assertEqual(trial.queued_keys(win,ord('+')),[ord('+'),ord('+'),ord('-'),ord('t')])
        self.assertEqual(win.getch(),ord('+'));self.assertEqual(win.timeouts,[0,250])
    def test_wide_filtered_height_and_coarse_class_share_color_anchors(self):
        e=m.Engine(ROOT/'maps','rgb')
        for kind,height in enumerate((0,200,500,1000,1800,2800),1):
            self.assertEqual(m.wide_color(e.rgb,height),e.rgb.REGIONAL[kind])
        self.assertNotEqual(m.wide_color(e.rgb,50),m.wide_color(e.rgb,150))
    def test_ansi_overlay_transparency_selection_and_backplates(self):
        import curses
        cells={(0,0):('*',0),(1,0):('@',1)}
        with patch.object(curses,'pair_number',side_effect=lambda a:a),patch.object(curses,'pair_content',side_effect=lambda n:(0,11) if n else (2,0)):
            result=m.ansi_overlays(cells)
            self.assertEqual(len(result[0,0]),2);self.assertEqual(result[1,0][2],m.ANSI_RGB[11])
            result=m.ansi_overlays(cells,backplate=(14,21,18))
            self.assertEqual(result[0,0][2],(14,21,18))
    def test_ansi_coarse_fallback_uses_same_subdued_family_as_filtered(self):
        kinds=[]
        e=m.Engine(ROOT/'maps','ansi',lambda kind,terrain:kinds.append(kind) or 0)
        e.prepare(m.Viewport((5.5355,5.5655),640,100,23),True,False)
        self.assertTrue(any(k.startswith('relief') for k in kinds))
        self.assertFalse(any(k.startswith('tone') and k!='tone00' for k in kinds))
    def test_multiple_vector_segments_keep_projection_scale(self):
        e=m.Engine(ROOT/'maps','rgb');view=m.Viewport((5.5555,5.5555),2,101,23)
        segments=[(555050,555250,556050,555250),(555050,555850,556050,555850)]
        layer=dict(tile=100000,coords=array('i',[n for segment in segments for n in segment]),index={(-123,47):(0,1)})
        e.atlas.roads=[layer];e.layer_bounds[id(layer)]=(555050,555250,556050,555850)
        cells,_=e._lines(view)
        expected={round(view.project(a/100000,b/100000)[1]) for a,b,_,_ in segments}
        self.assertEqual({y for x,y in cells},expected)
    def test_tinted_panel_preserves_halfcell_shapes_and_background(self):
        e=m.Engine(ROOT/'maps','rgb');e.view=m.Viewport((47,-122),1,2,1)
        original=(('▀',(120,160,80),(40,80,30)),(' ',(80,90,70),(80,90,70)))
        e.frame=original
        panel=e.panel((-1,0,2,1),tint=(0,0,0),opacity=.5)
        self.assertEqual(panel,{(0,0):('▀',(60,80,40),(20,40,15))});self.assertIs(e.frame,original)
        self.assertEqual(e.panel((0,0,1,1),opacity=0)[0,0],original[0])
        underlay={(0,0):('@',(200,200,200),(100,100,100))}
        self.assertEqual(e.panel((0,0,1,1),tint=(0,0,0),opacity=.5,underlay=underlay)[0,0],('@',(100,100,100),(50,50,50)))
    def test_canonical_places_prefer_fine_source_without_merging_distinct_places(self):
        def pack(name,width,labels):return dict(name=name,bbox=(-124,46,-120,49),raster=dict(width=width,height=width),labels=labels)
        city=dict(name='Seattle',kind='city',lat=47.6038321,lon=-122.330062)
        coarse=dict(city,name='  SEATTLE ',lat=47.600423,lon=-122.315322)
        far=dict(city,lat=48.8);peak=dict(city,kind='peak')
        labels=m.canonical_places([pack('coarse',100,[coarse,far,peak]),pack('fine',1000,[city])])
        close=[p for p in labels if p['kind']=='city' and p['lat']<48]
        self.assertEqual(len(close),1);self.assertEqual(close[0]['lon'],city['lon']);self.assertEqual(close[0]['sources'],('fine','coarse'))
        self.assertEqual(len(labels),3)
    def test_actual_unified_model_has_one_seattle(self):
        e=m.Engine(ROOT/'maps','rgb')
        labels=[p for p in e.places() if p['name'].casefold()=='seattle' and p['kind']=='city']
        self.assertEqual(len(labels),1);self.assertAlmostEqual(labels[0]['lon'],-122.330062)
        self.assertGreaterEqual(len(labels[0]['sources']),2)
        view=m.Viewport((47.6,-122.33),30,100,23);self.assertIn(labels[0],e.places(view))
    def test_authority_ids_aliases_and_conflicting_identifiers(self):
        def pack(name,width,labels):return dict(name=name,bbox=(-124,46,-120,49),raster=dict(width=width,height=width),labels=labels)
        a=dict(name='Harbor City',kind='city',lat=47,lon=-122,wikidata='Q123')
        b=dict(name='Harbour',aliases=['Harbor City'],kind='Town',lat=47.01,lon=-122.01,wikidata='https://www.wikidata.org/entity/q123')
        other=dict(a,wikidata='Q456',lat=47.0001)
        labels=m.canonical_places([pack('coarse',100,[b]),pack('fine',1000,[a,other])])
        self.assertEqual(len(labels),2)
        original=next(p for p in labels if ('wikidata','Q123') in p['identifiers'])
        self.assertEqual(original['name'],'Harbor City');self.assertEqual(original['sources'],('fine','coarse'))
        self.assertIn('harbour',original['aliases'])
    def test_fine_scale_same_name_places_are_not_merged_by_coarse_radius(self):
        a=dict(name='Smallville',kind='town',lat=47,lon=-122)
        b=dict(a,lat=47.01)
        pack=dict(name='fine',bbox=(-122.1,46.9,-121.9,47.1),raster=dict(width=1000,height=1000),labels=[a,b])
        self.assertEqual(len(m.canonical_places([pack])),2)
    def test_all_actual_overlapping_source_places_reconcile_and_distant_names_remain(self):
        e=m.Engine(ROOT/'maps','rgb')
        for name in ('Seattle','Tacoma','Everett','Bremerton','Olympia'):
            places=[p for p in e.places() if p['name']==name and p['kind']=='city']
            self.assertEqual(len(places),1,name);self.assertGreaterEqual(len(places[0]['sources']),2)
        self.assertEqual(len([p for p in e.places() if p['name']=='Vancouver']),2)
        identity=[(p['name'],p['lat'],p['lon']) for p in e.places()]
        e.prepare(m.Viewport((47.2,-122.4),2,100,23))
        self.assertEqual(identity,[(p['name'],p['lat'],p['lon']) for p in e.places()])

if __name__=='__main__':unittest.main()
