"""Keep host shader RGB arrays typed until sparse sky edits and RGB8 packing."""
from array import array
import operator
import time


def _rgb8(value):
    r,g,b=value
    return (max(0,min(255,int(r)))<<16)|(max(0,min(255,int(g)))<<8)|max(0,min(255,int(b)))


class Pixels:
    """List-compatible RGB reads/edits without allocating a tuple per sample.

    Shader values retain their original precision. Sparse celestial edits keep
    Python values separately, so a float64 moon color is never rounded to the
    shader's float32 storage before conversion to terminal RGB8.
    """
    __slots__=('values','np','edits','stats')

    def __init__(self,values,np,stats=None):
        if values.ndim!=2 or values.shape[1]!=3 or values.dtype.kind!='f':
            raise ValueError('shader RGB buffer must be a floating N by 3 array')
        self.values=values;self.np=np;self.edits={};self.stats=stats

    def __len__(self):return len(self.values)

    def _index(self,index):
        index=operator.index(index)
        if index<0:index+=len(self)
        if not 0<=index<len(self):raise IndexError('RGB sample index out of range')
        return index

    def __getitem__(self,index):
        if isinstance(index,slice):return [self[i] for i in range(*index.indices(len(self)))]
        index=self._index(index)
        if index in self.edits:return self.edits[index]
        return tuple(self.values[index].tolist())

    def __setitem__(self,index,value):
        index=self._index(index);value=tuple(value)
        if len(value)!=3:raise ValueError('RGB edit must have three components')
        self.edits[index]=value

    def __iter__(self):
        for index in range(len(self)):yield self[index]

    def packed_rgb(self):
        began=time.perf_counter();np=self.np
        # int(NaN) and int(infinity) reject invalid colors in the reference
        # path. Do not let a vector cast silently turn them into visible RGB.
        finite=np.isfinite(self.values).all(axis=1)
        values=self.values
        if not finite.all():
            invalid=~finite
            for index in self.edits:finite[index]=True
            if not finite.all():_rgb8(self[int(np.flatnonzero(~finite)[0])])
            values=values.copy();values[invalid]=0
        channels=np.clip(values,0,255).astype(np.uint32)
        packed=(channels[:,0]<<16)|(channels[:,1]<<8)|channels[:,2]
        result=array('I')
        if result.itemsize!=4:raise ValueError('RGB packing requires 32-bit unsigned int')
        result.frombytes(packed.astype(np.dtype('=u4'),copy=False).tobytes())
        for index,value in self.edits.items():result[index]=_rgb8(value)
        if self.stats is not None:
            self.stats['packing_seconds']+=time.perf_counter()-began
            self.stats['rgb_packed_frames']=self.stats.get('rgb_packed_frames',0)+1
            self.stats['rgb_packed_samples']=self.stats.get('rgb_packed_samples',0)+len(self)
            self.stats['rgb_overlay_samples']=self.stats.get('rgb_overlay_samples',0)+len(self.edits)
        return result
