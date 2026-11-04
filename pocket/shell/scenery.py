"""Small scenery recipes and a local named library; no app or radio state."""
from collections import namedtuple
from functools import lru_cache
import json
import math
import os
from pathlib import Path
import tempfile

Config=namedtuple('Config','preset quality density haze east north height yaw tilt zoom',defaults=('original','compact',1.,1.,0.,0.,0.,0.,0.,1.))
PRESETS=('original','wide','elevated','valley')
QUALITIES=('compact','detailed')
PHASES=('auto','full','waxing','crescent','new','waning')
ROOT=Path(__file__).resolve().parent


def validate(value):
    if not isinstance(value,dict) or set(value)!=set(Config._fields):raise ValueError('invalid scenery recipe')
    c=Config(**value)
    if c.preset not in PRESETS or c.quality not in QUALITIES:raise ValueError('invalid scenery choice')
    for key,lo,hi in (('density',0,3),('haze',0,2),('east',-20000,20000),('north',-20000,20000),('height',-5000,10000),('yaw',-180,180),('tilt',-60,60),('zoom',.25,4)):
        v=getattr(c,key)
        if type(v) not in (int,float) or not math.isfinite(v) or not lo<=v<=hi:raise ValueError('invalid scenery range')
    return c


@lru_cache(maxsize=1)
def presets():return json.loads((ROOT/'data/camera-presets.json').read_text())


def camera(base,config,aspect):
    from dataclasses import replace
    from geometry import Vec,Camera
    c=base
    if config.preset!='original':
        saved=presets()[config.preset]['camera'];c=Camera(**{**saved,'origin':Vec(*saved['origin'])})
    return replace(c,origin=Vec(c.origin.x+config.east,c.origin.y+config.height,c.origin.z+config.north),yaw=c.yaw+math.radians(config.yaw),elevation=max(-1.4,min(1.4,c.elevation+math.radians(config.tilt))),span_y=c.span_y/config.zoom,span_x=c.span_y*aspect/config.zoom)


@lru_cache(maxsize=3)
def woodland(field,camera,seed,density):
    """Stable world lattice, frustum admission, and bounded instance geometry."""
    from geometry import Vec,merge,cone
    from vegetation import lattice,noise
    meshes=[];count=0
    # The same world positions survive camera changes. Density admits a nested
    # subset; increasing it adds trees without relocating the existing ones.
    spacing=180
    from build_trace import checkpoint
    for iz in range(int((field.nz-1)*field.dz)//spacing):
        checkpoint()
        z=field.origin.z+iz*spacing
        if abs(z-camera.origin.z)>30000:continue
        for ix in range(int((field.nx-1)*field.dx)//spacing):
            x=field.origin.x+ix*spacing
            if abs(x-camera.origin.x)>24000:continue
            if lattice(ix+seed,iz+413)>.22*density:continue
            x+=(lattice(ix+seed,iz)-.5)*spacing*.8
            zz=z+(lattice(ix,iz+seed)-.5)*spacing*.8
            if not (field.origin.x<=x<=field.origin.x+(field.nx-1)*field.dx and field.origin.z<=zz<=field.origin.z+(field.nz-1)*field.dz):continue
            y=field.height(x,zz)
            if y>2150 or noise(x,zz,900)<.22:continue
            u,v,depth=camera.project(Vec(x,y,zz))
            if depth<100 or not (-.03<u<1.03 and -.08<v<1.08):continue
            h=22+noise(x,zz,55)*32;owner=f'woodland:{ix}:{iz}'
            for offset,scale in (((.12,.85),(.5,.6)) if depth<9000 else ((.1,1.),)):
                meshes.append(cone(Vec(x,y+h*offset,zz),h*.32*scale,h*scale,'fir',owner))
            count+=1
            if count>=3200:return merge(meshes)
    return merge(meshes)


def inherited_instances(mesh,coarse,fine):
    """Retain compact instance identity/placement; seat it on the refined DEM."""
    from geometry import Mesh,Vec
    triangles=[t for t in mesh.triangles if t.material!='terrain']
    used=sorted({i for t in triangles for i in t[:3]});indices={old:new for new,old in enumerate(used)}
    vertices=[]
    for i in used:
        p=mesh.vertices[i]
        try:dy=fine.height(p.x,p.z)-coarse.height(p.x,p.z)
        except ValueError:dy=0
        vertices.append(Vec(p.x,p.y+dy,p.z))
    return Mesh(tuple(vertices),tuple(t._replace(a=indices[t.a],b=indices[t.b],c=indices[t.c]) for t in triangles))


class Library:
    def __init__(self,directory=None):
        self.directory=Path(directory) if directory else ROOT/'artifacts/scenery-library'
        self.selected='';self.notice='';self.counter=0
    def names(self):
        return tuple(p.stem for p in sorted(self.directory.glob('scene-*.json')))[:128] if self.directory.exists() else ()
    def save(self,host):
        from datetime import datetime,timezone
        data={'version':1,'scenery':dict(host.scenery),'appearance':{k:getattr(host,k) for k in ('scene_seed','season','light_mode','moon_phase','terrain_grid','show_foliage','show_animals','show_flowers','terrain_shadows')}}
        self.directory.mkdir(parents=True,exist_ok=True)
        name='scene-'+host.scenery['preset']+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S-%fZ')
        fd,tmp=tempfile.mkstemp(dir=self.directory,prefix='.scene-')
        try:
            with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2);f.write('\n')
            os.replace(tmp,self.directory/(name+'.json'))
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        self.selected=name;self.notice='Saved '+name;return name
    def load(self,host,name):
        if name not in self.names():raise ValueError('unknown scenery')
        path=self.directory/(name+'.json')
        if path.stat().st_size>16384:raise ValueError('scenery file too large')
        d=json.loads(path.read_text());c=validate(d['scenery'])
        if d.get('version')!=1:raise ValueError('unknown scenery version')
        a=d['appearance']
        if a['season'] not in ('auto','spring','summer','autumn','winter') or a['light_mode'] not in ('dynamic','day','night'):raise ValueError('invalid scene appearance')
        if a['moon_phase'] not in PHASES or type(a['scene_seed']) is not int or not 0<=a['scene_seed']<2**32:raise ValueError('invalid scene seed or moon')
        if type(a['terrain_grid']) not in (int,float) or not 0<=a['terrain_grid']<=.35:raise ValueError('invalid scene grid')
        for k in ('show_foliage','show_animals','show_flowers','terrain_shadows'):
            if type(a[k]) is not bool:raise ValueError('invalid scene toggle')
        host.set_preference('scenery',c._asdict())
        for k in ('scene_seed','season','light_mode','moon_phase','terrain_grid','show_foliage','show_animals','show_flowers','terrain_shadows'):host.set_preference(k,a[k])
        self.selected=name;self.notice='Loaded '+name
        refresh(host)


def refresh(host):
    if host.effect!='terrain':host.set_effect('terrain')
    host.set_preference('background_enabled',True)
    host.camera_motion=None;host.background_step=-1
    host.invalidate((0,0,host.width,host.height))


def rows(host,library):
    from controls import Choice,Slider,Button
    def getter(key):return lambda:host.scenery[key]
    def setter(key):
        def set(value):host.set_preference('scenery',{**host.scenery,key:value});refresh(host)
        return set
    def safe(action):
        try:action()
        except (OSError,ValueError,KeyError,TypeError) as e:library.notice=str(e)
    def browse(d):
        names=library.names()
        if names:
            i=names.index(library.selected) if library.selected in names else -1
            safe(lambda:library.load(host,names[(i+d)%len(names)]))
    def capture():
        done=host.terrain_renderer.completed if host.terrain_renderer else None
        if not done:library.notice='Wait for terrain to finish';return
        from model_scene import view
        from camera_poc import capture as save_capture
        key,cells=done
        model=view(key[4],key[5],key[0]/(key[1]*2),key[7],key[8],key[10])
        n=key[10];path=save_capture(library.directory,model.camera,cells,key[0],key[1],'day' if key[3]==0 else 'night' if key[3]==1750 else 'dynamic',key[9],n)
        # This companion describes the exact completed render, even if sliders
        # already request another frame. Never label old pixels with new settings.
        path.with_suffix('.scene.json').write_text(json.dumps({'version':1,'render_key':{'lighting_tick':key[3],'moon_phase':key[6]},'scenery':dict(zip(Config._fields,n.scenery)) if n.scenery else Config()._asdict()},indent=2)+'\n')
        library.notice='Captured '+path.name
    controls=[Choice('Vantage',getter('preset'),setter('preset'),PRESETS).row(),Choice('Detail',getter('quality'),setter('quality'),QUALITIES).row()]
    for label,k,lo,hi,step in (('Trees','density',0,3,.25),('Haze','haze',0,2,.1),('East / west (m)','east',-20000,20000,150),('North / south (m)','north',-20000,20000,150),('Height (m)','height',-5000,10000,150),('Turn (deg)','yaw',-180,180,2),('Tilt (deg)','tilt',-60,60,2),('Zoom','zoom',.25,4,.1)):
        controls.append(Slider(label,getter(k),setter(k),lo,hi,step).row())
    controls += [('Seed',lambda:str(host.scene_seed),lambda d:(host.set_preference('scene_seed',(host.scene_seed+d)%2**32),refresh(host))),Button('Save scenery',lambda:safe(lambda:library.save(host))).row(),('Library',lambda:library.selected or 'No selection',browse),Button('Capture view',lambda:safe(capture)).row(),('Status',lambda:library.notice or 'Ready',lambda d:None)]
    return controls
