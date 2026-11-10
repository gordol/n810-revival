# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Mac native-GUI effect provider; terminal effect producers are untouched."""
from array import array
from functools import lru_cache
from pathlib import Path
import importlib.util,threading,time

class Provider:
    def __init__(self):
        path=Path(__file__).resolve().parents[2]/'build/graphics/_gpueffects.abi3.so'
        spec=importlib.util.spec_from_file_location('_gpueffects',path)
        self.gpu=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.gpu)
        self.owner=threading.get_ident();self.seconds=0.;self.cpu_seconds=0.;self.restores=[]
    @staticmethod
    @lru_cache(maxsize=8)
    def plan(seed,strands):
        import flurry
        return array('d',(value for row in flurry.plan(seed)[:strands] for value in row))
    def frame(self,name,width,height,step,ascii=False,weather=None,seed=0,nature_age=None,
              flurry_strands=48,flurry_sway=.6,flurry_speed=1.,flux_density=1.,flux_glow=.15,
              flux_arms=2,flurry_provider=None):
        if threading.get_ident()!=self.owner:raise RuntimeError('GPU effects must run on the frontend context owner')
        import paint
        from native_scene import NativeScene,base_plane
        lib=paint.NATIVE_SCENES
        if lib is None:raise RuntimeError('GPU effects require the existing native scene interface')
        base=base_plane(lib,width,height,ascii);started=time.perf_counter();cpu=time.process_time()
        if name=='flurry':
            count=max(8,min(192,int(flurry_strands)))
            plane=self.gpu.flurry(base,self.plan(seed,count),step,flurry_sway,flurry_speed,ascii)
        elif name=='flux':plane=self.gpu.flux(base,step,flux_density,flux_glow,flux_arms,ascii)
        else:raise ValueError('Not a GPU procedural effect')
        self.seconds+=time.perf_counter()-started;self.cpu_seconds+=time.process_time()-cpu
        return NativeScene(lib,base,plane,width,height)
    def status(self):
        result=dict(self.gpu.stats(),wall_seconds=self.seconds,cpu_seconds=self.cpu_seconds)
        if hasattr(self,'pixel_gpu'):result['pixel_composition']=dict(self.pixel_gpu.stats)
        if hasattr(self,'map_gpu'):result['station_map']=dict(self.map_gpu.stats)
        if hasattr(self,'terrain_gpu'):result['terrain_coverage']=dict(self.terrain_gpu.stats)
        if hasattr(self,'terrain_shader'):result['terrain_shading']=dict(self.terrain_shader.stats)
        return result
    def install(self,platform):
        import core
        original=core.effect_frame
        def effects(name,*args,**kwargs):
            return self.frame(name,*args,**kwargs) if name in ('flux','flurry') else original(name,*args,**kwargs)
        core.effect_frame=effects
        attach=platform.attach;present=platform.present
        def attached(host,*args):
            attach(host,*args)
            # GPU resources belong to the foreground GL context, not worker threads.
            host.background_async=False
            import sys
            path=str(Path(__file__).resolve().parent)
            if path not in sys.path:sys.path.insert(0,path)
            from map_gpu import MapGPU
            from terrain_gpu import CoverageGPU
            from terrain_shading import ExactShader
            from pixel_gpu import PixelGPU
            import map_terrain,desktop_elevation,geometry_compute,geometry,scene_acceleration
            self.map_gpu=MapGPU();self.terrain_gpu=CoverageGPU();self.terrain_shader=ExactShader()
            native_scene=getattr(platform,'gpu_context',None) is not None
            if not native_scene:
                self.pixel_gpu=PixelGPU();self.restores.append(self.pixel_gpu.install(platform))
            replacements=[(geometry_compute,'coverage_data',self.terrain_gpu.coverage),
                          (scene_acceleration,'_shader',self.terrain_shader)]
            if not native_scene:
                replacements.extend(((map_terrain,'sample_terrain',self.map_gpu.sample),
                                     (map_terrain,'draw_vectors',self.map_gpu.vectors),
                                     (desktop_elevation,'render',self.map_gpu.render_dem)))
            for module,name,value in replacements:
                prior=getattr(module,name);setattr(module,name,value)
                self.restores.append(lambda module=module,name=name,prior=prior:setattr(module,name,prior))
            geometry.raster.cache_clear()
            if host._native is None:raise RuntimeError('GPU composition requires native cell planes')
            lib=host._native.lib
            for name,index in (() if native_scene else (('compose',2),('blend_scene',3))):
                cpu=getattr(lib,name);gpu=getattr(self.gpu,name)
                def submit(*args,_cpu=cpu,_gpu=gpu,_index=index):
                    changed,computed,repair=_gpu(*args)
                    if repair:
                        ids=array('I');ids.frombytes(repair)
                        corrected=list(args);corrected[_index]=ids;_cpu(*corrected)
                    return ('',computed) if _index==2 else computed
                setattr(lib,name,submit)
                self.restores.append(lambda lib=lib,name=name,cpu=cpu:setattr(lib,name,cpu))
            flush=host.flush
            def full_flush(budget=2048,max_seconds=None,*,serialize=True):
                scene=host.backdrop
                if scene and getattr(scene,'native_surface',None) is None and hasattr(scene,'__dict__'):
                    pointer=lib.surface(host.width,host.height);glyphs=set()
                    for i in range(host.width*host.height):
                        char,color=scene.get((i%host.width,i//host.width),(' ',13));glyphs.add(char)
                        lib.set(pointer,i,ord(char),color)
                    scene.native_surface=pointer;scene.width=host.width;scene.height=host.height;scene.native_glyphs=''.join(sorted(glyphs))
                return flush(host.width*host.height,None,serialize=serialize)
            host.flush=full_flush
        def presented(*args):
            result=present(*args);platform.report['procedural_gpu']=self.status();return result
        platform.attach=attached;platform.present=presented
        def restore():
            for undo in reversed(self.restores):undo()
            core.effect_frame=original
        return restore
