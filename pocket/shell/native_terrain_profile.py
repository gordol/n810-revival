"""Terrain path graph over the existing offline USGS DEM, with explicit endpoint inputs."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event,Lock
from app_widgets import Canvas,TextInput
from terrain_elevation import calculate


class TerrainProfile:
    def __init__(self,maps=None,map_base=None,qth_path=None):
        self.width=90;self.height=30
        self.fields=[TextInput('',limit=48),TextInput('',limit=48),TextInput('144.39',limit=12),TextInput('2',limit=8),TextInput('10',limit=8)]
        self.field=0;self.result=None;self.error='';self.status='Choose two geographic endpoints'
        self.pool=None;self.pending=None;self.closed=False;self.wakeup=None;self._spans=();self._session_callback=None
        from terrain_point_map import PointMap
        self._progress_lock=Lock();self._progress_snapshot=None
        self.job='profile';self.sites=None;self.site_index=0;self.cancelled=Event();self._queued_profile=False
        self.screen='map';self.map=PointMap(self.set_endpoint,self.show_profile,maps,base=map_base)
        self.map.nearby=self.nearby;self.map.show_los=self.show_los;self.map.change_band=self.open_bands;self.map.change_radius=self.cycle_radius
        self.radius_km=5;self.band_index=next(i for i,(_,value) in enumerate(self.bands) if value=='144.39');self._band_offset=0;self._queued_los=False;self._los_enabled=False;self._coverage_view=None;self._retained_coverage=None;self._queued_refine=False;self.map.open_heights=self.open_heights
        self.map.toggle_mode=self.toggle_mode;self.map.clear=self.clear_selection;self.map.toggle_clearance=self.toggle_clearance
        from terrain_qth import QTH
        self.qth_store=QTH(qth_path) if qth_path else None;self.qth=None
        if self.qth_store:
            try:self.qth=self.qth_store.read()
            except (OSError,ValueError):pass
        self.map.qth=(self.qth['latitude'],self.qth['longitude']) if self.qth else None
        self.map.inspect_point=None;self.selected_sample=None;self.profile_zoom=None;self.target_label='';self.resolve_station=None;self._inspect_after_calculation=False
        self.map.inspect_obstruction=self.show_obstruction
        self.call_input=TextInput('',limit=16);self.map.open_call=self.open_call;self.map.go_qth=self.go_qth;self.map.fit_path=self.fit_path
        if self.qth:
            self.set_endpoint(self.map.qth,end=False);self.fields[3]=TextInput(f"{self.qth['height_m']:g}",limit=8)
    def terrain_available(self):
        provider=getattr(self,'enabled_provider',None)
        enabled=not callable(provider) or bool(provider())
        if not enabled:
            self._queued_los=False;self._queued_profile=False;self._los_enabled=False
            self.cancelled.set();self.map.coverage=None;self.map.inspect_point=None;self.result=None
            if self.pending and self.pending.done():
                try:self.pending.result()
                except Exception:pass
                self.pending=None
            self.screen='disabled'
        elif self.screen=='disabled':self.screen='map'
        return enabled
    def go_qth(self):
        if not self.qth:self.map.notice='No saved QTH; select a point and use Save as QTH';return True
        self.map.center=self.map.qth;self.map.span=1.;self.map.base.target_box.cancel();self.map.base.full_overview=False
        return True
    def save_qth(self,position=None):
        position=position or self.map.points[0]
        if not position:self.error='Select a location first';return False
        height=float(self.fields[3].text)
        if self.qth_store:self.qth_store.save(*position,height_m=height)
        self.qth=dict(latitude=position[0],longitude=position[1],height_m=height)
        self.map.qth=tuple(position);self.map.notice='QTH saved independently of path endpoints'
        return True
    def return_to_map(self):
        self.screen='map'
        if self.result:self.map.inspect_point=self.result.get('bottleneck')
        self.fit_path()
        return True
    def fit_path(self):
        import math
        if not all(self.map.points):return False
        a,b=self.map.points;center=((a[0]+b[0])/2,(a[1]+b[1])/2)
        horizontal=abs(a[1]-b[1])*111.32*math.cos(math.radians(center[0]))
        vertical=abs(a[0]-b[0])*111.32*max(1,(self.width-1)/max(1,2*(self.height-3)))
        self.map.center=center;self.map.span=max(.01,1.15*max(horizontal,vertical))
        self.map.base.target_box.cancel();self.map.base.full_overview=False
        return True
    def sync_qth_height(self):
        if not self.qth or not self.map.points[0]:return
        lat,lon=self.map.points[0]
        if abs(lat-self.qth['latitude'])+abs(lon-self.qth['longitude'])>1e-5:return
        try:height=float(self.fields[3].text)
        except ValueError:return
        if 0<=height<=10000 and height!=self.qth['height_m']:
            self.qth['height_m']=height
            if self.qth_store:self.qth_store.save(self.qth['latitude'],self.qth['longitude'],height_m=height,source=self.qth.get('source','User QTH'))
    def open_call(self):self.call_input=TextInput('',limit=16);self.screen='call-target'
    def profile_to_location(self,call,position):
        if not self.terrain_available():return False
        if not self.qth:self.error='Set your QTH first';self.map.notice=self.error;return False
        self.set_endpoint((self.qth['latitude'],self.qth['longitude']),end=False)
        self.fields[3]=TextInput(f"{self.qth['height_m']:g}",limit=8)
        self.set_endpoint(position,end=True);self.target_label=call;self.map.mode='path';self.profile_zoom=None
        self.screen='profile';return self.calculate()
    def lookup_call(self):
        try:
            if not self.resolve_station:raise ValueError('Station directory unavailable')
            call=self.call_input.text.strip().upper();position=self.resolve_station(call)
            if not position:raise ValueError('No observed position for '+call)
            return self.profile_to_location(call,position)
        except (ValueError,OSError) as error:self.error=str(error);return True
    def show_obstruction(self):
        if self.result:return self.inspect_bottleneck(on_map=True)
        if not all(self.map.points):self.map.notice='Select both endpoints first';return True
        self._inspect_after_calculation=True;self.map.notice='Calculating limiting sample…'
        return self.calculate()
    def inspect_bottleneck(self,on_map=False):
        if not self.result:return False
        point=self.result['bottleneck'] if on_map else self.selected_sample or self.result['bottleneck'];distance=point['distance_m'];self.map.inspect_point=self.result['bottleneck']
        if on_map:
            self.screen='map'
            self.map.notice=f"X: limiting sample {distance:.1f} m from start · F60 margin {point['fresnel_clearance_m']:+.2f} m"
        else:self.profile_zoom=(max(0,distance-250),min(self.result['distance_m'],distance+250))
        return True
    def toggle_mode(self):
        self.map.mode='area' if self.map.mode=='path' else 'path'
        self.map.coverage=None;self.map.candidates=[]
        self.map.cancel_pointer()
        self.map.notice='Tap your house; H sets roof height; L shows radius LOS' if self.map.mode=='area' else 'Select From, then To'
        if self._session_callback:self._session_callback()
    def clear_selection(self,clear_all=False):
        self._queued_los=False;self._queued_profile=False;self._los_enabled=False
        self._inspect_after_calculation=False;self.map.inspect_point=None;self.selected_sample=None
        if self.pending:self.cancelled.set()
        if self.map.mode=='area' and not clear_all:self.map.points[0]=None;self.fields[0]=TextInput('',limit=48)
        else:
            self.map.points=[None,None];self.fields[0]=TextInput('',limit=48);self.fields[1]=TextInput('',limit=48);self.map.end=False
        self.result=None;self.sites=None;self.map.coverage=None;self.map.candidates=[]
        self.map.notice='Selection cleared'
        if self._session_callback:self._session_callback()
    def reset_double_tap(self):self.map.base.reset_double_tap()
    def interaction_deactivated(self):self.map.cancel_pointer()
    def bind_wakeup(self,callback):
        self.wakeup=callback;self.map.bind_wakeup(callback)
    def show_profile(self):
        if self.map.mode=='area':self.open_heights();return
        self.screen='profile'
        if all(field.text for field in self.fields[:2]):self.calculate()
    @property
    def pointer_captured(self):return self.screen=='map' and self.map.pointer_captured
    def cancel_pointer(self):self.map.cancel_pointer()
    def layer(self):return self.map.layer() if self.screen=='map' else None
    def modal(self):return True
    def navigation_modal_hint(self):
        if self.screen=='map':return ('Terrain map',self.map.notice+' · C clear · O overview · V direct/preview')
        return ('Terrain Profile','I inspect · X map sample · Z first km · A full path · M map')
    def bind_session(self,callback):self._session_callback=callback
    def session_state(self):return dict(fields=[field.text for field in self.fields],radius_km=self.radius_km,center=list(self.map.center),span=self.map.span,mode=self.map.mode,coverage_mode=self.map.coverage_mode,origin_label=self.map.origin_label)
    def restore_session(self,state):
        values=state.get('fields') if isinstance(state,dict) else None
        if isinstance(state,dict) and isinstance(state.get('origin_label'),str):self.map.origin_label=state['origin_label'][:48]
        if isinstance(values,list) and len(values)==5 and all(isinstance(v,str) and len(v)<=48 for v in values):
            self.fields=[TextInput(v,limit=48) for v in values]
            from terrain_elevation import coordinate
            for i in range(2):
                try:self.map.points[i]=coordinate(values[i])
                except ValueError:pass
            if state.get('mode') in ('path','area'):self.map.mode=state['mode']
            if state.get('coverage_mode') in ('los','fresnel'):self.map.coverage_mode=state['coverage_mode']
            radius=state.get('radius_km',5)
            if radius in (1,2,5,10,20,50,100):self.radius_km=radius;self.map.radius_km=radius
            self.map.band_label=self.fields[2].text+' MHz'
            if self.map.owns_base:
                camera=state.get('center');span=state.get('span')
                if isinstance(camera,list) and len(camera)==2:
                    try:self.map.center=coordinate(f'{camera[0]},{camera[1]}')
                    except ValueError:pass
                if type(span) in (int,float) and .01<=span<=2000:self.map.span=span
    def set_endpoint(self,position,end=True):
        if isinstance(position,(list,tuple)) and len(position)==2:
            self.map.inspect_point=None;self.selected_sample=None;self.profile_zoom=None;self.result=None
            self.fields[1 if end else 0]=TextInput(f'{position[0]:.6f},{position[1]:.6f}',limit=48)
            self.map.points[1 if end else 0]=tuple(position)
            self.map.coverage=None
            if self.pending and self.job in ('coverage','sites'):self.cancelled.set()
            self.status='Observer selected' if not end else 'Target selected'
            if self._session_callback:self._session_callback()
    # Representative calculation frequencies; not a transmit-privilege table.
    bands=(('2200 m · LF','0.136'),('630 m · MF','0.475'),('160 m · HF','1.9'),('80 m · HF','3.7'),('60 m · HF','5.357'),
           ('40 m · HF','7.1'),('30 m · HF','10.125'),('20 m · HF','14.2'),
           ('17 m · HF','18.1'),('15 m · HF','21.2'),('12 m · HF','24.94'),('10 m · HF','28.4'),
           ('6 m · VHF','50.125'),('4 m · VHF','70.2'),('2 m · VHF 144 MHz','144.39'),('1.25 m · VHF 220 MHz','223.5'),
           ('70 cm · UHF','440'),('33 cm · 900 MHz','915'),('23 cm · 1.2 GHz','1296'),
           ('13 cm · 2.4 GHz','2400'),('5 cm · 5.8 GHz','5760'),('3 cm · 10 GHz','10368'))
    def toggle_clearance(self):
        self.map.coverage_mode='fresnel' if self.map.coverage_mode=='los' else 'los'
        self.map.notice=f"{'60% first Fresnel clearance' if self.map.coverage_mode=='fresnel' else 'Ground LOS'} · {self.fields[2].text} MHz · red means clear"
        if self._session_callback:self._session_callback()
    def open_heights(self):self.screen='house-settings' if self.map.mode=='area' else 'profile';self.field=3
    def open_bands(self):
        self.band_index=next((i for i,(_,value) in enumerate(self.bands) if value==self.fields[2].text),self.band_index)
        self.screen='bands'
    def cycle_radius(self):
        radii=(1,2,5,10,20,50,100);self.radius_km=radii[(radii.index(self.radius_km)+1)%len(radii)]
        self.map.radius_km=self.radius_km;self.map.coverage=None
        self.map.notice=f'Radius {self.radius_km:g} km selected · L calculates LOS'
        if self._session_callback:self._session_callback()
        if self.pending and self.job=='coverage':self.cancelled.set()
        if self._los_enabled:self.show_los()
    def select_band(self,index):
        self.band_index=index;label,value=self.bands[index];self.fields[2]=TextInput(value,limit=12)
        self.map.band_label=value+' MHz';self.map.coverage=None;self.screen='map'
        self.map.notice=f'{label} · {value} MHz selected · L recalculates'
        if self._session_callback:self._session_callback()
        if self.pending and self.job=='coverage':self.cancelled.set()
        if self._los_enabled:self.show_los()
    def publish_coverage(self,snapshot):
        if self.closed or self.cancelled.is_set():return
        with self._progress_lock:self._progress_snapshot=snapshot
        if self.wakeup:self.wakeup()
    def coverage_view(self):
        from desktop_elevation import enabled
        if not enabled():return None
        width=max(12,min(96,self.width));height=max(6,min(64,round((self.height-3)*width/max(1,self.width))))
        return (tuple(self.map.center),self.map.span,width,height)
    def show_los(self,refine=False):
        if not self.terrain_available():return False
        if self.closed:return False
        if self.pending:
            self._queued_los=True;self._queued_refine=refine;self.cancelled.set()
            self.map.notice=f'Queued LOS update · {self.radius_km:g} km radius'
            return True
        self._queued_los=False
        try:
            from terrain_elevation import coordinate
            coordinate(self.fields[0].text)
            frequency,tx,rx=map(float,(f.text for f in self.fields[2:]))
        except ValueError:self.map.notice='Select From and set antenna heights in Profile first';return True
        from terrain_worker import coverage
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='terrain-profile')
        self._los_enabled=True;self.sync_qth_height()
        self._coverage_view=self.coverage_view()
        self._retained_coverage=self.map.coverage if refine else None
        with self._progress_lock:self._progress_snapshot=None
        self.job='coverage';self.screen='map';self.error='';self.cancelled.clear()
        self.map.notice=f'Calculating LOS · {self.radius_km:g} km radius…';self.map.coverage=self._retained_coverage
        self.pending=self.pool.submit(coverage,self.fields[0].text,radius_km=self.radius_km,
            frequency_mhz=frequency,tx_height_m=tx,rx_height_m=rx,cancelled=self.cancelled.is_set,
            grid_steps=max(6,min(24,min(self.width,(self.height-3)*2)//8)),progress=self.publish_coverage,
            viewport=self._coverage_view,refine_only=refine)
        callback=self.wakeup
        if callback:self.pending.add_done_callback(lambda future:callback() if not self.closed else None)
        return True
    def nearby(self):
        if not self.terrain_available():return False
        if self.closed or self.pending:return False
        try:frequency,tx,rx=map(float,(f.text for f in self.fields[2:]))
        except ValueError:self.error='Frequency and antenna heights must be numbers';return True
        from terrain_sites import search
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='terrain-profile')
        self.job='sites';self.screen='sites';self.error='';self.sites=None;self.site_index=0
        self.status=f'Searching within {self.radius_km:g} km of From toward To…';self.cancelled.clear()
        self.pending=self.pool.submit(search,self.fields[0].text,self.fields[1].text,radius_km=self.radius_km,
            frequency_mhz=frequency,tx_height_m=tx,rx_height_m=rx,cancelled=self.cancelled.is_set)
        callback=self.wakeup
        if callback:self.pending.add_done_callback(lambda future:callback() if not self.closed else None)
        return True
    def choose_site(self):
        if not self.sites:return False
        candidate=self.sites['candidates'][self.site_index]
        self.set_endpoint(candidate['position'],end=False);self.result=candidate['profile'];self.screen='profile'
        self.status='Candidate selected · terrain screening only; access and vegetation unverified'
        return True
    def calculate(self):
        if not self.terrain_available():return False
        if self.closed:return False
        if self.pending:
            self._queued_profile=True;self._queued_los=False;self.cancelled.set();return True
        try:frequency,tx,rx=map(float,(f.text for f in self.fields[2:]))
        except ValueError:self.error='Frequency and antenna heights must be numbers';return True
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='terrain-profile')
        self.sync_qth_height()
        self.job='profile';self.result=None;self.error='';self.status='Sampling installed USGS elevation data…'
        self.pending=self.pool.submit(calculate,self.fields[0].text,self.fields[1].text,frequency_mhz=frequency,tx_height_m=tx,rx_height_m=rx,count=4097)
        callback=self.wakeup
        if callback:self.pending.add_done_callback(lambda future:callback() if not self.closed else None)
        if self._session_callback:self._session_callback()
        return True
    def poll_interval(self):
        interval=self.map.base.poll_interval()
        return min(.05,interval) if self.pending and interval is not None else .05 if self.pending else interval
    def merge_coverage(self,value):
        if not value or not self._retained_coverage:return value
        old=self._retained_coverage
        known={tuple(cell['position']):cell for cell in old['cells']}
        known.update((tuple(cell['position']),cell) for cell in value['cells'])
        return dict(value,cells=list(known.values())[-24000:])
    def poll(self):
        if not self.terrain_available():return False
        changed=bool(self.map.base.poll())
        if self._los_enabled and self.screen=='map' and self.map.coverage and self.map.base.target_box.view is None and self.map.base._detail_request is None and not self.map.base.full_overview:
            view=self.coverage_view()
            if view is not None and view!=self._coverage_view:
                self._coverage_view=view;self.show_los(refine=True);changed=True
        with self._progress_lock:
            snapshot=self._progress_snapshot;self._progress_snapshot=None
        if snapshot is not None and not self.cancelled.is_set() and self.job=='coverage':
            self.map.coverage=self.merge_coverage(snapshot);changed=True
            self.map.notice=f"Computing · {snapshot['radius_km']:g} km · {len(snapshot['cells'])} sites tested"
        if not self.pending or not self.pending.done():return changed
        future=self.pending;self.pending=None
        if self._queued_profile:
            self._queued_profile=False
            try:future.result()
            except Exception:pass
            self.calculate();return True
        if self._queued_los:
            try:future.result()
            except Exception:pass
            refine=self._queued_refine;self._queued_refine=False
            self.show_los(refine=refine);return True
        try:
            value=future.result()
            if self.job in ('coverage','sites') and self.cancelled.is_set():value=None
            if self.job=='coverage':
                self.map.coverage=self.merge_coverage(value)
                if value is None:self.map.notice='Overlay cancelled after settings changed; L recalculates'
                if value:
                    self.map.notice=f"Red clear · {value['frequency_mhz']:g} MHz · {value['radius_km']:g} km radius · antenna {value['tx_height_m']:g}m / remote {value['rx_height_m']:g}m"
                self.status='Sampled ground LOS; buildings and trees are not included'
            elif self.job=='sites':
                self.sites=value;self.status='Choose a candidate to inspect its path; access and vegetation unverified'
                self.map.candidates=value['candidates'] if value else []
            else:
                self.result=value
                i=min(range(len(value['samples'])),key=lambda i:value['samples'][i]['fresnel_clearance_m'] if value['samples'][i]['fresnel_clearance_m'] is not None else float('inf'))
                value['bottleneck']=dict(value['samples'][i],coordinate=value['sample_coordinates'][i])
                self.selected_sample=None
                self.map.inspect_point=value['bottleneck'];self.status='Profile from installed USGS 3DEP elevations'
                self.map.notice=f"X F60 limiting sample {value['bottleneck']['distance_m']:.1f} m · X centers sample"
                if self._inspect_after_calculation:
                    self._inspect_after_calculation=False;self.inspect_bottleneck(on_map=True)
        except Exception as error:
            self.error=str(error)[:512];self.status='Calculation unavailable'
            if self.job=='coverage':self.map.notice=self.error
        return True
    def key(self,key):
        if not self.terrain_available():return False
        if key in ('escape','\x1b') and self.screen!='map':
            if self.screen=='profile':return self.return_to_map()
            self.screen='map';return True
        if self.screen=='call-target':
            if key in ('\r','\n'):return self.lookup_call()
            if key in ('escape','\x1b'):self.screen='map';return True
            return self.call_input.key(key)
        if self.screen=='profile' and key in ('i','I'):return self.inspect_bottleneck()
        if self.screen=='profile' and key in ('x','X'):return self.inspect_bottleneck(on_map=True)
        if self.screen=='profile' and key in ('a','A'):self.profile_zoom=None;self.selected_sample=None;return True
        if self.screen=='profile' and key in ('z','Z') and self.result:
            self.profile_zoom=(0,min(1000,self.result['distance_m']))
            candidates=[(i,row) for i,row in enumerate(self.result['samples']) if row['distance_m']<=1000 and row['fresnel_clearance_m'] is not None]
            if candidates:
                i,row=min(candidates,key=lambda item:item[1]['fresnel_clearance_m'])
                self.selected_sample=dict(row,coordinate=self.result['sample_coordinates'][i])
            return True
        if self.screen=='map' and key in ('g','G'):self.open_call();return True
        if self.screen=='map' and key in ('q','Q'):return self.go_qth()
        if self.screen=='map' and key in ('w','W'):return self.fit_path()
        if self.screen=='map' and key in ('x','X'):return self.show_obstruction()
        if self.screen=='map' and key in ('L','R','J','H','F','C','T'):key=key.lower()
        if self.screen=='bands':
            if key in ('home','end'):self.band_index=0 if key=='home' else len(self.bands)-1;return True
            if key in ('pageup','pagedown'):self.band_index=max(0,min(len(self.bands)-1,self.band_index+(-1 if key=='pageup' else 1)*max(1,self.height-5)));return True
            if key in ('up','down'):self.band_index=(self.band_index+(1 if key=='down' else -1))%len(self.bands);return True
            if key in ('\r','\n'):self.select_band(self.band_index);return True
            if key in ('escape','\x1b','m'):self.screen='map';return True
            return False
        if self.screen=='map' and key=='j':self.toggle_clearance();return True
        if self.screen=='map' and key=='h':self.open_heights();return True
        if self.screen=='map' and key=='l':return self.show_los()
        if self.screen=='map' and key=='f':self.open_bands();return True
        if self.screen=='map' and key=='r':self.cycle_radius();return True
        if key=='n':return self.nearby()
        if self.screen=='sites':
            if key=='m':self.screen='map';return True
            if key in ('up','down') and self.sites:self.site_index=(self.site_index+(1 if key=='down' else -1))%len(self.sites['candidates']);return True
            if key in ('\r','\n'):return self.choose_site()
            return False
        if self.screen=='map':return self.map.key(key)
        if key in ('m','M') and self.screen=='profile':return self.return_to_map()
        if key=='m':self.screen='map';return True
        if self.screen=='house-settings':
            if key in ('\t','backtab'):self.field=2+(self.field-2+(-1 if key=='backtab' else 1))%3;return True
            if key in ('\r','\n'):return self.show_los()
            before=self.fields[self.field].text;handled=self.fields[self.field].key(key)
            if before!=self.fields[self.field].text:
                self.map.coverage=None
                if self.pending:self.cancelled.set()
            return handled
        if key in ('\t','backtab'):self.field=(self.field+(-1 if key=='backtab' else 1))%5;return True
        if key in ('\r','\n'):return self.calculate()
        before=self.fields[self.field].text
        handled=self.fields[self.field].key(key)
        if self.fields[self.field].text!=before:
            self.map.coverage=None
            if self.pending and self.job in ('coverage','sites'):self.cancelled.set()
        return handled
    def pointer_event(self,event,width):
        if self.screen=='map':return self.map.pointer_event(event,width)
        return self.pointer(event[2],event[3],width,event[1],event[4])
    def pointer(self,column,row,width,button=0,released=False):
        if self.screen=='call-target':
            if not released and button==0 and row==3:return self.lookup_call()
            return False
        if self.screen=='profile' and not released and button==0 and row==0:
            if column<10:return self.return_to_map()
            if 24<=column<39:return self.inspect_bottleneck()
            if 39<=column<51:return self.inspect_bottleneck(on_map=True)
        if self.screen=='house-settings':
            if not released and button==0:
                if row==0:self.screen='map';return True
                if 1<=row<=3:self.field=row+1;return True
                if row==5:return self.show_los()
            return False
        if self.screen=='bands':
            if button&64:self.band_index=max(0,min(len(self.bands)-1,self.band_index+(3 if button&1 else -3)));return True
            if not released and button==0 and 2<=row<self.height-2 and self._band_offset+row-2<len(self.bands):self.select_band(self._band_offset+row-2);return True
            return False
        if self.screen=='sites':
            if not released and button==0 and row>=4 and self.sites and row-4<len(self.sites['candidates']):
                self.site_index=row-4;return self.choose_site()
            if not released and button==0 and row==0:self.screen='map';return True
            return False
        if self.screen=='map':return self.map.pointer(column,row,width,button,released)
        if not released and button==0 and row==0:
            if column<10:self.screen='map';return True
            if column<23:return self.nearby()
            return False
        if released or button!=0:return False
        if self.screen=='profile' and self.result and 10<=row<self.height-4 and 7<=column<self.width-2:
            start,end=self.profile_zoom or (0,self.result['distance_m']);distance=start+(end-start)*(column-7)/max(1,self.width-10)
            i=min(range(len(self.result['samples'])),key=lambda i:abs(self.result['samples'][i]['distance_m']-distance))
            self.selected_sample=dict(self.result['samples'][i],coordinate=self.result['sample_coordinates'][i]);return True
        if 1<=row<=5:self.field=row-1;return True
        if row==6:return self.calculate()
        return False
    def lines(self):
        if not self.terrain_available():
            c=Canvas(self.width,self.height);c.put(0,0,'Terrain / LOS disabled')
            c.put(0,2,'Enable in Settings → App: Station Map')
            self._spans=();return c.lines()
        if self.screen=='call-target':
            c=Canvas(self.width,self.height);c.put(0,0,'Profile from saved QTH to callsign')
            c.put(0,1,'Callsign: '+self.call_input.draw(max(1,self.width-10)))
            c.put(0,3,'[ Open profile ]');c.put(0,5,self.error or 'Uses the station directory position and your saved QTH.')
            self._spans=();return c.lines()
        if self.screen=='house-settings':
            c=Canvas(self.width,self.height);c.put(0,0,'[ Map M ] House radius LOS settings')
            for row,(index,label) in enumerate(((2,'Frequency MHz'),(3,'Roof antenna m'),(4,'Remote antenna m')),1):
                c.put(0,row,label+':');c.put(20,row,self.fields[index].draw(max(1,self.width-20)))
                c.role(20,row,max(1,self.width-20),'input' if self.field==index else 'body')
            c.put(0,5,f'[ Show radius LOS ] · {self.radius_km:g} km')
            c.put(0,7,'Heights above local ground. No target pin is required.')
            c.put(0,9,'Ground geometry only; buildings and trees are not included.')
            c.put(0,self.height-1,'Tab field · Enter show radius LOS · M map')
            self._spans=c.styled_spans();return c.lines()
        if self.screen=='bands':
            c=Canvas(self.width,self.height);c.put(0,0,'Frequency presets')
            visible=max(1,self.height-4);self._band_offset=max(0,min(self.band_index-visible//2,len(self.bands)-visible))
            for row,i in enumerate(range(self._band_offset,min(len(self.bands),self._band_offset+visible)),2):
                label,value=self.bands[i];c.put(0,row,('> ' if i==self.band_index else '  ')+label+' · '+value+' MHz')
            c.put(0,self.height-1,'↑↓ choose · Enter select · M map · Frequency affects Fresnel clearance')
            self._spans=();return c.lines()
        if self.screen=='map':
            self.map.width=self.width;self.map.height=self.height
            self.map.height_label=self.fields[3].text+' / '+self.fields[4].text+' m'
            return self.map.lines()
        if self.screen=='sites':
            c=Canvas(self.width,self.height);c.put(0,0,f'[ Map M ] Nearby sites · within {self.radius_km:g} km of From')
            c.put(0,1,self.error or self.status)
            c.put(0,3,'    North    East     LOS      Fresnel margin   Move')
            if self.sites:
                for i,item in enumerate(self.sites['candidates'][:max(0,self.height-6)]):
                    c.put(0,4+i,f"{'>' if i==self.site_index else ' '} {item['north_km']:+6.1f} km {item['east_km']:+6.1f} km {item['los']:7} {item['clearance_m']:+8.1f} m {item['offset_km']:5.1f} km")
            c.put(0,self.height-1,'↑↓ candidate · Enter inspect · M map · Terrain screening; check site access')
            self._spans=();return c.lines()
        c=Canvas(self.width,self.height);c.put(0,0,'[ Map M ] [ Nearby N ] [ Inspect I ] [ X map ] Terrain Profile');c.role(0,0,self.width,'toolbar')
        for i,label in enumerate(('From lat,lon','To lat,lon','Frequency MHz','From height m','To height m')):
            c.put(0,i+1,label+':');c.put(17,i+1,self.fields[i].draw(max(1,self.width-17)))
            c.role(17,i+1,max(1,self.width-17),'input' if self.field==i else 'body')
        c.put(0,6,'[ Calculating… ]' if self.pending else '[ Calculate profile ]');c.role(0,6,self.width,'control')
        if self.result:
            r=self.result;all_rows=r['samples'];x_start,x_end=self.profile_zoom or (0,r['distance_m'])
            rows=[row for row in all_rows if x_start<=row['distance_m']<=x_end]
            if len(rows)<2:rows=all_rows;x_start,x_end=0,r['distance_m']
            left=7;top=10;w=max(2,self.width-left-2);h=max(3,self.height-top-5)
            heights=[v for row in rows for v in (row['terrain_adjusted_m'],row['ray_m']) if v is not None]
            low=min(heights);high=max(heights);span=max(1,high-low)
            def line_y(value):return top+h-1-round((value-low)/span*(h-1))
            c.put(0,top,f'{high:.0f}m');c.put(0,top+h-1,f'{low:.0f}m')
            from bisect import bisect_left
            distances=[row['distance_m'] for row in rows]
            previous=None
            for x in range(w):
                distance=x_start+x*(x_end-x_start)/(w-1)
                index=min(len(rows)-1,max(1,bisect_left(distances,distance)))
                a,b=rows[index-1],rows[index]
                fraction=(distance-a['distance_m'])/(b['distance_m']-a['distance_m'])
                ray=a['ray_m']+(b['ray_m']-a['ray_m'])*fraction
                terrain=None if a['terrain_adjusted_m'] is None or b['terrain_adjusted_m'] is None else a['terrain_adjusted_m']+(b['terrain_adjusted_m']-a['terrain_adjusted_m'])*fraction
                if terrain is not None:
                    y=line_y(terrain)
                    if previous is not None:
                        for yy in range(min(y,previous),max(y,previous)+1):c.put(left+x,yy,'│')
                    c.put(left+x,y,'*');c.role(left+x,y,1,'heading');previous=y
                else:previous=None
                radius=a['fresnel_radius_m']+(b['fresnel_radius_m']-a['fresnel_radius_m'])*fraction
                lower=ray-r['fresnel_fraction']*radius
                if low<=lower<=high:c.put(left+x,line_y(lower),'·')
                c.put(left+x,line_y(ray),'-')
            cursor=self.selected_sample
            if cursor and cursor['terrain_adjusted_m'] is not None and x_start<=cursor['distance_m']<=x_end:
                cx=left+round((cursor['distance_m']-x_start)/(x_end-x_start)*(w-1));cy=line_y(cursor['terrain_adjusted_m'])
                c.put(cx,cy,'+');c.role(cx,cy,1,'accent')
            critical=r.get('bottleneck')
            if critical and x_start<=critical['distance_m']<=x_end:
                xx=left+round((critical['distance_m']-x_start)/(x_end-x_start)*(w-1))
                yy=line_y(critical['terrain_adjusted_m']);marker_x=max(left,min(xx-1,left+w-3))
                c.put(marker_x,yy,' X ');c.role(marker_x,yy,3,'obstruction')
                if yy>top:c.put(xx,yy-1,'│');c.role(xx,yy-1,1,'obstruction')
            if critical:
                c.put(0,9,f" X  {critical['distance_m']:.1f} m from start · F60 margin {critical['fresnel_clearance_m']:+.2f} m · I inspect / X map");c.role(0,9,3,'obstruction')
            c.put(left,top+h,f'{x_start/1000:.3f} km');c.put(max(left,self.width-13),top+h,f"{x_end/1000:.3f} km")
            c.put(0,7,f"{'Coarse screening' if r['coarse'] else 'Sampled'} LOS {r['sampled_los']} · Fresnel {r['sampled_fresnel']} · {r['distance_m']/1000:.2f} km")
            if not r['coarse'] and r.get('adaptive_sampling'):
                stats=r['adaptive_sampling']
                c.put(0,8,f"{r['sample_count']} samples · {stats['cleared_intervals']} stretches cleared by terrain maxima")
            if r['coarse']:c.put(0,8,'Coarse regional data: obtain finer tiles before choosing a reception site.')
            inspected=cursor or critical
            if inspected and (self.profile_zoom or cursor):
                lat,lon=inspected['coordinate']
                c.put(0,8,f"{'Cursor + · ' if cursor else ''}{lat:.6f},{lon:.6f} · terrain {inspected['elevation_m']:.2f} m ASL · ray clear {inspected['clearance_m']:+.2f} m")
            finest=r.get('finest_grid_spacing_north_m',r['native_grid_spacing_north_m']);coarsest=r['native_grid_spacing_north_m']
            detail=f'{finest:.0f}–{coarsest:.0f}' if coarsest-finest>1 else f'{coarsest:.0f}'
            c.put(0,self.height-3,f"{r['source'].split(' + ')[0]} · grid ~{detail} m N/S")
        else:
            c.put(0,8,self.error or 'From / To use decimal latitude,longitude. No synthetic terrain.')
            c.put(0,10,'PNW coverage: 43–52 N, 128–116 W. Finest installed grid is used.')
            c.put(0,11,'USGS regional tiles where installed; NOAA overview elsewhere.')
            c.put(0,13,'* terrain / - direct ray. Antenna heights are above local ground.')
        c.put(0,self.height-2,self.error or self.status);c.role(0,self.height-2,self.width,'warning' if self.error else 'status')
        c.put(0,self.height-1,'I inspect sample · X map sample · Z first km · A full path · M map')
        self._spans=c.styled_spans();return c.lines()
    def spans(self):return self._spans
    def close(self):
        self.closed=True;self.cancelled.set();self.wakeup=None;self.map.close()
        if self.pending:self.pending.cancel()
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
