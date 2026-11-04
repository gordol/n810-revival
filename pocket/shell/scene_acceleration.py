"""Opt-in numeric backend and bounded persistent view cache; CPU remains default."""
import functools
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import math
from array import array
from collections import OrderedDict

_shader=None
_cache=None
_original_base=None
_fallbacks=0
_fallback_reason=None
_shader_lock=threading.RLock()


def shade_pixels(model,coverage,env,sun,moon,season):
    global _fallbacks,_fallback_reason
    if _shader is None:return None
    from build_trace import checkpoint
    checkpoint()
    try:
        with _shader_lock:pixels=_shader.shade(model,coverage,env,sun,moon,season)
    except (RuntimeError,ValueError,MemoryError,OSError) as error:
        _fallbacks+=1;_fallback_reason=str(error)
        return None
    checkpoint()
    return pixels


def status():
    return dict(shader=dict(_shader.stats) if _shader else {'backend':'cpu-reference'},
                cache=dict(_cache.stats) if _cache else None,fallbacks=_fallbacks,fallback_reason=_fallback_reason)


def configure(backend='cpu',cache_dir=None):
    """Launch once before workers; optional dependencies never prevent startup."""
    import time
    began=time.monotonic();error=None
    try:
        if backend!='cpu' or cache_dir is not None or _shader is not None or _cache is not None:install(backend,cache_dir)
    except (ImportError,RuntimeError,ValueError,OSError,MemoryError) as failure:
        error=type(failure).__name__+': '+str(failure)
        install('cpu')
    return dict(requested_backend=backend,cache_directory=str(cache_dir) if cache_dir else None,
                setup_seconds=time.monotonic()-began,setup_fallback=error)


def cache_identity(backend,root=None):
    """Conservatively invalidate for app source and bundled scene data changes."""
    import hashlib
    import sys,platform,importlib.metadata
    root=Path(root) if root is not None else Path(__file__).parent
    # The camera presets and helpers such as effects.sample affect final cells.
    # Include the whole flat application source set so adding a dependency does
    # not require updating a hand-maintained list. Generated artifacts are outside
    # these locations and do not invalidate otherwise reusable completed views.
    paths=sorted(set(root.glob('*.py'))|{p for p in (root/'data').rglob('*') if p.is_file()})
    versions={n:importlib.metadata.version(n) for n in ('numpy','mlx')} if backend=='gpu' else ({'numpy':importlib.metadata.version('numpy')} if backend=='numpy' else {})
    identity=dict(schema=2,backend=backend,versions=versions,python=sys.version,
                  machine=platform.machine(),files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})
    return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()


class ViewCache:
    def __init__(self,path,identity,max_entries=4,max_bytes=64*1024*1024):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=True)
        self.identity=identity;self.max_entries=max_entries;self.max_bytes=max_bytes
        self.lock=threading.RLock()
        self.hot=OrderedDict()
        self.stats=dict(hits=0,disk_hits=0,memory_hits=0,misses=0,writes=0,evictions=0,invalid=0,entries=0,bytes=0)
    def key(self,args):
        import hashlib
        raw=json.dumps([self.identity,args],separators=(',',':'),allow_nan=False).encode()
        return hashlib.sha256(raw).hexdigest()
    def get(self,args):
        import hashlib
        import zipfile,zlib
        key=self.key(args);path=self.path/(key+'.view')
        if key in self.hot:
            self.hot.move_to_end(key);self.stats['hits']+=1;self.stats['memory_hits']+=1
            return self.hot[key][0]
        try:
            if path.stat().st_size>self.max_bytes:raise ValueError('cache file too large')
            with zipfile.ZipFile(path) as z:
                if sorted(z.namelist())!=['cells.bin','meta.json','wire.json']:raise ValueError('cache members')
                if z.getinfo('meta.json').file_size>32768 or z.getinfo('cells.bin').file_size>2097152*12 or z.getinfo('wire.json').file_size>64*1024*1024:raise ValueError('cache member too large')
                meta=json.loads(z.read('meta.json'))
                if meta['key']!=key or meta['identity']!=self.identity:raise ValueError('cache identity')
                w,h=meta['size'];raw=z.read('cells.bin')
                if not 1<=w<=4096 or not 1<=h<=2048 or w*h>2097152 or len(raw)!=w*h*12:raise ValueError('cache dimensions')
                if hashlib.sha256(raw).hexdigest()!=meta['cells_sha256']:raise ValueError('cache cells digest')
                from geometry import Frame
                from loading import WireFrame
                frame=Frame()
                for i,(char,color) in enumerate(struct.iter_unpack('!IQ',raw)):
                    if not chr(char).isprintable() or color>=1<<49:raise ValueError('cache cell')
                    frame[i%w,i//w]=(chr(char),color)
                data=json.loads(z.read('wire.json'));wire=WireFrame()
                if len(data['items'])>w*h or len(data['depth_range'])!=2 or not all(math.isfinite(v) for v in data['depth_range']):raise ValueError('wire bounds')
                for x,y,char,depth in data['items']:
                    if type(x) is not int or type(y) is not int or not 0<=x<w or not 0<=y<h or len(char)!=1 or not char.isprintable() or math.isnan(depth):raise ValueError('wire item')
                    wire[x,y]=char;wire.depth[x,y]=depth
                wire.depth_range=tuple(data['depth_range'])
                surface=data['surface_depth']
                if surface is not None:
                    values,pw,ph,sw,sh=surface
                    if type(pw) is not int or type(ph) is not int or not 1<=pw<=4096 or not 1<=ph<=4096 or pw*ph>2097152 or len(values)!=pw*ph or (sw,sh)!=(w,h) or any(math.isnan(v) for v in values):raise ValueError('wire surface dimensions')
                    wire.surface_depth=(array('f',values),pw,ph,sw,sh)
                if data['starts'] is not None:
                    if len(data['starts'])!=w*h or not all(math.isfinite(v) and 0<=v<=1 for v in data['starts']):raise ValueError('wire starts')
                    wire.starts=array('f',data['starts'])
                bands=data['bands']
                if bands is not None:
                    if len(bands)!=64 or sum(map(len,bands))>w*h or any(type(i) is not int or not 0<=i<w*h for band in bands for i in band):raise ValueError('wire bands')
                    wire.bands=bands
                wire.contours={tuple(xy) for xy in data['contours']};wire.accents={tuple(xy) for xy in data['accents']}
                if not (wire.contours|wire.accents)<=wire.keys():raise ValueError('wire accents outside coverage')
                frame.wireframe=wire
            os.utime(path,None);self.stats['hits']+=1;self.stats['disk_hits']+=1
            self.remember(key,frame);self.trim();return frame
        except FileNotFoundError:self.stats['misses']+=1;return None
        except (OSError,ValueError,KeyError,TypeError,OverflowError,EOFError,zipfile.BadZipFile,zlib.error) as error:
            self.stats['last_invalid_reason']=str(error)
            self.stats['invalid']+=1;self.stats['misses']+=1;return None
    def put(self,args,frame):
        import hashlib
        import zipfile
        from build_trace import checkpoint
        checkpoint()
        w,h=args[:2];key=self.key(args)
        raw=b''.join(struct.pack('!IQ',ord(frame[x,y][0]),frame[x,y][1]) for y in range(h) for x in range(w))
        wire=getattr(frame,'wireframe',{})
        data=dict(items=[[x,y,char,getattr(wire,'depth',{}).get((x,y),0)] for (x,y),char in wire.items()],
                  depth_range=getattr(wire,'depth_range',(0,1)),surface_depth=[list(wire.surface_depth[0]),*wire.surface_depth[1:]] if getattr(wire,'surface_depth',None) is not None else None,
                  starts=list(wire.starts) if getattr(wire,'starts',None) is not None else None,
                  bands=getattr(wire,'bands',None),contours=sorted(getattr(wire,'contours',())),accents=sorted(getattr(wire,'accents',())))
        meta=dict(key=key,identity=self.identity,size=[w,h],cells_sha256=hashlib.sha256(raw).hexdigest())
        fd,tmp=tempfile.mkstemp(prefix='.view-',dir=self.path);os.close(fd)
        try:
            with zipfile.ZipFile(tmp,'w',zipfile.ZIP_DEFLATED) as z:
                z.writestr('meta.json',json.dumps(meta,separators=(',',':')))
                z.writestr('cells.bin',raw);z.writestr('wire.json',json.dumps(data,separators=(',',':')))
            checkpoint()
            if Path(tmp).stat().st_size<=self.max_bytes:
                os.replace(tmp,self.path/(key+'.view'));self.stats['writes']+=1;self.trim()
                self.remember(key,frame)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    def remember(self,key,frame):
        wire=getattr(frame,'wireframe',{})
        # Conservative per-entry budget; the existing engine may share these
        # same immutable objects in its own LRU. This is not process RSS.
        size=len(frame)*512+len(wire)*1024
        surface=getattr(wire,'surface_depth',None)
        if surface is not None:size+=len(surface[0])*8
        starts=getattr(wire,'starts',None)
        if starts is not None:size+=len(starts)*64
        limit=min(self.max_bytes,64*1024*1024)
        if size<=limit:self.hot[key]=(frame,size);self.hot.move_to_end(key)
        while len(self.hot)>min(2,self.max_entries) or sum(v[1] for v in self.hot.values())>limit:
            self.hot.popitem(last=False)
        self.stats.update(memory_entries=len(self.hot),memory_bytes_estimate=sum(v[1] for v in self.hot.values()))
    def trim(self):
        files=sorted(self.path.glob('*.view'),key=lambda p:p.stat().st_mtime_ns,reverse=True)
        total=0;kept=0
        for p in files:
            size=p.stat().st_size
            if kept>=self.max_entries or total+size>self.max_bytes:p.unlink();self.stats['evictions']+=1
            else:total+=size;kept+=1
        self.stats.update(entries=kept,bytes=total)


def install(backend='cpu',cache_dir=None):
    global _shader,_cache,_original_base,_fallbacks,_fallback_reason
    _fallbacks=0;_fallback_reason=None
    import model_scene
    if _original_base is None:_original_base=model_scene.base
    _original_base.cache_clear()
    if backend=='cpu':_shader=None
    elif backend in ('gpu','numpy'):
        from gpu_shading import Shader
        _shader=Shader(backend)
    else:raise ValueError('unknown scene backend')
    _cache=ViewCache(cache_dir,cache_identity(backend)) if cache_dir else None
    @functools.wraps(_original_base)
    def base(*args,**kwargs):
        if kwargs or _cache is None:return _original_base(*args,**kwargs)
        with _cache.lock:
            cached=_cache.get(args)
            if cached is not None:return cached
            frame=_original_base(*args)
            try:_cache.put(args,frame)
            except OSError:_cache.stats['write_errors']=_cache.stats.get('write_errors',0)+1
            return frame
    base.cache_clear=_original_base.cache_clear;base.cache_info=_original_base.cache_info
    model_scene.base=base
    return status()


def precache(keys):
    """Explicit bounded sequential warming; no new thread pool or timer."""
    if len(keys)>4:raise ValueError('at most four requested pre-cache views')
    import model_scene
    return [model_scene.base(*key) for key in keys]
