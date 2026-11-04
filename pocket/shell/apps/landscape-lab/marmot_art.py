"""Metre-scale marmot anatomy study for the existing geometry/cell renderer."""
import math


def ellipsoid(center, radii, material, owner, segments=12, rings=8, clean_poles=False):
    from geometry import Vec, Mesh, Triangle
    vertices=[]
    for row in range(rings+1):
        latitude=-math.pi/2+math.pi*row/rings
        for col in range(segments):
            angle=col*math.tau/segments
            vertices.append(Vec(center.x+radii[0]*math.cos(latitude)*math.cos(angle),
                                center.y+radii[1]*math.sin(latitude),
                                center.z+radii[2]*math.cos(latitude)*math.sin(angle)))
    triangles=[]
    for row in range(rings):
        for col in range(segments):
            a=row*segments+col;b=row*segments+(col+1)%segments
            c=a+segments;d=b+segments
            if clean_poles and row==0:triangles.append(Triangle(b,c,d,material,owner))
            elif clean_poles and row==rings-1:triangles.append(Triangle(a,c,b,material,owner))
            else:triangles.extend((Triangle(a,c,b,material,owner),Triangle(b,c,d,material,owner)))
    return Mesh(tuple(vertices),tuple(triangles))


def marmot(origin, pose='forage', owner='animal:marmot:0', scale=.48, detail='inspection'):
    """Rounded torso, four short legs, muzzle, small ears and tapered furry tail.

    Default nose-to-tail length is about .9m in this illustrative art study.
    Geometry remains in world metres, so wide cameras naturally lose detail.
    Optional world detail reduces tessellation and omits sub-cell claws, inner
    ear inserts and eye glints. Default inspection output is unchanged.
    """
    from geometry import Vec,merge
    if detail not in ('inspection','world'):raise ValueError('Unknown marmot detail: '+str(detail))
    segments,rings_count={'inspection':(12,8),'world':(8,4)}[detail]
    parts=[]
    def body(name, xyz, radii, material='fur'):
        if detail!='inspection' and name.startswith(('claw','earinner','eyeglint')):return
        center=Vec(*(origin[j]+xyz[j]*scale for j in range(3)))
        parts.append(ellipsoid(center,tuple(r*scale for r in radii),material,owner+':'+name,segments,rings_count,detail!='inspection'))
    lift=.13 if pose=='look' else -.07 if pose=='forage' else 0
    body('torso',(-.10,.32,0),(.53,.30,.28))
    body('haunch',(-.38,.28,.01),(.26,.25,.25))
    # Far limbs first; depth coverage, not drawing order, resolves occlusion.
    for i,(x,z) in enumerate(((-.35,.17),(.27,.15),(-.35,-.17),(.27,-.17))):
        stride=(.05 if i%2 else -.05) if pose=='walk' else 0
        body('leg'+str(i),(x+stride,.12,z),(.085,.12,.07))
        body('paw'+str(i),(x+.05+stride,.035,z-.025),(.10,.033,.065),'bird')
        for toe in range(3):
            body('claw'+str(i)+'-'+str(toe),(x+.142+stride,.024,z-.063+toe*.033),(.025,.012,.009),'roof')
    body('neck',(.24,.42+lift*.45,0),(.29,.23,.22))
    # A single broad tapered skull, rather than spherical cheek/muzzle lobes.
    from geometry import Mesh,Triangle
    rings=((.18,.50,.13,.15),(.36,.54,.17,.18),(.54,.51,.13,.145),(.69,.47,.075,.085),(.74,.47,.044,.055))
    vertices=[];faces=[]
    for x,y,ry,rz in rings:
        for j in range(segments):
            angle=j*math.tau/segments
            p=(x,y+lift+math.cos(angle)*ry,math.sin(angle)*rz)
            vertices.append(Vec(*(origin[k]+p[k]*scale for k in range(3))))
    for row in range(4):
        for j in range(segments):
            a=row*segments+j;b=row*segments+(j+1)%segments;c=a+segments;d=b+segments
            faces.extend((Triangle(a,b,c,'wood',owner+':head'),Triangle(b,d,c,'wood',owner+':head')))
    parts.append(Mesh(tuple(vertices),tuple(faces)))
    body('nose',(.748,.49+lift,-.008),(.027,.032,.055),'roof')
    for i,z in enumerate((.13,-.15)):
        body('ear'+str(i),(.275,.655+lift,z),(.047,.041,.036))
        body('earinner'+str(i),(.287,.66+lift,z-.022),(.024,.024,.012),'bird')
    body('eye',(.465,.579+lift,-.153),(.019,.019,.012),'roof')
    body('eyeglint',(.469,.584+lift,-.164),(.004,.004,.003),'glass')
    # Overlapping tapered sections avoid a thin rod or a long squirrel plume.
    for i,(x,y,z,r) in enumerate(((-.62,.21,.06,.145),(-.76,.16,.09,.125),(-.9,.13,.12,.10),(-1.01,.12,.15,.065))):
        body('tail'+str(i),(x,y,z),(.17,r,r),'fur' if i<2 else 'bird')
    return merge(parts)


def fur_overlay(model, coverage, cells, width, height, origin=(0,0,0)):
    """Sparse light/dark fur strokes on matching visible anatomy surfaces only."""
    mesh,normals,materials,samples,depths,_,pw,ph,*_=coverage
    owners=['']*len(mesh.vertices)
    bounds={}
    for tri in mesh.triangles:
        if tri.owner.startswith('animal:marmot:'):
            for index in tri[:3]:owners[index]=tri.owner
            points=[mesh.vertices[index] for index in tri[:3]]
            lo,hi=bounds.setdefault(tri.owner,([float('inf')]*3,[-float('inf')]*3))
            for p in points:
                for j in range(3):lo[j]=min(lo[j],p[j]);hi[j]=max(hi[j],p[j])
    marks=[];seen=set();tones={}
    # Material-local fur palette inherits the canonical render's exposure. It
    # avoids using generic metal/roof colors as the final anatomy colors.
    bases={'fur':(108,87,62),'wood':(121,91,56),'metal':(112,123,128),
           'roof':(52,65,66),'bird':(75,79,83),'glass':(210,166,89)}
    def tint(value,sample):
        if sample is None or not owners[sample[0]]:return value
        name=owners[sample[0]].rsplit(':',1)[-1]
        a,b,c,wa,wb,wc=sample
        point=[mesh.vertices[a][j]*wa+mesh.vertices[b][j]*wb+mesh.vertices[c][j]*wc for j in range(3)]
        lo,hi=bounds[owners[a]]
        q=[(point[j]-lo[j])/max(1e-8,hi[j]-lo[j]) for j in range(3)]
        target=(146,146,133)
        if name in ('torso','haunch'):
            front=q[0] if name=='torso' else .12
            target=tuple(a*(1-front)+b*front for a,b in zip((117,101,81),(175,176,163)))
        elif name=='neck':target=(168,168,153)
        elif name=='head':
            target=(135,137,125)
            if q[0]>.40 and q[1]>.52:target=(77,79,74)
            elif q[0]>.72:target=(192,188,166)
        if name=='muzzle':target=(148,128,99)
        elif name=='cheek':target=(143,111,74)
        elif name.startswith(('paw','claw')):target=(44,39,32)
        elif name.startswith('tail'):target=(103,76,48) if name in ('tail0','tail1') else (77,57,37)
        elif name.startswith('earinner'):target=(80,57,38)
        elif name=='nose':target=(34,27,23)
        elif name=='eye':target=(22,18,15)
        elif name=='eyeglint':target=(181,174,149)
        from vegetation import noise
        if name not in ('eye','eyeglint','nose') and not name.startswith(('paw','claw')):
            local=[point[j]-origin[j] for j in range(3)]
            fleck=noise(local[0]+local[1]*.6,local[2]-local[1]*.3,.008)
            target=tuple(v*(.80+.40*fleck) for v in target)
        original=bases.get(materials[sample[0]],bases['fur'])
        exposure=sum(value>>s&255 for s in (16,8,0))/sum(original)
        return sum(max(0,min(255,round(v*exposure)))<<s for v,s in zip(target,(16,8,0)))
    for (x,y),(char,ink) in cells.items():
        xx=min(pw-1,int((x+.5)*pw/width))
        indexes=[min(ph-1,int((y+fy)*ph/height))*pw+xx for fy in (.25,.75)]
        pair=[samples[i] for i in indexes]
        upper,lower=(ink&0xffffff,ink>>24&0xffffff) if char=='▄' else (ink>>24&0xffffff,ink&0xffffff)
        if any(s is not None and owners[s[0]] for s in pair):
            upper,lower=tint(upper,pair[0]),tint(lower,pair[1])
            tones[x,y]=('▄',(1<<48)|(lower<<24)|upper)
        if any(s is None for s in pair):continue
        names=[owners[s[0]] for s in pair]
        if not names[0] or names[0]!=names[1]:continue
        if any(token in names[0] for token in ('eye','nose','earinner','paw')):continue
        a,b,c,wa,wb,wc=pair[1]
        p=[sum(mesh.vertices[index][j]*weight for index,weight in ((a,wa),(b,wb),(c,wc))) for j in range(3)]
        key=tuple(math.floor((v-origin[j])/.025) for j,v in enumerate(p))
        if key in seen:continue
        seen.add(key)
        identity=key[0]*73856093 ^ key[1]*19349663 ^ key[2]*83492791
        if identity%7>2:continue
        rgb=tuple(round(((upper>>s&255)+(lower>>s&255))/2) for s in (16,8,0))
        dark=identity%5==0
        fg=tuple(max(0,min(255,round(v*(.68 if dark else 1.28)))) for v in rgb)
        bg=tuple(round(v*(1.03 if dark else .96)) for v in rgb)
        from paint import ink as color
        glyph=(',',"'",';','/')[identity%4]
        marks.append((depths[indexes[1]],(x,y),(glyph,color(*fg,background=bg))))
    tones.update({point:value for _,point,value in sorted(marks)[:512]})
    return tones
