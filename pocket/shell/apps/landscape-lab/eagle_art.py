"""Reference-led bald eagle flight study for canonical geometry and coverage."""
import math


def eagle(origin, pose='glide', owner='animal:eagle'):
    from geometry import Vec,Mesh,Triangle,merge
    from marmot_art import ellipsoid
    parts=[]
    def solid(name,points,material='bird',height=.012):
        n=len(points)
        vertices=tuple(Vec(x,side*height,z) for side in (-1,1) for x,z in points)
        faces=[]
        for j in range(1,n-1):
            faces.extend((Triangle(0,j+1,j,material,owner+':'+name),Triangle(n,n+j,n+j+1,material,owner+':'+name)))
        for j in range(n):
            k=(j+1)%n
            faces.extend((Triangle(j,k,n+j,material,owner+':'+name),Triangle(k,n+k,n+j,material,owner+':'+name)))
        parts.append(Mesh(vertices,tuple(faces)))
    wing=((.06,-.19),(.32,-.27),(.65,-.22),(.79,-.13),(.80,.22),(.66,.32),(.40,.29),(.18,.27),(.065,.20))
    for side in (-1,1):
        solid('wing'+str(side),[(side*x,z) for x,z in wing])
        # Separate long primary feathers create the photographed fingered tips.
        for j,(tx,tz) in enumerate(((.99,-.21),(1.09,-.10),(1.10,.04),(1.06,.18),(.99,.32),(.88,.40))):
            bx,bz=.70,-.13+j*.065
            dx,dz=tx-bx,tz-bz;length=math.hypot(dx,dz)
            nx,nz=-dz/length*.044,dx/length*.044
            solid('primary'+str(side)+'-'+str(j),[(side*(bx+nx),bz+nz),(side*(tx+nx*.5),tz+nz*.5),(side*tx,tz),(side*(tx-nx*.5),tz-nz*.5),(side*(bx-nx),bz-nz)])
        # Overlapping feather panels follow the swept trailing edge.
        for j in range(7):
            x=.22+j*.078
            solid('feather'+str(side)+'-'+str(j),[(side*x,-.12),(side*(x+.068),-.10),(side*(x+.10),.275),(side*(x+.025),.30)],height=.018)
    solid('tail',[(-.065,.20),(.065,.20),(.24,.62),(.13,.66),(0,.64),(-.13,.66),(-.24,.62)],'metal')
    for name,center,radii,material in (
        ('body',Vec(0,0,-.015),(.12,.09,.33),'bird'),
        ('neck',Vec(0,.015,-.29),(.075,.075,.12),'metal'),
        ('head',Vec(0,.025,-.37),(.065,.065,.10),'metal'),
        ('beak',Vec(0,.0,-.485),(.042,.041,.075),'glass'),
        ('hook',Vec(0,-.025,-.53),(.026,.045,.025),'glass'),
        ('eye',Vec(.073,.034,-.414),(.008,.009,.012),'roof')):
        parts.append(ellipsoid(center,radii,material,owner+':'+name))
    mesh=merge(parts)
    bank=.46 if pose=='bank' else 0
    vertices=[]
    for p in mesh.vertices:
        y=p.y+(abs(p.x)*.26 if pose=='upstroke' else 0)
        x=p.x*math.cos(bank)-y*math.sin(bank)
        y=p.x*math.sin(bank)+y*math.cos(bank)
        vertices.append(Vec(origin.x+x,origin.y+y,origin.z+p.z))
    return Mesh(tuple(vertices),mesh.triangles)


def feather_overlay(model,coverage,cells,width,height,origin=(0,0,0)):
    mesh,normals,materials,samples,depths,_,pw,ph,*_=coverage
    owners=['']*len(mesh.vertices)
    for tri in mesh.triangles:
        if tri.owner.startswith('animal:eagle'):
            for i in tri[:3]:owners[i]=tri.owner.rsplit(':',1)[-1]
    result={};count=0
    bases={'bird':(75,79,83),'metal':(112,123,128),'glass':(210,166,89),'roof':(52,65,66)}
    def color(value,sample):
        if sample is None or not owners[sample[0]]:return value
        name=owners[sample[0]]
        target=(65,48,34)
        if name.startswith('feather'):target=(89,68,46)
        elif name in ('head','neck','tail'):target=(220,216,201)
        elif name in ('beak','hook'):target=(204,158,48)
        elif name=='eye':target=(25,23,17)
        exposure=sum(value>>s&255 for s in (16,8,0))/sum(bases[materials[sample[0]]])
        return sum(max(0,min(255,round(c*exposure)))<<s for c,s in zip(target,(16,8,0)))
    for (x,y),(ch,ink) in cells.items():
        xx=min(pw-1,int((x+.5)*pw/width))
        pair=[samples[min(ph-1,int((y+fy)*ph/height))*pw+xx] for fy in (.25,.75)]
        if not any(s is not None and owners[s[0]] for s in pair):continue
        upper,lower=(ink&0xffffff,ink>>24&0xffffff) if ch=='▄' else (ink>>24&0xffffff,ink&0xffffff)
        upper,lower=color(upper,pair[0]),color(lower,pair[1])
        result[x,y]=('▄',(1<<48)|(lower<<24)|upper)
        if count>=256 or any(s is None for s in pair):continue
        names=[owners[s[0]] for s in pair]
        if names[0]!=names[1] or not names[0].startswith(('wing','feather','tail')):continue
        a,b,c,wa,wb,wc=pair[1]
        px,pz=(mesh.vertices[a][j]*wa+mesh.vertices[b][j]*wb+mesh.vertices[c][j]*wc for j in (0,2))
        identity=math.floor((px-origin[0])/.025)*73856093 ^ math.floor((pz-origin[2])/.035)*19349663
        if identity%7:continue
        bg=tuple(round(((upper>>s&255)+(lower>>s&255))*.5) for s in (16,8,0))
        from paint import ink as paint
        fg=tuple(round(v*.75) for v in bg)
        result[x,y]=('/' if px<0 else '\\',paint(*fg,background=bg));count+=1
    return result
