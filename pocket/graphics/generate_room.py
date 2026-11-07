# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Canonical mesh and normals only. No projection, lighting or rasterization."""
from pathlib import Path
import sys,math,json,hashlib
p=Path(__file__).resolve().parent;r=p.parents[1]
output=Path(sys.argv[1]) if len(sys.argv)>1 else r/'pocket/build/graphics'
output.mkdir(parents=True,exist_ok=True)
sys.path[:0]=[str(r/'pocket/shell/apps/surface-renderer'),str(r/'pocket/shell')]
from room import fixture
from geometry import Vec
field,static,moving,env=fixture()
colors={'terrain':(56,81,67),'metal':(112,123,128),'fern':(45,82,47),'wood':(121,91,56)}
lines=['/* Generated from the actual Surface Room fixture, no mesh reduction. */','struct room_draw {unsigned first,count,moving; float color[4];};']
verts=[];draws=[];ids=[];triangle_offset=0
for mesh,ismoving in ((static,0),(moving,1)):
 sums=[[0.,0.,0.] for _ in mesh.vertices]
 for t in mesh.triangles:
  a,b,c=[mesh.vertices[i] for i in t[:3]];u=[b[i]-a[i] for i in range(3)];v=[c[i]-a[i] for i in range(3)]
  n=[u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
  if n[1]<0:n=[-x for x in n]
  for index in t[:3]:sums[index]=[x+y for x,y in zip(sums[index],n)]
 normals=[tuple(x/math.sqrt(sum(y*y for y in n)) for x in n) if sum(x*x for x in n)>1e-12 else (0.,1.,0.) for n in sums]
 for material in dict.fromkeys(t.material for t in mesh.triangles):
  ts=[t for t in mesh.triangles if t.material==material]
  for start in range(0,len(ts),256):
   batch=ts[start:start+256];first=len(verts)
   for t in batch:
    for i in t[:3]:
     verts.append((*mesh.vertices[i],*normals[i]));ids.append(triangle_offset+mesh.triangles.index(t)+1)
   draws.append((first,len(verts)-first,ismoving,colors[material]))
 triangle_offset+=len(mesh.triangles)
lines+=['static const float room_vertices[][6]={']+[ '{'+','.join(format(x,'.9g')+'f' if '.' in format(x,'.9g') or 'e' in format(x,'.9g') else format(x,'.9g')+'.0f' for x in v)+'},' for v in verts]+['};','static const struct room_draw room_draws[]={']
lines+=['{%d,%d,%d,{%s,1}},'%(a,b,c,','.join(format(x/255,'.9f')+'f' for x in color)) for a,b,c,color in draws]+['};']
lines+=['static const float room_ids[][3]={']+['{%.9ff,%.9ff,%.9ff},'%((((i>>11)&31)+.5)/32,(((i>>5)&63)+.5)/64,((i&31)+.5)/32) for i in ids]+['};']
(output/'room_mesh.h').write_text('\n'.join(lines)+'\n')
assert len(verts)//3==632
(output/'mesh-proof.json').write_text(json.dumps({'triangles':632,'vertices_emitted':len(verts),'draws':len(draws),'CPU_transform':False,'CPU_lighting':False,'CPU_raster':False,'source_sha256':hashlib.sha256((r/'pocket/shell/apps/surface-renderer/room.py').read_bytes()).hexdigest()},indent=2)+'\n')
