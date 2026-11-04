"""Fixed world stands and seasonal deciduous groves around frozen Lab art.

Illustrative forest composition, not a species distribution dataset. No camera-
following placement, new renderer, flower/wildlife changes, or production hook.
"""
from dataclasses import replace
from functools import lru_cache
from pathlib import Path
import hashlib,importlib.util,math

MAX_REPLACED_OWNERS=512
MAX_OVERLAY_CELLS=32768
MAX_GLYPHS=2304
MAX_ADDED_TRIANGLES=64000
PINS={'seasonal_foreground.py':'1a56b771f0d4de5d37a83bca89eeaf1de14f16a9739f82451d7ae87fa724e03a',
      'static_foreground.py':'cb0dc7750455e77da067f909352eed0d0ce9080e107e0617faef7fc7462e514a'}
# Fixed world zones: sparse groves between overlapping near/middle/far stands.
DECIDUOUS=((-1550.,23270.,70.),(-1050.,22600.,70.),(-710.,22120.,65.))
EVERGREEN=((-1702.,23391.,105.),(-1230.,24455.,75.),(-567.,27560.,220.),(-1480.,22100.,65.))


@lru_cache(maxsize=1)
def seasonal():
    directory=Path(__file__).with_name('frozen')
    for name,sha in PINS.items():
        if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=sha:raise ValueError('forest art dependency changed: '+name)
    spec=importlib.util.spec_from_file_location('_mixed_seasonal',directory/'seasonal_foreground.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def leaf_mass(origin,radius,height,owner,seed,index):
    from geometry import Vec,Mesh,Triangle
    f=seasonal().baseline();vertices=[Vec(origin.x,origin.y-height,origin.z)];faces=[]
    turn=f.random(seed,index+700)*math.tau
    for ring,phi in enumerate((math.pi*.25,math.pi*.5,math.pi*.75)):
        for j in range(8):
            a=turn+j*math.tau/8;r=radius*math.sin(phi)*(.85+.25*f.random(seed,index*31+j))
            vertices.append(Vec(origin.x+math.cos(a)*r,origin.y-math.cos(phi)*height,origin.z+math.sin(a)*r*.88))
    top=len(vertices);vertices.append(Vec(origin.x,origin.y+height,origin.z))
    for j in range(8):
        k=(j+1)%8;faces.append(Triangle(0,1+k,1+j,'fern',owner));faces.append(Triangle(17+j,17+k,top,'fern',owner))
        for ring in range(2):
            a=1+ring*8+j;b=1+ring*8+k;c=a+8;d=b+8
            faces.extend((Triangle(a,b,c,'fern',owner),Triangle(b,d,c,'fern',owner)))
    return Mesh(tuple(vertices),tuple(faces))


def tree_form(root,h,angle,identity,seed):
    """Persistent tapering leader, rising limbs and fine forks; same in leaf-off."""
    from geometry import Vec
    f=seasonal().baseline();x,y,z=root
    leanx=(f.random(seed,identity+44)-.5)*h*.07
    leanz=(f.random(seed,identity+45)-.5)*h*.07
    def spine(t):return Vec(x+leanx*t,y+h*t,z+leanz*t)
    segments=[(spine(0),spine(.48),h*.032,'trunk'),(spine(.48),spine(.76),h*.023,'trunk'),(spine(.76),spine(1),h*.012,'leader')]
    leaves=[]
    for branch in range(5):
        a=angle+branch*2.399963
        spread=h*(.20-.022*branch)*(.86+.24*f.random(seed,identity+branch+81))
        start=spine(.46+branch*.075)
        tip=Vec(x+math.cos(a)*spread+leanx*.8,y+h*(.62+branch*.074),z+math.sin(a)*spread+leanz*.8)
        segments.append((start,tip,h*(.011-branch*.0012),'limb'))
        for fork in (-1,1):
            angle2=a+fork*.65
            end=Vec(tip.x+math.cos(angle2)*h*.075,tip.y+h*(.075+.02*f.random(seed,identity+branch)),tip.z+math.sin(angle2)*h*.075)
            segments.append((tip,end,h*.0035,'twig'))
            leaves.append((end,branch,fork))
    return segments,leaves


def build(model,seed=12345,season='summer'):
    if season not in ('spring','summer','autumn','winter'):raise ValueError('unsupported forest season')
    s=seasonal();organic,meta=s.build(model,seed,season)
    from geometry import Vec,Mesh,merge
    from landscape_detail import beam
    f=s.baseline()
    # Open areas for real deciduous populations, removing only named old conifers.
    groups={}
    for t in model.mesh.triangles:
        if t.material in ('fir','cedar','tree') and t.owner.startswith(('tree:','grove:','woodland:')):
            groups.setdefault(t.owner,set()).update(t[:3])
    removed=set()
    for owner,ids in groups.items():
        vs=[model.mesh.vertices[i] for i in ids]
        x=(min(p.x for p in vs)+max(p.x for p in vs))/2;z=(min(p.z for p in vs)+max(p.z for p in vs))/2
        if any(((x-cx)/(r*1.12))**2+((z-cz)/(r*.70))**2<1 for cx,cz,r in DECIDUOUS):removed.add(owner)
    replaced=set(meta.get('replaced_tree_owners',()))|removed
    if len(replaced)>MAX_REPLACED_OWNERS:raise ValueError('forest replacement budget')
    kept=Mesh(organic.mesh.vertices,tuple(t for t in organic.mesh.triangles if t.owner not in removed))
    parts=[kept];anchors=[];records=[]
    for family,zones,count in (('evergreen',EVERGREEN,12),('deciduous',DECIDUOUS,12)):
        for grove,(cx,cz,radius) in enumerate(zones):
            for index in range(count):
                identity=(10000 if family=='evergreen' else 20000)+grove*100+index
                a=index*2.399963+f.random(seed,grove+91)*math.tau
                rr=radius*math.sqrt(.10+.85*f.random(seed,identity))
                x=cx+math.cos(a)*rr;z=cz+math.sin(a)*rr*.60
                y=f.surface(model.terrain,x,z);owner=f'mixed:{family}:{grove}:{index}'
                anchors.append((owner,x,z));h=(36+f.random(seed,identity+1)*24) if family=='evergreen' else (32+f.random(seed,identity+1)*14)
                if family=='evergreen':
                    parts.append(beam(Vec(x,y,z),Vec(x,y+h*.82,z),max(.3,h*.012),'wood',owner))
                    kind='cedar' if grove%2 and index%3==0 else 'fir'
                    for tier,(lift,scale) in enumerate(((.12,1.),(.39,.74),(.64,.43))):
                        parts.append(f.crown(Vec(x,y+h*lift,z),h*.26*scale,h*scale*.67,kind,owner,seed,identity+tier))
                else:
                    segments,leaves=tree_form(Vec(x,y,z),h,a,identity,seed)
                    for start,end,width,role in segments:
                        parts.append(beam(start,end,max(.11,width),'wood',owner))
                    fullness={'spring':.62,'summer':1.,'autumn':.62,'winter':0.}[season]
                    if fullness:
                        for leaf,(end,branch,fork) in enumerate(leaves):
                            if season=='autumn' and (index+branch+fork)%3==0:continue
                            width=h*(.115+.025*f.random(seed,identity+leaf+121))*fullness
                            rise=h*(.12+.025*f.random(seed,identity+leaf+131))*fullness
                            parts.append(leaf_mass(end,width,rise,owner,seed,identity+leaf))
                records.append(dict(owner=owner,family=family,grove=grove,root=(x,y,z),height=h))
    result=replace(organic,mesh=merge(parts));added=len(result.mesh.triangles)-len(model.mesh.triangles)
    if added>MAX_ADDED_TRIANGLES:raise ValueError('forest geometry budget')
    info=dict(meta,season=season,replaced_tree_owners=sorted(replaced),removed_original_tree_owners=sorted(removed),
        mixed_forest=records,mixed_anchor_sha256=hashlib.sha256(repr(anchors).encode()).hexdigest(),
        grove_zones=dict(evergreen=EVERGREEN,deciduous=DECIDUOUS),added_triangles=added,
        added_vertices=len(result.mesh.vertices)-len(model.mesh.vertices),
        forest_note='Fixed illustrative world groves; clustered evergreen depth layers and selected deciduous areas. No mapped species claim.')
    return result,info


def overlay(model,coverage,cells,width,height,seed=12345,season='summer',snow=False):
    s=seasonal();result=s.overlay(model,coverage,cells,width,height,seed,season)
    from vegetation import noise
    mesh,normals,materials,samples,depths,_,pw,ph,*_=coverage
    owners=['']*len(mesh.vertices)
    for t in mesh.triangles:
        if t.owner.startswith('mixed:deciduous:'):
            for i in t[:3]:owners[i]=t.owner
    text=sum(ch not in ('▄','▀',' ') for ch,_ in result.values());seen=set()
    for y in range(height):
        for x in range(width):
            xx=min(pw-1,int((x+.5)*pw/width));ids=[min(ph-1,int((y+fy)*ph/height))*pw+xx for fy in (.25,.75)]
            pair=[samples[i] for i in ids]
            if any(p is None for p in pair):continue
            owner=owners[pair[0][0]]
            if not owner or owners[pair[1][0]]!=owner or any(materials[p[0]]!='fern' for p in pair):continue
            if abs(depths[ids[0]]-depths[ids[1]])>max(35,min(depths[i] for i in ids)*.04):continue
            original,style=cells[x,y]
            if original not in ('▄','▀'):continue
            upper,lower=(style&0xffffff,style>>24&0xffffff) if original=='▄' else (style>>24&0xffffff,style&0xffffff)
            a,b,c,wa,wb,wc=pair[1];px,py,pz=(mesh.vertices[a][j]*wa+mesh.vertices[b][j]*wb+mesh.vertices[c][j]*wc for j in range(3))
            mass=noise(px+py*.4,pz,9);grove=int(owner.split(':')[2])
            target=(91,134,65) if season=='spring' else (49,99,52) if season=='summer' else ((173,126,45),(151,81,39),(143,105,43))[grove]
            def color(value):
                rgb=s.rgb(value);exposure=max(.18,min(1.15,sum(rgb)/174));rough=.88+.23*mass
                return tuple(max(0,min(255,round(t*exposure*rough))) for t in target)
            up,lo=color(upper),color(lower);ch='▄';ink=(1<<48)|(s.pack(lo)<<24)|s.pack(up)
            anchor=(owner,math.floor(px/6),math.floor(py/4),math.floor(pz/6))
            identity=int.from_bytes(hashlib.sha256(repr(anchor).encode()).digest()[:4],'big')
            if anchor not in seen and text<MAX_GLYPHS and identity%5!=0:
                seen.add(anchor);text+=1;ch=(".,;'" if season!='autumn' else ",;/'")[identity%4]
                base=tuple((u+l)/2 for u,l in zip(up,lo));fg=tuple(v*(1.3 if mass>.45 else .60) for v in base)
                ink=(1<<48)|(s.pack(fg)<<24)|s.pack(base)
            elif (x,y) in result and result[x,y][0] not in ('▄','▀',' '):text-=1
            if len(result)<MAX_OVERLAY_CELLS or (x,y) in result:result[x,y]=ch,ink
    return finish_structure(model,coverage,cells,result,width,height,seed,season,snow)


def snow_surfaces(model,coverage,cells,result,width,height):
    """Static snow resting on upward-facing surfaces, not weather simulation."""
    s=seasonal();f=s.baseline()
    mesh,normals,materials,samples,depths,_,pw,ph,*_=coverage
    for y in range(height):
      for x in range(width):
        xx=min(pw-1,int((x+.5)*pw/width));ids=[min(ph-1,int((y+fy)*ph/height))*pw+xx for fy in (.25,.75)]
        pair=[samples[i] for i in ids]
        if any(p is None for p in pair):continue
        kinds=[materials[p[0]] for p in pair]
        if kinds[0]!=kinds[1] or kinds[0] not in ('terrain','fir','cedar','tree','wood'):continue
        if min(depths[i] for i in ids)>=11000 and (x,y) not in result:continue
        # Ground snow starts from the actual winter-lit base, not selected green art patches.
        base=cells[x,y] if kinds[0]=='terrain' else result.get((x,y),cells[x,y])
        ch,style=base
        up,lo=(style&0xffffff,style>>24&0xffffff) if ch=='▄' else (style>>24&0xffffff,style&0xffffff)
        values=[]
        for hit,value in zip(pair,(up,lo)):
            a,b,c,wa,wb,wc=hit
            ny=normals[a].y*wa+normals[b].y*wb+normals[c].y*wc
            fade=max(0,min(1,(11000-max(depths[i] for i in ids))/3500))
            amount=f.smooth(.10,.70,ny)*(.76 if kinds[0]=='terrain' else .65)*fade
            rgb=s.rgb(value);den=380 if kinds[0]=='terrain' else 174 if kinds[0] in ('fir','cedar','tree') else 268
            exposure=max(.28,min(.95,sum(rgb)/den))
            values.append(s.pack(tuple(v*(1-amount)+t*exposure*amount for v,t in zip(rgb,(216,225,230)))))
        if ch=='▄':style=(1<<48)|(values[1]<<24)|values[0]
        else:style=(1<<48)|(values[0]<<24)|values[1]
        if len(result)<MAX_OVERLAY_CELLS or (x,y) in result:result[x,y]=ch,style
    return result


def finish_structure(model,coverage,cells,result,width,height,seed,season,snow):
    """Subcell trunk/limb features use existing line clipping and raster depth."""
    from geometry import Vec
    from loading import clip_line
    s=seasonal();f=s.baseline()
    if snow:result=snow_surfaces(model,coverage,cells,result,width,height)
    _,_,materials,samples,depths,_,pw,ph,*_=coverage
    text=sum(ch not in ('▄','▀',' ') for ch,_ in result.values());drawn={}
    for grove,(cx,cz,radius) in enumerate(DECIDUOUS):
        for index in range(12):
            identity=20000+grove*100+index
            angle=index*2.399963+f.random(seed,grove+91)*math.tau
            rr=radius*math.sqrt(.10+.85*f.random(seed,identity))
            x=cx+math.cos(angle)*rr;z=cz+math.sin(angle)*rr*.60;y=f.surface(model.terrain,x,z)
            h=32+f.random(seed,identity+1)*14
            segments,_=tree_form(Vec(x,y,z),h,angle,identity,seed)
            for start,end,thickness,role in segments:
                a,b=model.camera.project(start),model.camera.project(end)
                if min(a[2],b[2])<100:continue
                ax,ay,bx,by=a[0]*width,a[1]*height,b[0]*width,b[1]*height
                clipped=clip_line(ax,ay,bx,by,width,height)
                if clipped is None:continue
                x0,y0,x1,y1=clipped;dx,dy=x1-x0,y1-y0
                steps=max(1,min(32,round(max(abs(dx),abs(dy)))))
                char='|' if abs(dy)>abs(dx)*1.7 else '_' if abs(dx)>abs(dy)*2.5 else '\\' if dx*dy>0 else '/'
                horizontal=abs(end.y-start.y)<math.hypot(end.x-start.x,end.z-start.z)*.95
                for step in range(steps+1):
                    xx,yy=round(x0+dx*step/steps),round(y0+dy*step/steps)
                    if not (0<=xx<width and 0<=yy<height):continue
                    t=((xx-ax)/(bx-ax)) if abs(bx-ax)>abs(by-ay) else ((yy-ay)/(by-ay)) if by!=ay else 0
                    t=max(0,min(1,t));depth=1/((1-t)/a[2]+t/b[2])
                    pixel=min(ph-1,int((yy+.5)*ph/height))*pw+min(pw-1,int((xx+.5)*pw/width))
                    if depth>depths[pixel]+max(2,depth*.001):continue
                    if drawn.get((xx,yy),math.inf)<depth:continue
                    hit=samples[pixel]
                    if hit is not None and materials[hit[0]]=='fern' and depths[pixel]<depth+2:continue
                    old=result.get((xx,yy),cells[xx,yy]);is_text=old[0] not in ('▄','▀',' ')
                    if not is_text and text>=MAX_GLYPHS:continue
                    if (xx,yy) not in result and len(result)>=MAX_OVERLAY_CELLS:continue
                    style=old[1];back=tuple(((style>>sh&255)+(style>>(sh+24)&255))/2 for sh in (16,8,0))
                    distance=max(.35,1-depth/14000)
                    tone=(189,199,201) if snow and horizontal and role!='trunk' else (108,111,101)
                    foreground=tuple(v*distance for v in tone)
                    result[xx,yy]=(char,(1<<48)|(s.pack(foreground)<<24)|s.pack(back))
                    text+=not is_text;drawn[xx,yy]=depth
    return result
