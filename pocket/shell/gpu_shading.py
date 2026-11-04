"""Optional Apple GPU lighting/interpolation kernel; coverage remains authoritative."""
from collections import OrderedDict
import time


def numeric(xp,a,p):
    snow=xp.clip((a['vertices'][:,1]-p['snowline'])/p['transition']+.5,0,1)
    terrain=a['terrain']
    direct=p['sunlight']*xp.maximum(xp.sum(a['normals']*p['sun'],axis=1),0)*a['sun_v']
    lunar=p['moonlight']*xp.maximum(xp.sum(a['normals']*p['moon'],axis=1),0)*a['moon_v']
    snow_light=snow*terrain
    lunar=lunar*(1+.25*snow_light)
    tint=xp.stack((.65+.17*snow_light,.8+.10*snow_light,xp.ones_like(snow)),axis=1)
    light=xp.minimum(1.2,p['ambient']+.72*direct[:,None]+lunar[:,None]*tint)
    light=light+a['glass'][:,None]*p['glass_emission']*(1-p['sunlight'])
    base=xp.where(terrain[:,None]>0,p['terrain_base']+(p['snow_base']-p['terrain_base'])*snow[:,None],a['bases'])
    colors=base*light
    ids=a['ids'];weights=a['weights'][:,:,None]
    color=xp.sum(colors[ids]*weights,axis=1)
    albedo=a['albedos']*p['season_scale']
    albedo=albedo+(p['winter_color']-albedo)*p['winter']
    detail=albedo*xp.sum(light[ids]*weights,axis=1)
    color=xp.where(a['has_albedo'][:,None]>0,detail,color)
    view=p['origin']-a['water']
    view=view/xp.sqrt(xp.maximum(xp.sum(view*view,axis=1),1e-24))[:,None]
    half=view+p['reflection_light']
    half=half/xp.sqrt(xp.maximum(xp.sum(half*half,axis=1),1e-24))[:,None]
    glint=xp.maximum(half[:,1],0)**48*(p['moonlight']*180+p['sunlight']*90)
    ripple=.90+.1*xp.sin(a['water'][:,2]*.13+a['water'][:,0]*.09)
    water_color=(p['sky']*.6+p['water_base']+glint[:,None])*ripple[:,None]
    color=xp.where(a['has_water'][:,None]>0,water_color,color)
    color=color*(1+.65*(1-p['sunlight']))
    color=color+(p['haze']-color)*a['haze'][:,None]
    sky=p['sky']*a['gradient'][:,None]
    return xp.where(a['valid'][:,None]>0,color,sky)


class Shader:
    def __init__(self,backend='gpu',max_entries=2,max_bytes=128*1024*1024):
        import numpy as np
        self.np=np;self.backend=backend;self.rows=OrderedDict()
        self.max_entries=max_entries;self.max_bytes=max_bytes
        self.stats=dict(backend=backend,frames=0,samples=0,prepared_hits=0,prepared_misses=0,
                        preparation_seconds=0.,execution_and_readback_seconds=0.,packing_seconds=0.,owned_prepared_bytes=0)
        self.mx=None
        if backend=='gpu':
            import mlx.core as mx
            if not mx.metal.is_available():raise RuntimeError('Apple Metal GPU unavailable')
            self.mx=mx
            self.kernel=mx.compile(lambda a,p:numeric(mx,a,p))
            self.stats.update(device=mx.device_info(),precision='float32')
        else:self.stats.update(device='CPU NumPy',precision='float64')

    def prepare(self,model,coverage):
        np=self.np
        mesh,normals,materials,samples,depths,haze,pw,ph,albedos,water=coverage
        key=id(samples)
        if key in self.rows and self.rows[key][0] is samples:
            self.stats['prepared_hits']+=1;self.rows.move_to_end(key);return self.rows[key][1]
        began=time.perf_counter();self.stats['prepared_misses']+=1
        vertices=np.asarray(mesh.vertices,dtype=np.float64)
        ids=np.frombuffer(samples.ids,dtype=np.uint32).reshape(-1,3).copy()
        valid=ids[:,0]!=samples.empty;ids[~valid]=0
        first=np.frombuffer(samples.weights,dtype=np.float32).reshape(-1,2).astype(np.float64)
        weights=np.column_stack((first,1-first[:,0]-first[:,1]))
        rgb={'tree':(28,67,47),'fir':(28,67,47),'cedar':(40,72,52),'wood':(121,91,56),
             'roof':(52,65,66),'metal':(112,123,128),'glass':(210,166,89),'flower':(166,130,174),
             'fur':(108,87,62),'bird':(75,79,83),'fern':(45,82,47)}
        packed=np.frombuffer(albedos.values,dtype=np.uint32)
        albedo=np.column_stack(((packed>>16)&255,(packed>>8)&255,packed&255)).astype(np.float64)
        field=model.terrain
        ix=np.clip(np.rint((vertices[:,0]-field.origin.x)/field.dx),0,field.nx-1).astype(np.int32)
        iz=np.clip(np.rint((vertices[:,2]-field.origin.z)/field.dz),0,field.nz-1).astype(np.int32)
        a=dict(vertices=vertices,normals=np.asarray(normals,dtype=np.float64),
               terrain=np.asarray([m=='terrain' for m in materials],dtype=np.float64),
               glass=np.asarray([m=='glass' for m in materials],dtype=np.float64),
               bases=np.asarray([rgb.get(m,(90,120,150)) for m in materials],dtype=np.float64),
               ids=ids,weights=weights,valid=valid.astype(np.float64),albedos=albedo,
               has_albedo=(packed!=0xffffffff).astype(np.float64),
               water=np.asarray([p if p is not None else (0,0,0) for p in water],dtype=np.float64),
               has_water=np.asarray([p is not None for p in water],dtype=np.float64),
               haze=np.asarray(haze,dtype=np.float64),
               gradient=.72+.28*(np.arange(len(samples))//pw)/max(1,ph-1))
        row=dict(cpu=a,indices=iz*field.nx+ix)
        if self.mx:
            mx=self.mx
            with mx.stream(mx.gpu):
                row['gpu']={k:mx.array(v.astype(np.uint32 if k=='ids' else np.float32)) for k,v in a.items()}
                mx.eval(row['gpu'])
        size=sum(x.nbytes for x in a.values())+row['indices'].nbytes
        if 'gpu' in row:size+=sum(v.nbytes for v in row['gpu'].values())
        row['bytes']=size
        if size<=self.max_bytes:
            self.rows[key]=(samples,row)
            while len(self.rows)>self.max_entries or sum(v[1]['bytes'] for v in self.rows.values())>self.max_bytes:
                self.rows.popitem(last=False)
        self.stats['owned_prepared_bytes']=sum(v[1]['bytes'] for v in self.rows.values())
        self.stats['preparation_seconds']+=time.perf_counter()-began
        return row

    def shade(self,model,coverage,env,sun,moon,season):
        np=self.np;row=self.prepare(model,coverage)
        winter=.38 if season=='winter' else 0.
        scale=(1.10,.95,.88) if season=='autumn' else (.94,1.08,.98) if season=='spring' else (1,1,1)
        params=dict(sun=env.sun,moon=env.moon,ambient=env.ambient,sky=env.sky,haze=env.haze,
                    sunlight=env.sunlight,moonlight=env.moonlight,snowline=3000 if model.terrain.units=='meters' else .68,
                    transition=400 if model.terrain.units=='meters' else .15,season_scale=scale,winter=winter,
                    winter_color=(205,214,213),origin=model.camera.origin,
                    reflection_light=env.moon if env.moonlight else env.sun,
                    glass_emission=(.18,.10,.025),terrain_base=(56,81,67),snow_base=(198,207,203),water_base=(7,16,20))
        index=row['indices'];n=len(index)
        sunlight=np.asarray(sun,dtype=np.float64)[index] if len(sun) else np.ones(n)
        moonlight=np.asarray(moon,dtype=np.float64)[index] if len(moon) else np.ones(n)
        began=time.perf_counter()
        if self.mx:
            mx=self.mx
            with mx.stream(mx.gpu):
                a=dict(row['gpu'],sun_v=mx.array(sunlight.astype(np.float32)),moon_v=mx.array(moonlight.astype(np.float32)))
                p={k:mx.array(np.asarray(v,dtype=np.float32)) for k,v in params.items()}
                pixels=self.kernel(a,p);mx.eval(pixels);mx.synchronize()
                result=np.array(pixels)
        else:
            a=dict(row['cpu'],sun_v=sunlight,moon_v=moonlight)
            result=numeric(np,a,{k:np.asarray(v,dtype=np.float64) for k,v in params.items()})
        self.stats['execution_and_readback_seconds']+=time.perf_counter()-began
        from gpu_pixels import Pixels
        began=time.perf_counter();pixels=Pixels(result,np,self.stats)
        self.stats['packing_seconds']+=time.perf_counter()-began
        self.stats['frames']+=1;self.stats['samples']+=len(pixels)
        return pixels
