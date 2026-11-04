"""Render the small real-elevation geometry model through the cell compositor."""
from functools import lru_cache
from pathlib import Path
import json
import math
from dataclasses import replace
from geometry import HeightField,Vec,Model,Camera,unit,render,merge
from paint import Scene
from build_trace import mark,Trace
from landscape_detail import Nature,details,resolve


@lru_cache(maxsize=2)
def tahoma(stride=2):
    import array,sys,zlib
    directory=Path(__file__).with_name('data')
    data=json.loads(directory.joinpath('tahoma-3dep.json').read_text())
    raw=array.array('h');raw.frombytes(zlib.decompress(directory.joinpath('tahoma-3dep.i16.zlib').read_bytes()))
    if sys.byteorder!='little':raw.byteswap()
    mark('source',len(raw))
    # Retain the full downloaded grid on disk; use a bounded 129x129 mesh.
    nx=(data['nx']-1)//stride+1;nz=(data['nz']-1)//stride+1
    values=tuple(raw[z*data['nx']+x] for z in range(0,data['nz'],stride) for x in range(0,data['nx'],stride))
    radius=6371000
    latitude=data['latitude_first']+data['latitude_step']*(data['nz']-1)/2
    dx=math.radians(data['longitude_step']*stride)*radius*math.cos(math.radians(latitude))
    dz=math.radians(data['latitude_step']*stride)*radius
    field=HeightField(nx,nz,Vec(-(nx-1)*dx/2,0,0),dx,dz,values,'meters')
    mark('height field',nx*nz)
    from vegetation import forest
    from landscape_detail import ground_mesh
    terrain=ground_mesh(field);mark('terrain',len(terrain.triangles))
    trees=forest(field);mark('instances',len(trees.triangles))
    mesh=merge((terrain,trees));mark('world',len(mesh.vertices))
    peak=field.values.index(max(field.values))
    target=Vec(field.origin.x+(peak%field.nx)*dx,1800,(peak//field.nx)*dz)
    # A south-side elevated viewpoint makes near trees larger than far forest.
    distance=24000
    eye_z=target.z-distance
    eye_y=field.height(target.x,eye_z)+500
    elevation=-math.atan2(target.y-eye_y,distance)
    camera=Camera(origin=Vec(target.x,eye_y,eye_z),elevation=elevation,
                  span_x=24000,span_y=8500,focal=distance)
    mark('camera',1)
    return Model(field,mesh,camera,unit(Vec(-.6,1,-.5)))


def view(desktop=0,overview=False,aspect=0,parallax=.005,zoom=1.65,nature=None):
    from landscape_detail import geometry_nature
    return _view(desktop,overview,aspect,parallax,zoom,geometry_nature(nature,scenery=True))


@lru_cache(maxsize=6)
def _view(desktop,overview,aspect,parallax,zoom,nature):
    from scenery import Config,camera as scene_camera,woodland
    config=Config(*nature.scenery) if nature and nature.scenery else Config()
    model=tahoma(1 if config.quality=='detailed' else 2)
    camera=scene_camera(tahoma().camera,config,aspect or model.camera.span_x/model.camera.span_y)
    if nature is not None:
        mesh=details(tahoma().terrain,tahoma().camera.origin,nature)
        if config.quality=='detailed':
            from scenery import inherited_instances
            from landscape_detail import ground_mesh
            mesh=merge((ground_mesh(model.terrain),inherited_instances(mesh,tahoma().terrain,model.terrain)))
        if nature.foliage and config.quality=='detailed' and config.density:
            mesh=merge((mesh,woodland(model.terrain,camera,nature.seed,config.density)))
        model=replace(model,mesh=mesh)
    model=replace(model,sample_limit=2097152 if config.quality=='detailed' else 470400,sample_edge=4096 if config.quality=='detailed' else 1024,haze_strength=.88*config.haze)
    if aspect>0:camera=replace(camera,span_x=camera.span_y*aspect)
    # Neighboring desktops look across the same world; overview pulls back.
    # Keep the preferred left-hand composition even with parallax disabled.
    # Desktop movement remains a small offset around this shared camera anchor.
    offset=((-.012 if config.preset=='original' else 0)+(desktop-1)*parallax)*camera.span_x
    camera=replace(camera,origin=Vec(camera.origin.x+offset,camera.origin.y+(600*(zoom-1)/.65 if overview else 0),camera.origin.z),
                   elevation=camera.elevation+(.025*(zoom-1)/.65 if overview else 0),
                   span_x=camera.span_x*(zoom if overview else 1),
                   span_y=camera.span_y*(zoom if overview else 1))
    return replace(model,camera=camera)


view.cache_clear=_view.cache_clear
view.cache_info=_view.cache_info


@lru_cache(maxsize=4)
def base(width,height,ascii=False,lighting_tick=0,desktop=0,overview=False,moon_phase='auto',parallax=.005,zoom=1.65,terrain_shadows=True,nature=None):
    from lighting import environment
    from moon import phase_value
    phase=phase_value(moon_phase,lighting_tick*20)
    env=environment(lighting_tick*20)
    env=env._replace(moonlight=env.moonlight*(.5+.5*math.cos(phase*math.tau)))
    model=view(desktop,overview,width/max(1,height*2),parallax,zoom,nature)
    from build_trace import preview
    from loading import wire_preview
    preview(lambda:wire_preview(model,width,height))
    cells,_=render(model,width,height,environment=env,moon_phase=phase,cast_shadows=terrain_shadows,prepare_wire=True,season=nature.season if nature else 'summer',grid_strength=nature.grid if nature else .08)
    if ascii:cells={xy:('.' if char=='·' else ':',style) for xy,(char,style) in cells.items()}
    return cells


def frame(width,height,ascii=False,age=0,desktop=0,overview=False,mode='dynamic',moon_phase='auto',parallax=.005,zoom=1.65,terrain_shadows=True,nature=None):
    from night_scene import scene_age
    nature=resolve(nature,age)
    age=scene_age(age,mode)
    if parallax==0:desktop=1
    if zoom==1:overview=False
    # A 20-second virtual-time bucket: tiny shifts, no lighting work per UI tick.
    return Scene(base(width,height,ascii,int(max(0,age)//20),desktop,overview,moon_phase,parallax,zoom,terrain_shadows,nature),{})


from frame_worker import Renderer as FrameWorker


class Renderer(FrameWorker):
    def frame(self,width,height,ascii=False,age=0,desktop=0,overview=False,mode='dynamic',moon_phase='auto',parallax=.005,zoom=1.65,terrain_shadows=True,nature=None):
        if not self._resume('terrain'):
            return Scene(self.completed[1],{}) if self.completed and self.completed[0][:3]==(width,height,ascii) else Scene({},{})
        from night_scene import scene_age
        nature=resolve(nature,age)
        age=scene_age(age,mode)
        if parallax==0:desktop=1
        if zoom==1:overview=False
        key=(width,height,ascii,int(max(0,age)//20),desktop,overview,moon_phase,parallax,zoom,terrain_shadows,nature)
        desired={key,key[:5]+(not overview,)+key[6:]}
        desired.update(key[:4]+((desktop+d)%3,False)+key[6:] for d in (-1,1))
        if self.pending is not None and self.pending.done():
            result=self.pending.result();self.ready[self.requested]=result
            # Fast demo time may advance beyond a lighting key before it finishes.
            # Show completed work for the same viewport/camera while newer work runs.
            if self.requested[:3]==key[:3] and self.requested[4:6]==key[4:6]:
                self.completed=(self.requested,result)
            while len(self.ready)>4:
                victim=next((k for k in self.ready if k not in desired),next((k for k in self.ready if k!=key),next(iter(self.ready))))
                self.ready.pop(victim)
            self.pending=None
        if key in self.ready:
            self.completed=(key,self.ready[key])
            if self.prewarm and self.pending is None:
                neighbors=[key[:4]+((desktop+d)%3,False)+key[6:] for d in (-1,1)] if parallax else []
                if zoom>1:neighbors.append(key[:5]+(not overview,)+key[6:])
                candidate=next((k for k in neighbors if k not in self.ready),None)
                if candidate is not None:self.start(candidate)
            return Scene(self.completed[1],{})
        if self.pending is None:self.start(key)
        if self.completed is not None and self.completed[0][:3]==key[:3]:
            return Scene(self.completed[1],{})
        return Scene({}, {})
