"""Existing Scene/set interfaces over bounded native scene and damage buffers."""
from collections.abc import Mapping,MutableSet
from functools import lru_cache
from paint import Scene

def indices(raw):
    view=memoryview(raw)
    return view if view.format=='I' else view.cast('I')

class Damage(MutableSet):
    def __init__(self,lib,size,values=()):
        self.lib,self.size=lib,size;self.handle=lib.damage_new(size);self.update(values)
    def __len__(self):return self.lib.damage_count(self.handle)
    def __iter__(self):return iter(self.take(self.size))
    def __contains__(self,index):
        return isinstance(index,int) and 0<=index<self.size and self.lib.damage_has(self.handle,index)
    def add(self,index):self.lib.damage_update(self.handle,(index,),True)
    def discard(self,index):
        if index in self:self.lib.damage_update(self.handle,(index,),False)
    def update(self,*values):
        for value in values:
            if isinstance(value,Damage) and value.lib is self.lib and value.size==self.size:self.lib.damage_merge(self.handle,value.handle,0)
            else:self.lib.damage_update(self.handle,value,True)
    def difference_update(self,*values):
        for value in values:
            if isinstance(value,Damage) and value.lib is self.lib and value.size==self.size:self.lib.damage_merge(self.handle,value.handle,2)
            else:self.lib.damage_update(self.handle,value,False)
    def intersection_update(self,other):
        if isinstance(other,Damage) and other.lib is self.lib and other.size==self.size:self.lib.damage_merge(self.handle,other.handle,1)
        else:self.difference_update(set(self)-set(other))
    def clear(self):self.lib.damage_rect(self.handle,self.size,0,0,self.size,1,False)
    def copy(self):return set(self)
    def mark(self,stride,x,y,width,height):self.lib.damage_rect(self.handle,stride,x,y,width,height)
    def bounds(self,stride):
        if hasattr(self.lib,'damage_bounds'):return self.lib.damage_bounds(self.handle,stride)
        if not stride or self.size%stride:raise ValueError('invalid damage stride')
        values=self.take(self.size)
        if not values:return (0,0,0,0)
        left=min(i%stride for i in values);right=max(i%stride for i in values)+1
        top=min(values)//stride;bottom=max(values)//stride+1
        return left,top,right-left,bottom-top
    def take(self,budget,priority=None):return indices(self.lib.damage_take(self.handle,budget,priority.handle if priority is not None else None))
    def intersects(self,values):return self.lib.damage_intersects(self.handle,values)
    @classmethod
    def _from_iterable(cls,values):return set(values)

class Plane(Mapping):
    def __init__(self,lib,pointer,width,height,order=None,factory=None):
        self.lib,self.pointer,self.width,self.height=lib,pointer,width,height
        self.order,self.factory=order,factory
    def __len__(self):return self.width*self.height if self.order is None else len(self.order)
    def __iter__(self):
        for index in range(self.width*self.height) if self.order is None else self.order:yield index%self.width,index//self.width
    def __getitem__(self,key):
        x,y=key
        if not isinstance(x,int) or not isinstance(y,int) or not 0<=x<self.width or not 0<=y<self.height:raise KeyError(key)
        index=y*self.width+x
        if self.order is not None and not self.lib.scene_has(self.pointer,index):raise KeyError(key)
        raw=self.lib.get(self.pointer,index)
        if raw is None:raise KeyError(key)
        value=chr(raw[0]),raw[1]
        return self.factory(*value) if self.factory else value

class NativeScene(Scene):
    native_glyphs=' ▄·+-/\\.'
    def __len__(self):
        # The native base covers the viewport. Job-size accounting must not
        # walk overlays and fetch individual native cells just to count it.
        return self.width*self.height
    def __init__(self,lib,base,pointer,width,height,factory=None):
        self.lib,self.native_surface,self.width,self.height=lib,pointer,width,height
        self.native_base=base
        order=indices(lib.scene_indices(pointer))
        super().__init__(Plane(lib,base,width,height,factory=factory),Plane(lib,pointer,width,height,order,factory))
    def as_cells(self,factory):return NativeScene(self.lib,self.native_base,self.native_surface,self.width,self.height,factory)
    def mark_changes(self,damage,previous):
        before=previous.native_surface if isinstance(previous,NativeScene) and previous.lib is self.lib else None
        self.lib.damage_diff(damage.handle,before,self.native_surface)

@lru_cache(maxsize=4)
def base_plane(lib,width,height,ascii):
    from build_trace import checkpoint
    return lib.nebula(width,height,ascii,checkpoint)

def flux(lib,width,height,step,ascii,density,glow,arms):
    from build_trace import checkpoint
    base=base_plane(lib,width,height,ascii)
    plane=lib.flux_surface(width,height,step,ascii,density,glow,arms,base,checkpoint)
    return NativeScene(lib,base,plane,width,height)
