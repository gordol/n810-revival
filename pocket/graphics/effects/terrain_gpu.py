# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Metal triangle coverage with canonical retained weights and explicit edge repair."""
from array import array
import threading,math

class CoverageGPU:
    def __init__(self):
        import mlx.core as mx
        import numpy as np
        if not mx.metal.is_available():raise RuntimeError('Metal terrain coverage unavailable')
        self.mx=mx;self.np=np;self.lock=threading.RLock()
        self.stats=dict(backend='Metal triangle coverage',frames=0,pixels=0,edge_repair_pixels=0,cpu_weight_samples=0,triangle_candidates=0)
        self.kernel=mx.fast.metal_kernel(name='pocket_terrain_coverage',input_names=['points','triangles','starts','candidates','shape'],output_names=['winner','uncertain'],source=r'''
uint i=thread_position_in_grid.x;
uint width=shape[0],height=shape[1];if(i>=width*height)return;
uint x=i%width,y=i/width,tile=(y/16)*shape[2]+x/16;
float px=float(x)+.5f,py=float(y)+.5f,best=INFINITY;uint win=0xffffffffu,risk=0;
for(uint j=starts[tile];j<starts[tile+1];j++){
 uint t=candidates[j];uint ia=triangles[3*t],ib=triangles[3*t+1],ic=triangles[3*t+2];
 float ax=points[3*ia],ay=points[3*ia+1],az=points[3*ia+2];
 float bx=points[3*ib],by=points[3*ib+1],bz=points[3*ib+2];
 float cx=points[3*ic],cy=points[3*ic+1],cz=points[3*ic+2];
 float area=(bx-ax)*(cy-ay)-(by-ay)*(cx-ax);if(abs(area)<1e-8f)continue;
 float a=((bx-px)*(cy-py)-(by-py)*(cx-px))/area;
 float b=((cx-px)*(ay-py)-(cy-py)*(ax-px))/area,c=1-a-b;
 float edge=min(a,min(b,c));if(abs(edge)<.0001f)risk=1;
 if(edge < -1e-8f)continue;
 float depth=shape[3]?1/(a/az+b/bz+c/cz):a*az+b*bz+c*cz;
 if(isfinite(best)&&abs(depth-best)<.0001f*max(1.f,abs(best)))risk=1;
 if(depth<best){best=depth;win=t;}
}
winner[i]=win;uncertain[i]=risk;
''')
    def coverage(self,mesh,projected,pw,ph,focal,depths,samples,triangle_type,checked,workspace=None):
        with self.lock:return self._coverage(mesh,projected,pw,ph,focal,depths,samples,checked)
    def _coverage(self,mesh,projected,pw,ph,focal,depths,samples,checked):
        mx,np=self.mx,self.np
        p=np.asarray(projected,dtype=np.float64).copy();p[:,0]*=pw;p[:,1]*=ph
        tris=np.asarray([t[:3] for t in checked(mesh.triangles,256)],dtype=np.uint32).reshape(-1,3)
        tw=(pw+15)//16;th=(ph+15)//16;bins=[[] for _ in range(tw*th)]
        for t,ids in enumerate(tris):
            v=p[ids];a,b,c=v
            area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(area)<1e-8:continue
            x0=max(0,math.floor(min(v[:,0])));x1=min(pw-1,math.ceil(max(v[:,0])))
            y0=max(0,math.floor(min(v[:,1])));y1=min(ph-1,math.ceil(max(v[:,1])))
            if x0>x1 or y0>y1:continue
            for yy in range(y0//16,y1//16+1):
                for xx in range(x0//16,x1//16+1):bins[yy*tw+xx].append(t)
        starts=[0];flat=[]
        for row in bins:flat.extend(row);starts.append(len(flat))
        with mx.stream(mx.gpu):
            out=self.kernel(inputs=[mx.array(p.astype(np.float32)),mx.array(tris),mx.array(starts,dtype=mx.uint32),mx.array(flat or [0],dtype=mx.uint32),mx.array([pw,ph,tw,int(bool(focal))],dtype=mx.uint32)],grid=(pw*ph,1,1),threadgroup=(256,1,1),output_shapes=[(pw*ph,),(pw*ph,)],output_dtypes=[mx.uint32,mx.uint32])
            mx.eval(out);winner=np.array(out[0]);risk=np.array(out[1])
        # Canonical double arithmetic supplies retained float32 weights for each winner.
        visible=np.flatnonzero(winner!=0xffffffff);chosen=tris[winner[visible]]
        a,b,c=(p[chosen[:,j]] for j in range(3));px=visible%pw+.5;py=visible//pw+.5
        area=(b[:,0]-a[:,0])*(c[:,1]-a[:,1])-(b[:,1]-a[:,1])*(c[:,0]-a[:,0])
        w1=((b[:,0]-px)*(c[:,1]-py)-(b[:,1]-py)*(c[:,0]-px))/area
        w2=((c[:,0]-px)*(a[:,1]-py)-(c[:,1]-py)*(a[:,0]-px))/area;w3=1-w1-w2
        if focal:
            d=1/(w1/a[:,2]+w2/b[:,2]+w3/c[:,2]);w1=w1*d/a[:,2];w2=w2*d/b[:,2]
        else:d=w1*a[:,2]+w2*b[:,2]+w3*c[:,2]
        target_ids=np.frombuffer(samples.ids,dtype=np.uint32).reshape(-1,3);weights=np.frombuffer(samples.weights,dtype=np.float32).reshape(-1,2);z=np.frombuffer(depths,dtype=np.float32)
        target_ids[visible]=chosen;weights[visible,0]=w1;weights[visible,1]=w2;z[visible]=d
        for i in np.flatnonzero(risk):
            x,y=int(i%pw),int(i//pw);px,py=x+.5,y+.5;best=math.inf;hit=None
            for t in bins[(y//16)*tw+x//16]:
                ids=tris[t];a,b,c=p[ids];area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
                u=((b[0]-px)*(c[1]-py)-(b[1]-py)*(c[0]-px))/area;v=((c[0]-px)*(a[1]-py)-(c[1]-py)*(a[0]-px))/area;q=1-u-v
                if min(u,v,q)<-1e-8:continue
                depth=1/(u/a[2]+v/b[2]+q/c[2]) if focal else u*a[2]+v*b[2]+q*c[2]
                if depth<best:
                    best=float(np.float32(depth));hit=(ids,u*depth/a[2] if focal else u,v*depth/b[2] if focal else v)
            if hit is None:target_ids[i]=0xffffffff;weights[i]=0;z[i]=math.inf
            else:target_ids[i]=hit[0];weights[i]=hit[1:];z[i]=best
        self.stats['frames']+=1;self.stats['pixels']+=pw*ph;self.stats['edge_repair_pixels']+=int(np.count_nonzero(risk));self.stats['cpu_weight_samples']+=len(visible);self.stats['triangle_candidates']+=len(flat)
        return True
