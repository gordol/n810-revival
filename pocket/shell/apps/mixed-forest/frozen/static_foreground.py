"""Static world-anchored foreground for the isolated medium-terrain comparison.

Call build before preparing coverage, then overlay once on completed cells.
Caller owns source pinning, model/coverage identity and lighting. No engine import
path changes, rendering, terrain generation, caches, clocks or animal state here.
"""
from dataclasses import replace
import hashlib,math

MAX_OVERLAY_CELLS=8192
MAX_GLYPHS=1280
MAX_GROUND_GLYPHS=512
MAX_FORM_GLYPHS=768


def random(seed,index):
    n=(seed ^ (index*0x9e3779b9))&0xffffffff
    n=((n^(n>>16))*0x45d9f3b)&0xffffffff
    return ((n^(n>>16))&0xffffffff)/4294967296


def cover(x,z,seed):
    from vegetation import noise
    warp=(noise(x,z,450)-.5)*180
    return noise(x+warp+seed%4096,z-warp*.3,230)


def crown(origin,radius,height,material,owner,seed,index):
    """Asymmetric six-branch crown skirts; dimensions remain world metres."""
    from geometry import Vec,Mesh,Triangle
    profile=((0,.50),(.18,1),(.52,.56),(1,.04)) if material=='fir' else ((0,.40),(.24,.94),(.60,1),(1,.08))
    vertices=[];faces=[];turn=random(seed,index+7000)*math.tau
    for ring,(lift,spread) in enumerate(profile):
        for j in range(6):
            angle=turn+j*math.tau/6
            # Persistent branch lengths make an uneven, open-edged silhouette.
            branch=.70+.45*random(seed,index*47+j+20000)
            r=radius*spread*branch
            vertices.append(Vec(origin.x+math.cos(angle)*r+height*lift*.035,origin.y+height*lift,origin.z+math.sin(angle)*r))
    for ring in range(3):
        for j in range(6):
            a=ring*6+j;b=ring*6+(j+1)%6;c=a+6;d=b+6
            faces.extend((Triangle(a,b,c,material,owner),Triangle(b,d,c,material,owner)))
    return Mesh(tuple(vertices),tuple(faces))


def smooth(a,b,x):
    t=max(0,min(1,(x-a)/(b-a)))
    return t*t*(3-2*t)


def branch_masses(model,seed):
    """Replace twelve near crown envelopes with bounded irregular branch clusters."""
    from geometry import Vec,Mesh
    groups={}
    for tri in model.mesh.triangles:
        if tri.material in ('fir','cedar','tree') and tri.owner.startswith(('tree:','grove:','woodland:')):
            group=groups.setdefault(tri.owner,[set(),tri.material]);group[0].update(tri[:3])
    eligible=[]
    for owner,(indexes,material) in groups.items():
        vertices=[model.mesh.vertices[i] for i in indexes]
        low=Vec(*(min(p[j] for p in vertices) for j in range(3)))
        high=Vec(*(max(p[j] for p in vertices) for j in range(3)))
        x,z=(low.x+high.x)/2,(low.z+high.z)/2
        u,top,depth=model.camera.project(Vec(x,high.y,z))
        _,bottom,_=model.camera.project(Vec(x,low.y,z))
        if depth<=100 or depth>7500 or not (-.02<u<1.02 and top<1 and bottom>0):continue
        if bottom-top<.012:continue
        eligible.append((bottom-top,owner,material,low,high))
    from landscape_detail import beam
    parts=[];records=[]
    for _,owner,material,low,high in sorted(eligible,key=lambda p:(-p[0],p[1]))[:12]:
        identity=int.from_bytes(hashlib.sha256(owner.encode()).digest()[:4],'big')
        kind=material if material in ('fir','cedar') else ('cedar' if identity%3==0 else 'fir')
        x,z=(low.x+high.x)/2,(low.z+high.z)/2
        low=Vec(low.x,min(low.y,surface(model.terrain,x,z)),low.z)
        radius=min(high.x-low.x,high.z-low.z)/2;height=high.y-low.y
        parts.append(beam(Vec(x,low.y,z),Vec(x,low.y+height*.89,z),max(.45,radius*.075),'wood',owner))
        tiers=7 if kind=='fir' else 6;limbs=2 if kind=='fir' else 3
        turn=random(seed,identity)*math.tau
        for level in range(tiers):
            t=.13+level/(tiers-1)*.78
            spread=radius*(1-t)**(.64 if kind=='fir' else .44)
            y=low.y+height*t
            # Overlapping central foliage joins the branch clusters around the spine.
            core=crown(Vec(x,y-height*.065,z),spread*.82,height*.23,kind,owner,seed,identity+level*53)
            vertices=tuple(Vec(*(max(low[k],min(high[k],p[k])) for k in range(3))) for p in core.vertices)
            parts.append(Mesh(vertices,core.triangles))
            for j in range(limbs):
                angle=turn+level*2.39996+j*math.tau/limbs
                length=spread*(.62+.22*random(seed,identity+level*9+j))
                end=Vec(x+math.cos(angle)*length,y-height*.025,z+math.sin(angle)*length)
                parts.append(beam(Vec(x,y,z),end,max(.25,radius*.035),'wood',owner))
                rise=height*(.18 if kind=='fir' else .20)
                origin=Vec(end.x,end.y-rise*.3,end.z)
                mesh=crown(origin,spread*.53,rise,kind,owner,seed,identity+level*7+j)
                vertices=tuple(Vec(*(max(low[k],min(high[k],p[k])) for k in range(3))) for p in mesh.vertices)
                parts.append(Mesh(vertices,mesh.triangles))
        records.append(dict(owner=owner,kind=kind,low=low,high=high))
    return parts,records


def surface(field,x,z):
    field.height(x,z)
    fx=(x-field.origin.x)/field.dx;fz=(z-field.origin.z)/field.dz
    ix=min(field.nx-2,int(fx));iz=min(field.nz-2,int(fz));u=fx-ix;v=fz-iz
    a,b,c,d=(field.values[j*field.nx+i] for i,j in ((ix,iz),(ix+1,iz),(ix,iz+1),(ix+1,iz+1)))
    return a+(b-a)*u+(c-a)*v if u+v<=1 else d+(c-d)*(1-u)+(b-d)*(1-v)


def boulder(origin,radius,height,owner,seed,index):
    """An irregular embedded stone with rounded shoulders and a sloped cap."""
    from geometry import Vec,Mesh,Triangle
    vertices=[];faces=[]
    for ring,(lift,spread) in enumerate(((-.12,.72),(.35,1),(.83,.62))):
        for j in range(6):
            a=j*math.tau/6+.11*ring
            r=radius*spread*(.82+.18*random(seed,index*31+j))
            vertices.append(Vec(origin.x+math.cos(a)*r,origin.y+height*lift,origin.z+math.sin(a)*r))
    vertices.append(Vec(origin.x-radius*.14,origin.y+height,origin.z+radius*.1))
    for ring in range(2):
        for j in range(6):
            a=ring*6+j;b=ring*6+(j+1)%6
            faces.extend((Triangle(a,b,a+6,'metal',owner),Triangle(b,b+6,a+6,'metal',owner)))
    for j in range(6):faces.append(Triangle(12+j,12+(j+1)%6,18,'metal',owner))
    return Mesh(tuple(vertices),tuple(faces))


def build(model,seed=12345):
    """Return model + bounded added instances; preserve terrain/camera identity."""
    from geometry import Vec,cone,merge
    from landscape_detail import box
    from vegetation import noise
    field=model.terrain;parts=[model.mesh];anchors=[]
    counts={'fir':0,'cedar':0,'shrub':0,'rock':0}
    # Fixed Rainier study world region; candidate coordinates never follow camera.
    for i in range(384):
        x=-4800+random(seed,i*3)*8800
        z=21350+random(seed,i*3+1)*6300
        try:
            y=surface(field,x,z)
            sx=(field.height(x+8,z)-field.height(x-8,z))/16
            sz=(field.height(x,z+8)-field.height(x,z-8))/16
        except ValueError:continue
        slope=math.hypot(sx,sz);patch=noise(x+seed%4096,z,520)
        if y>2000 or slope>.85:continue
        # Ecotone patches leave deterministic clearings between stands.
        kind='rock' if slope>.5 else 'shrub' if patch<.30 else ('cedar' if i%3==0 else 'fir') if patch>.53 else None
        if kind is None:continue
        cap=24 if kind=='rock' else 48 if kind=='shrub' else 32
        if counts[kind]>=cap:continue
        r=random(seed,i*3+2);owner=f'lab-foreground:{kind}:{i}'
        p=Vec(x,y,z);anchors.append((owner,x,z));counts[kind]+=1
        if kind in ('fir','cedar'):
            h=16+r*26;radius=h*((.21+.05*r) if kind=='fir' else (.29+.05*r))
            parts.append(box(Vec(x-.5,y,z-.5),1,h*.48,1,'wood',owner))
            tiers=((.14,1),(.42,.70),(.68,.38)) if kind=='fir' else ((.20,1),(.52,.77))
            for level,(lift,scale) in enumerate(tiers):
                parts.append(crown(Vec(x,y+h*lift,z),radius*scale,h*scale*.68,kind,owner,seed,i*3+level))
        elif kind=='shrub':
            # Low clusters retain metre-scale size; glyph texture carries masses.
            for j in range(3):
                dx=(j-1)*1.5;zz=z+(j%2)*1.2
                base=surface(field,x+dx,zz)
                parts.append(cone(Vec(x+dx,base,zz),1.8+r*2.1,1.1+r*1.7,'fern',owner))
        else:
            parts.append(boulder(p,1.8+r*4,1.4+r*3.8,owner,seed,i))
    branches,decorated=branch_masses(model,seed)
    replaced={r['owner'] for r in decorated}
    from geometry import Mesh
    parts[0]=Mesh(model.mesh.vertices,tuple(t for t in model.mesh.triangles if t.owner not in replaced))
    parts.extend(branches)
    mesh=merge(parts)
    meta=dict(replaced_tree_owners=sorted(replaced),decorated_trees=decorated,seed=seed,candidate_budget=384,added_counts=counts,added_triangles=len(mesh.triangles)-len(model.mesh.triangles),added_vertices=len(mesh.vertices)-len(model.mesh.vertices),anchor_xz_sha256=hashlib.sha256(repr(anchors).encode()).hexdigest(),anchor_xz=anchors,region_m=dict(x=(-4800,4000),z=(21350,27650)),note='World-coordinate candidates and IDs fixed across camera/quality. Heights reseat on visible DEM mesh; actual visible admission depends on coverage. Terrain/camera and all unselected inherited geometry remain unchanged; selected tree owner envelopes are replaced within stable bounds. Tree crowns illustrative; meadow/shrub tones are aggregate surface texture, not enlarged individual blades.')
    return replace(model,mesh=mesh),meta


def tones(model,coverage,cells,width,height,seed=12345):
    """Bounded coherent terrain-tone cells, preserving half-cell lighting."""
    if not (1<=width<=510 and 1<=height<=118):raise ValueError('Static foreground viewport budget exceeded')
    from vegetation import noise
    mesh,normals,materials,samples,depths,_,pw,ph,*_=coverage
    candidates=[]
    def tone(sample,source):
        a,b,c,wa,wb,wc=sample
        px,py,pz=(mesh.vertices[a][j]*wa+mesh.vertices[b][j]*wb+mesh.vertices[c][j]*wc for j in range(3))
        ny=normals[a].y*wa+normals[b].y*wb+normals[c].y*wc
        mass=cover(px,pz,seed)
        fine=noise(px,pz,18)
        # Each half-cell keeps its own shaded source color and surface sample.
        rgb=tuple((source>>s)&255 for s in (16,8,0))
        illumination=max(.30,min(1.12,sum(rgb)/180))
        rock=(1-smooth(.60,.82,ny))*smooth(.50,.76,noise(px+seed%8192,pz,90))
        if mass<.36:
            target=(35,73,54);amount=.32+(.36-mass)*1.1
        elif mass>.54:
            target=(96,119,60);amount=.28+(mass-.54)*.75
        else:
            target=(100,89,65);amount=.20
        # Rock exposure blends softly into the surrounding cover, not a cliff-wide band.
        rock_amount=rock*.70
        target=tuple(t*(1-rock_amount)+r*rock_amount for t,r in zip(target,(108,110,100)))
        amount=max(amount,rock_amount)
        roughness=.86+.28*fine
        # Material masses inherit source exposure, local slope and fine roughness.
        color=tuple(max(0,min(255,round((v*(1-amount)+t*illumination*amount)*roughness))) for v,t in zip(rgb,target))
        weight=amount
        packed=(color[0]<<16)|(color[1]<<8)|color[2]
        return packed,weight,py
    for y in range(height):
        for x in range(width):
            xx=min(pw-1,int((x+.5)*pw/width))
            indexes=[min(ph-1,int((y+fy)*ph/height))*pw+xx for fy in (.25,.75)]
            ss=[samples[index] for index in indexes]
            if any(s is None or materials[s[0]]!='terrain' for s in ss):continue
            far=max(depths[index] for index in indexes)
            if far>7500:continue
            if abs(depths[indexes[0]]-depths[indexes[1]])>max(120,depths[indexes[0]]*.08):continue
            ch,under=cells[x,y]
            if ch not in ('▄','▀'):continue
            lower,upper=(under>>24&0xffffff,under&0xffffff) if ch=='▄' else (under&0xffffff,under>>24&0xffffff)
            top,wt,yt= tone(ss[0],upper)
            bottom,wb,yb=tone(ss[1],lower)
            if max(yt,yb)>2050:continue
            strength=max(wt,wb)*max(0,min(1,(9000-far)/4500))
            if strength<.025:continue
            # Strongest organic patches receive the bounded budget, not tile rows.
            value=('▄',(1<<48)|(bottom<<24)|top)
            candidates.append((strength,x,y,value))
    return {(x,y):value for _,x,y,value in sorted(candidates,key=lambda p:(-p[0],p[2],p[1]))[:6144]}


def glyphs(model,coverage,tonal,width,height,seed=12345):
    """Sparse near-surface accents, one jittered world anchor per cover tile."""
    from geometry import Vec
    from vegetation import noise
    mesh,normals,materials,samples,depths,_,pw,ph,*_=coverage
    sites={}
    for x,y in tonal:
        ix=min(pw-1,int((x+.5)*pw/width));iy=min(ph-1,int((y+.75)*ph/height))
        sample=samples[iy*pw+ix]
        if sample is None:continue
        a,b,c,wa,wb,wc=sample
        px,pz=(mesh.vertices[a][j]*wa+mesh.vertices[b][j]*wb+mesh.vertices[c][j]*wc for j in (0,2))
        qx,qz=math.floor(px/18),math.floor(pz/18)
        identity=qx*73856093 ^ qz*19349663
        if identity in sites:continue
        chance=random(seed,identity)
        if chance>.85:continue
        ax=(qx+.12+.76*random(seed,identity+1))*18
        az=(qz+.12+.76*random(seed,identity+2))*18
        try:ay=surface(model.terrain,ax,az)
        except ValueError:continue
        u,v,depth=model.camera.project(Vec(ax,ay+.15,az))
        if depth<=100 or depth>6500 or not(0<=u<1 and 0<=v<1):continue
        if chance>.85*(1-depth/10000):continue
        point=int(u*width),int(v*height)
        if point not in tonal:continue
        xx,yy=point;col=min(pw-1,int((xx+.5)*pw/width))
        indexes=[min(ph-1,int((yy+fy)*ph/height))*pw+col for fy in (.25,.75)]
        ss=[samples[index] for index in indexes]
        if any(s is None or materials[s[0]]!='terrain' for s in ss):continue
        ds=[depths[index] for index in indexes]
        tolerance=max(1,(max(ds)-min(ds))*.55)
        if not min(ds)-tolerance<=depth<=max(ds)+tolerance:continue
        if max(ds)-min(ds)>max(70,depth*.055):continue
        # The cell represents a textured surface patch, not a separate creature.
        ink=tonal[point][1];upper=ink&0xffffff;lower=ink>>24&0xffffff
        top=tuple(upper>>s&255 for s in (16,8,0));bottom=tuple(lower>>s&255 for s in (16,8,0))
        if max(abs(a-b) for a,b in zip(top,bottom))>36:continue
        base=tuple(round((a+b)/2) for a,b in zip(top,bottom))
        mass=cover(ax,az,seed)
        face=ss[1];a,b,c,wa,wb,wc=face
        ny=normals[a].y*wa+normals[b].y*wb+normals[c].y*wc
        variant=int(random(seed,identity+3)*4)
        if (1-smooth(.60,.82,ny))*smooth(.50,.76,noise(ax+seed%8192,az,90))>.20:
            char=('.',':','_','/')[variant];gray=sum(base)/3
            color=tuple(round(v*.7+gray*.3) for v in base)
        elif mass<.36:
            char=('v','y',';',"'")[variant];color=base
        else:
            char=('y',';','/','\\')[variant];color=base
        contrast=1.18+.48*(1-depth/6500)
        color=tuple(min(255,round(v*contrast)) for v in color)
        packed=(1<<48)|((color[0]<<16|color[1]<<8|color[2])<<24)|(base[0]<<16|base[1]<<8|base[2])
        sites[identity]=(depth,point,(char,packed),identity)
    result={}
    for depth,point,value,identity in sorted(sites.values(),key=lambda p:(p[0],p[1])):
        if len(result)>=MAX_GROUND_GLYPHS:break
        result.setdefault(point,value)
        if len(result)>=MAX_GROUND_GLYPHS or random(seed,identity+40000)>.30:continue
        # A pair of different strokes shares a shaded base: a clump, not a stamp.
        dx=-1 if identity%2 else 1;neighbor=point[0]+dx,point[1]
        if neighbor not in tonal or neighbor in result:continue
        col=min(pw-1,int((neighbor[0]+.5)*pw/width));row=min(ph-1,int((neighbor[1]+.5)*ph/height))
        if abs(depths[row*pw+col]-depth)>max(60,depth*.03):continue
        ink=tonal[neighbor][1];a=ink>>24&0xffffff;b=ink&0xffffff
        base=tuple(round(((a>>s&255)+(b>>s&255))*.45) for s in (16,8,0))
        fg=tuple(min(255,round(v*1.42)) for v in base)
        char=(',',"'",';','/')[identity%4]
        result[neighbor]=(char,(1<<48)|((fg[0]<<16|fg[1]<<8|fg[2])<<24)|(base[0]<<16|base[1]<<8|base[2]))
    return result


def forms(model,coverage,cells,width,height,seed=12345):
    """Material-shaped foliage and stone strokes on actual visible surfaces."""
    from vegetation import noise
    mesh,normals,materials,samples,depths,_,pw,ph,*_=coverage
    owners=['']*len(mesh.vertices)
    for tri in mesh.triangles:
        if tri.material in ('fir','cedar','tree','metal'):
            for index in tri[:3]:owners[index]=tri.owner
    candidates=[];marks=[];seen=set()
    def shade(sample,source,depth):
        a,b,c,wa,wb,wc=sample;material=materials[a];owner=owners[a]
        tree=material in ('fir','cedar','tree')
        rock=material=='metal' and owner.startswith('lab-foreground:rock:')
        if not (tree or rock) or depth>8500:return source,None
        px,py,pz=(mesh.vertices[a][j]*wa+mesh.vertices[b][j]*wb+mesh.vertices[c][j]*wc for j in range(3))
        ny=normals[a].y*wa+normals[b].y*wb+normals[c].y*wc
        footprint=max(1.5,depth*model.camera.span_y/max(1,model.camera.focal*height*2))
        fine=noise(px+py*.31,pz-py*.23,max(2.5,footprint*1.4))
        mass=noise(px+py*.65,pz-py*.18,8 if tree else 1.7)
        rgb=tuple(source>>shift&255 for shift in (16,8,0))
        fade=max(0,min(1,(8500-depth)/5000))
        if tree:
            strength=.70+.45*mass+.15*fine
            highlight=smooth(.55,.88,mass)*.18
            exposure=max(.25,min(1,sum(rgb)/150))
            color=tuple(round(v*(1+fade*(strength-1))+t*exposure*highlight*fade) for v,t in zip(rgb,(78,110,62)))
        else:
            strength=.72+.28*ny+.16*fine
            color=tuple(round(v*(1+fade*(strength-1))) for v in rgb)
        color=tuple(max(0,min(255,v)) for v in color)
        packed=color[0]<<16|color[1]<<8|color[2]
        identity=(owner,math.floor(px/3),math.floor(py/2),math.floor(pz/3))
        digest=int.from_bytes(hashlib.sha256(repr(identity).encode()).digest()[:4],'big')
        return packed,(owner,tree,identity,digest,mass,depth,color,fade)
    for y in range(height):
        for x in range(width):
            ch,style=cells[x,y]
            if ch not in ('▄','▀'):continue
            upper,lower=(style&0xffffff,style>>24&0xffffff) if ch=='▄' else (style>>24&0xffffff,style&0xffffff)
            xx=min(pw-1,int((x+.5)*pw/width))
            indexes=[min(ph-1,int((y+fy)*ph/height))*pw+xx for fy in (.25,.75)]
            adjusted=[];info=[]
            for index,source in zip(indexes,(upper,lower)):
                if samples[index] is None:adjusted.append(source);info.append(None)
                else:
                    value,detail=shade(samples[index],source,depths[index]);adjusted.append(value);info.append(detail)
            if not any(info):continue
            depth=min(item[5] for item in info if item)
            value=('▄',(1<<48)|(adjusted[1]<<24)|adjusted[0])
            candidates.append((depth,x,y,value))
            if not all(info) or info[0][0]!=info[1][0]:continue
            owner,tree,identity,digest,mass,depth,color,fade=info[1]
            if identity in seen or random(seed,digest)>.85*max(.45,fade):continue
            seen.add(identity)
            variant=digest%6
            char=('y','v','/','\\',"'",';')[variant] if tree else ('_',':','/','-',"'",'.')[variant]
            base=tuple(round(((adjusted[0]>>sh&255)+(adjusted[1]>>sh&255))/2) for sh in (16,8,0))
            shadow=mass<.35
            fg=tuple(max(0,min(255,round(v*(.52 if shadow else 1.43)+(0 if shadow else 4)))) for v in base)
            bg=tuple(round(v*(1.04 if shadow else .91)) for v in base)
            ink=(1<<48)|((fg[0]<<16|fg[1]<<8|fg[2])<<24)|(bg[0]<<16|bg[1]<<8|bg[2])
            marks.append((depth,x,y,(char,ink)))
    result={(x,y):value for _,x,y,value in sorted(candidates,key=lambda p:(p[0],p[2],p[1]))[:2048]}
    count=0
    for _,x,y,value in sorted(marks,key=lambda p:(p[0],p[2],p[1])):
        if (x,y) not in result:continue
        result[x,y]=value;count+=1
        if count>=MAX_FORM_GLYPHS:break
    return result


def overlay(model,coverage,cells,width,height,seed=12345):
    """One bounded hybrid plane: tonal relief plus sparse nearer text accents."""
    result=tones(model,coverage,cells,width,height,seed)
    result.update(glyphs(model,coverage,result,width,height,seed))
    result.update(forms(model,coverage,cells,width,height,seed))
    return result
