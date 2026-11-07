# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Metal terrain shading with counted RGB8 boundary corrections."""
from gpu_shading import Shader,numeric

class ExactShader(Shader):
    def __init__(self):
        super().__init__('gpu');self.stats['precision_samples']=0;self.stats['cpu_repair_vertices']=0
    def shade(self,model,coverage,env,sun,moon,season):
        import time
        np,mx=self.np,self.mx;row=self.prepare(model,coverage)
        scale=(1.10,.95,.88) if season=='autumn' else (.94,1.08,.98) if season=='spring' else (1,1,1)
        params=dict(sun=env.sun,moon=env.moon,ambient=env.ambient,sky=env.sky,haze=env.haze,
                    sunlight=env.sunlight,moonlight=env.moonlight,snowline=3000 if model.terrain.units=='meters' else .68,
                    transition=400 if model.terrain.units=='meters' else .15,season_scale=scale,winter=.38 if season=='winter' else 0.,
                    winter_color=(205,214,213),origin=model.camera.origin,reflection_light=env.moon if env.moonlight else env.sun,
                    glass_emission=(.18,.10,.025),terrain_base=(56,81,67),snow_base=(198,207,203),water_base=(7,16,20))
        index=row['indices'];n=len(index)
        sunlight=np.asarray(sun,dtype=np.float64)[index] if len(sun) else np.ones(n)
        moonlight=np.asarray(moon,dtype=np.float64)[index] if len(moon) else np.ones(n)
        began=time.perf_counter()
        with mx.stream(mx.gpu):
            a=dict(row['gpu'],sun_v=mx.array(sunlight.astype(np.float32)),moon_v=mx.array(moonlight.astype(np.float32)))
            p={k:mx.array(np.asarray(v,dtype=np.float32)) for k,v in params.items()}
            pixels=self.kernel(a,p);mx.eval(pixels);result=np.array(pixels).astype(np.float64)
        uncertain=np.any(np.abs(result-np.rint(result))<.01,axis=1)
        ids=np.flatnonzero(uncertain)
        if len(ids):
            vertex_keys={'vertices','normals','terrain','glass','bases'}
            a={k:v if k in vertex_keys else v[ids] for k,v in row['cpu'].items()}
            a.update(sun_v=sunlight,moon_v=moonlight)
            result[ids]=numeric(np,a,{k:np.asarray(v,dtype=np.float64) for k,v in params.items()})
            self.stats['cpu_repair_vertices']+=len(row['cpu']['vertices'])
        self.stats['precision_samples']+=len(ids);self.stats['frames']+=1;self.stats['samples']+=len(result)
        self.stats['execution_and_readback_seconds']+=time.perf_counter()-began
        from gpu_pixels import Pixels
        return Pixels(result,np,self.stats)
