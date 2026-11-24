"""Inspection meshes for Pacific Northwest wildlife. Coordinates are view units."""
from array import array
import gzip
import math
import struct
from functools import lru_cache
from pathlib import Path
from geometry import Mesh, Triangle, Vec, merge
from marmot_art import ellipsoid

FOX_FRAMES=16
FOX_ASSETS={'fox':'red_fox.mesh.gz','arctic_fox':'arctic_fox.mesh.gz'}

NAMES={'marmot':'Hoary marmot','eagle':'Bald eagle','chipmunk':"Townsend's chipmunk",
       'squirrel':'Douglas squirrel','pika':'American pika','goat':'Mountain goat','fox':'Red fox','arctic_fox':'Arctic fox','bear':'American black bear','trout':'Rainbow trout'}


def skin(rings, paint):
    vertices=tuple(v for ring in rings for v in ring)
    count=len(rings[0])
    triangles=[]
    for i in range(len(rings)-1):
        for j in range(count):
            a=i*count+j
            b=i*count+(j+1)%count
            color=paint(i,(j+.5)*math.tau/count) if callable(paint) else paint
            triangles.extend((Triangle(a,b,a+count,color,''),Triangle(b,b+count,a+count,color,'')))
    return Mesh(vertices,tuple(triangles))


def body(stations,paint):
    # The spine is narrower than the ribs. Below the cheeks and ribs the
    # section draws inward toward the jaw or sternum.
    rings=[]
    for x,y,h,w in rounded_path(stations):
        ring=[]
        for angle in ANGLES:
            up=math.cos(angle)
            flank=math.sin(angle)
            breadth=(1-.25*max(0.,-up)-.12*max(0.,up))
            ring.append(Vec(x,y+h*math.copysign(abs(up)**.82,up),
                            w*breadth*math.copysign(abs(flank)**.88,flank)))
        rings.append(ring)
    return skin(rings,lambda i,t:paint((i+.5)/4,t)) if callable(paint) else skin(rings,paint)


def mix_color(a,b,amount):
    amount=min(1.,max(0.,amount))
    return sum(round(((a>>shift)&255)*(1-amount)+((b>>shift)&255)*amount)<<shift
               for shift in (16,8,0))


ANGLES=tuple(i*math.tau/40 for i in range(40))


def rounded_path(path):
    points=[]
    for i,(b,c) in enumerate(zip(path,path[1:])):
        a,d=path[max(0,i-1)],path[min(len(path)-1,i+2)]
        for step in range(4):
            t=step/4
            points.append(tuple(.5*(2*q+(r-p)*t+(2*p-5*q+4*r-s)*t*t+
                                    (3*q-p-3*r+s)*t*t*t)
                                for p,q,r,s in zip(a,b,c,d)))
    return points+[path[-1]]


def tube(path,color):
    """Fur tails, pinnae and horns taper along a curved centreline in the XY plane."""
    rings=[]
    for i,(x,y,z,r,w) in enumerate(path):
        before,after=path[max(0,i-1)],path[min(len(path)-1,i+1)]
        dx,dy=after[0]-before[0],after[1]-before[1]
        length=math.hypot(dx,dy) or 1
        rings.append([Vec(x-dy/length*r*math.cos(t),y+dx/length*r*math.cos(t),z+w*math.sin(t)) for t in ANGLES])
    return skin(rings,color)


def hindquarters(torso,species,paint,foot):
    """Continue two patches of the pelvic surface down to the hind paws."""
    # Each contour is (x, height, fore-aft radius, half breadth). The
    # lowest rings describe the sole, so a resting leg stays planted while
    # the head lifts. Squirrels have a long hind foot; pikas a short one.
    contours={
        'marmot':[(-.264,.115,.091,.047),(-.245,.084,.074,.041),
                  (-.281,.050,.049,.031),(-.299,.031,.030,.027),
                  (-.254,.027,.073,.030),(-.244,.008,.071,.025)],
        'chipmunk':[(-.178,.116,.059,.032),(-.155,.090,.046,.027),
                    (-.184,.060,.032,.021),(-.207,.032,.016,.014),
                    (-.167,.027,.055,.017),(-.156,.009,.053,.015)],
        'squirrel':[(-.173,.143,.081,.039),(-.132,.108,.057,.036),
                    (-.169,.078,.045,.027),(-.214,.038,.023,.018),
                    (-.159,.031,.072,.022),(-.147,.008,.069,.018)],
        'pika':[(-.152,.105,.065,.037),(-.133,.077,.055,.032),
                (-.157,.053,.039,.025),(-.177,.031,.023,.019),
                (-.146,.026,.051,.024),(-.136,.008,.048,.021)],
        'goat':[(-.314,.292,.069,.049),(-.293,.248,.049,.038),
                (-.334,.171,.033,.029),(-.370,.119,.024,.022),
                (-.367,.100,.018,.018),(-.359,.060,.015,.015),
                (-.355,.042,.018,.018),(-.344,.023,.016,.016)]}
    stance={'marmot':.089,'chipmunk':.055,'squirrel':.068,'pika':.068,'goat':.091}[species]
    n=len(ANGLES)
    vertices=list(torso.vertices)
    triangles=list(torso.triangles)
    for side,j0,j1 in ((1,11,19),(-1,21,29)):
        lo,hi=3,12
        # body() emits two triangles for every longitudinal/angular cell.
        remove={2*(i*n+j)+k for i in range(lo,hi) for j in range(j0,j1) for k in (0,1)}
        border=([(lo,j) for j in range(j0,j1)]+[(i,j1) for i in range(lo,hi)]+
                [(hi,j) for j in range(j1,j0,-1)]+[(i,j0) for i in range(hi,lo,-1)])
        last=[i*n+j for i,j in border]
        angles=[math.atan2(1-2*(j-j0)/(j1-j0),2*(i-lo)/(hi-lo)-1) for i,j in border]
        colors=[paint(i/4,j*math.tau/n) for i,j in border]
        # Drop faces by their original indices. Preserve the common border
        # vertices so the top of the thigh shares the torso normals.
        for index in remove:triangles[index]=None
        sections=rounded_path(contours[species])
        for row,(x,y,rx,rz) in enumerate(sections):
            f=row/(len(sections)-1)
            offset=side*(.028 if species=='goat' else .013)*min(1.,f*2)
            ring=[]
            for t in angles:
                ring.append(len(vertices))
                vertices.append(Vec(x+offset+rx*math.cos(t),y,side*stance+rz*math.sin(t)))
            for k in range(len(ring)):
                color=mix_color(colors[k],foot,min(1.,f*1.15))
                b=(k+1)%len(ring)
                triangles.extend((Triangle(last[k],last[b],ring[k],color,''),
                                  Triangle(last[b],ring[b],ring[k],color,'')))
            last=ring
        for k in range(1,len(last)-1):
            triangles.append(Triangle(last[0],last[k],last[k+1],foot,''))
    return Mesh(tuple(vertices),tuple(face for face in triangles if face is not None))


def goat_leg(hind, side, coat):
    """Standing ungulate limb, lofted down through horizontal sections."""
    # x, height, fore-aft radius, lateral radius. The stifle is high
    # against the belly, the hock projects behind it, and the cannon
    # drops almost vertically. The forearm stacks under the elbow.
    stagger=side*(.028 if hind else -.028)
    foot_x=(-.344 if hind else .133)+stagger
    foot_z=side*.091
    parts=[]
    if not hind:
        sections=[
        (.115,.509,.047,.027), (.107,.426,.067,.049),
        (.094,.322,.054,.043), (.081,.250,.040,.031),
        (.107,.170,.026,.024), (.121,.123,.022,.023),
        (.120,.107,.019,.020), (.119,.063,.014,.015),
        (.122,.043,.018,.018), (.133,.023,.015,.016),
        ]
        rings=[]
        for x,y,rx,rz in rounded_path(sections):
            load=min(1.,max(0.,(.32-y)/.23))
            # Stagger the planted feet around the centre of mass.
            x+=stagger*load
            z=side*(.056+.035*load)
            rings.append([Vec(x+rx*math.cos(t),y,z+rz*math.sin(t)) for t in ANGLES])
        limb=skin(rings,lambda i,t:mix_color(coat,0xb9b4a5,max(0.,i/len(rings)-.6)))
        parts.append(limb)
    # Each claw broadens toward the bearing edge and has a flat sole.
    for claw in (-1,1):
        rings=[]
        for y,offset,length,width,gap in ((.034,-.005,.014,.008,.006),
                                          (.025,.000,.022,.010,.008),
                                          (.011,.008,.028,.011,.010),
                                          (.002,.008,.029,.011,.011),
                                          (.002,.008,.001,.001,.011)):
            rings.append([Vec(foot_x+offset+length*math.cos(t),y,
                              foot_z+claw*(gap+.003*math.cos(t))+width*math.sin(t))
                          for t in ANGLES])
        parts.append(skin(rings,0x514941))
    return merge(parts)


# Offline adaptation of the Khronos Fox sample. See red_fox_credits.md.
@lru_cache(maxsize=len(FOX_ASSETS))
def fox_animation(species):
    with gzip.open(Path(__file__).with_name(FOX_ASSETS[species]),'rb') as src:
        frames,count,faces=struct.unpack('<III',src.read(12))
        if frames!=FOX_FRAMES:raise ValueError('Unexpected fox animation length')
        triangles=tuple(Triangle(a,b,c,color,'') for a,b,c,color in
                        struct.iter_unpack('<4I',src.read(faces*16)))
        positions=src.read()
        if len(positions)!=frames*count*6:raise ValueError('Incomplete fox animation')
        return count,triangles,positions


def fox_model(species,phase):
    count,triangles,positions=fox_animation(species)
    frame=memoryview(positions)[phase*count*6:(phase+1)*count*6]
    return Mesh(tuple(Vec(x/16000,y/16000,z/16000) for x,y,z in struct.iter_unpack('<3h',frame)),triangles)


def mammal(species,phase):
    if species in FOX_ASSETS:return fox_model(species,phase)
    # Sagittal outlines (x, dorsal height, ventral height, half breadth).
    # Lay out pelvis, lumbar tuck, rib cage, shoulder, nape, skull and muzzle
    # independently so the ventral outline need not mirror the back.
    outlines={
        'marmot':[(-.43,.230,.179,.040),(-.385,.336,.106,.115),(-.295,.380,.074,.135),
                  (-.158,.367,.113,.125),(-.028,.353,.084,.128),(.095,.388,.102,.128),
                  (.175,.390,.215,.091),(.253,.410,.234,.090),(.326,.389,.239,.082),
                  (.394,.332,.247,.060),(.425,.315,.272,.035)],
        'chipmunk':[(-.32,.176,.133,.025),(-.27,.228,.097,.057),(-.20,.251,.082,.073),
                    (-.09,.245,.125,.058),(.035,.239,.107,.068),(.116,.254,.128,.063),
                    (.166,.252,.187,.044),(.227,.290,.182,.060),(.298,.261,.182,.043),
                    (.365,.218,.196,.017)],
        'squirrel':[(-.31,.222,.138,.031),(-.265,.299,.097,.072),(-.195,.329,.085,.091),
                    (-.075,.304,.143,.073),(.044,.309,.147,.081),(.12,.333,.166,.081),
                    (.172,.323,.232,.054),(.239,.367,.229,.067),(.304,.324,.229,.050),
                    (.367,.270,.244,.020)],
        'pika':[(-.278,.196,.132,.033),(-.233,.271,.081,.084),(-.161,.309,.062,.101),
                (-.053,.300,.090,.091),(.038,.291,.079,.099),(.107,.296,.106,.092),
                (.150,.287,.156,.070),(.201,.303,.151,.076),(.253,.267,.146,.061),
                (.292,.213,.169,.035)],
        'goat':[(-.480,.404,.353,.036),(-.432,.487,.290,.086),(-.332,.517,.222,.111),
                (-.154,.492,.272,.094),(.010,.533,.209,.124),(.132,.614,.199,.125),
                (.222,.571,.369,.086),(.317,.626,.426,.079),(.387,.588,.421,.068),
                (.458,.524,.407,.051),(.50,.466,.417,.035)]}
    stations=[(x,(top+bottom)/2,(top-bottom)/2,width)
              for x,top,bottom,width in outlines[species]]
    base,belly={'marmot':(0x928e84,0x685443),'chipmunk':(0x99673d,0xddbf87),'squirrel':(0x766b52,0xc9924a),
                'pika':(0x9b8877,0xcbb693),'goat':(0xe6e1cf,0xc3baa7)}[species]
    def coat(i,t):
        d=min(t,math.tau-t)
        if species=='chipmunk':
            if i<=5:
                if d<.13 or .57<d<.80 or 1.12<d<1.38:return 0x392f24
                if .80<=d<=1.12 or .23<d<.47:return 0xe9d8ac
            elif 6<=i<=8:
                if 1.03<d<1.34 or 1.71<d<2:return 0xe9d7af
                if 1.34<=d<=1.71:return 0x50372b
        if species=='marmot':
            mantle=math.exp(-((i-4.8)/2.5)**2)*min(1.,max(0.,2.4-d))
            fur=mix_color(0x776855,0xc9c4b5,mantle)
            fur=mix_color(fur,0x57483e,(d-1.65)*.8)
            crown=math.exp(-((i-7.9)/1.1)**2)*max(0.,1.25-d)
            return mix_color(fur,0x493e34,crown)
        if species=='squirrel' and i<6 and 1.47<d<1.66:return 0x423b31
        return mix_color(base,belly,(d-1.48)*1.8)
    lift=(.0,.025,-.019)[phase]
    stations=[(x,y+lift*max(0,i-3)/6,h,w) for i,(x,y,h,w) in enumerate(stations)]
    paw=0x443b31 if species=='marmot' else base if species=='goat' else belly
    parts=[hindquarters(body(stations,coat),species,coat,paw)]
    def oval(x,y,z,rx,ry,rz,color):
        parts.append(ellipsoid(Vec(x,y,z),(rx,ry,rz),color,'',16,10,True))
    end=stations[-1]
    oval(end[0],end[1]+.002,0,.014,.015,end[3]*.92,0x342d29)
    head=stations[7]
    ear=tuple(.55*a+.45*b for a,b in zip(stations[6],head))
    shoulder=stations[5]
    for side in (-1,1):
        z=side*head[3]*.92
        eye=.013 if species in ('chipmunk','squirrel','pika') else .016
        oval(head[0]+.012,head[1]+head[2]*.30,z,eye,eye*.85,.008,0x211d18)
        oval(head[0]+.017,head[1]+head[2]*.36,z+side*.006,.0025,.0025,.0015,0xe8e4d8)
        if species=='marmot':
            muzzle=stations[-2]
            oval(muzzle[0]-.012,muzzle[1]-.009,side*muzzle[3]*.84,
                 .031,.018,.014,0xc6b7a1)
            for j in range(3):
                oval(muzzle[0]-.022+j*.009,muzzle[1]-.006+(j%2)*.006,
                     side*(muzzle[3]*.84+.013),.0025,.002,.002,0x51463c)
        size={'marmot':.033,'chipmunk':.032,'squirrel':.052,'pika':.061,'goat':.052}[species]
        ex,ey,ez=ear[0],ear[1]+ear[2]*.74,side*ear[3]*.65
        # A thin cupped pinna rises from the skull and leans back, with a
        # broad rim in the pika and a longer lance-shaped tip in the goat.
        length=size*(2 if species=='goat' else 1.42)
        sweep=size*(1.35 if species=='goat' else .43)
        ear_path=[(ex,ey-size*.32,ez,size*.45,.012),
                  (ex-sweep*.30,ey+length*.25,ez+side*.009,size*.63,.015),
                  (ex-sweep*.66,ey+length*.70,ez+side*.016,size*.52,.010),
                  (ex-sweep,ey+length,ez+side*.021,size*(.24 if species=='pika' else .07),.003)]
        parts.append(tube(rounded_path(ear_path),lambda i,t:mix_color(base,0x806b60,
                          max(0.,side*math.sin(t))**4*math.sin(math.pi*(i+.5)/12))))
        if species=='goat':
            parts.extend(goat_leg(hind,side,base) for hind in (False,True))
        else:
            x,y,h,w=shoulder
            leg_z=side*w*.61
            heel=x-.012-side*(.019 if phase==1 else -.006)
            toe=heel+.090
            leg=[(x,y,leg_z,.040,.045),(x-.039,.098,leg_z,.025,.029),
                 (heel-.014,.053,leg_z,.018,.018),(heel,.030,leg_z,.021,.025),
                 (toe-.020,.024,leg_z,.017,.026),(toe,.026,leg_z,.006,.016)]
            limb_scale={'marmot':.83,'chipmunk':.55,'squirrel':.65,'pika':.66}[species]
            leg=rounded_path([(lx,ly,lz,r*limb_scale,w*limb_scale) for lx,ly,lz,r,w in leg])
            parts.append(tube(leg,lambda i,t:mix_color(base,paw,(i-9)/6)))
        if species=='goat':
            parts.append(tube([(ear[0]+.037,ey+.033,ez,.022,.018),(ear[0]+.029,ey+.12,ez,.016,.012),
                               (ear[0]-.004,ey+.19,ez,.008,.007),(ear[0]-.032,ey+.208,ez,.001,.001)],0x3d3832))
    tails={'marmot':[(-.34,.21,.067),(-.43,.135,.068),(-.51,.081,.056),(-.60,.066,.034),(-.66,.061,.003)],
           'chipmunk':[(-.26,.16,.025),(-.36,.18,.030),(-.44,.23,.034),(-.54,.28,.030),(-.64,.34,.012),(-.67,.34,.002)],
           'squirrel':[(-.22,.16,.049),(-.35,.18,.087),(-.42,.30,.083),(-.40,.45,.087),(-.32,.55,.082),(-.20,.56,.065),(-.10,.50,.039),(-.05,.46,.004)],
           'goat':[(-.44,.38,.03),(-.50,.42,.031),(-.535,.45,.008)]}
    if species in tails:
        tail=tails[species]
        path=rounded_path([(x,y+lift*i/len(tail),.012,r,r*.86) for i,(x,y,r) in enumerate(tail)])
        parts.append(tube(path,0x665341 if species=='marmot' else base))
        if species=='squirrel':
            # Guard hairs fan away from the tail centreline, breaking up the contour.
            import random
            rng=random.Random(47)
            for j in range(720):
                i=rng.randrange(1,len(path)-1)
                x,y,z,r,w=path[i]
                dx,dy=path[i+1][0]-path[i-1][0],path[i+1][1]-path[i-1][1]
                length=math.hypot(dx,dy) or 1
                dx,dy=dx/length,dy/length
                t=rng.random()*math.tau
                nx,ny,nz=-dy*math.cos(t),dx*math.cos(t),math.sin(t)
                start=Vec(x+nx*r*.94,y+ny*r*.94,z+nz*w*.94)
                tip=Vec(start.x+dx*.040+nx*.026,start.y+dy*.040+ny*.026,start.z+nz*.026)
                edge=Vec(start.x+dy*.004,start.y-dx*.004,start.z+.003)
                parts.append(Mesh((start,tip,edge),(Triangle(0,1,2,mix_color(0x4d463b,0xc1a682,rng.random()),''),)))
    if species=='goat':
        parts.append(tube([(.37,.447,0,.04,.037),(.35,.375,0,.027,.025),(.32,.32,0,.003,.004)],0xd0c8b5))
    model=merge(parts)
    return model


def raptor(phase):
    parts=[]
    def feather(root,tip,width,color):
        x,y,z=root;tx,ty,tz=tip
        dx,dz=tx-x,tz-z
        span=math.hypot(dx,dz)
        rings=[]
        for f,r in ((0,.03),(.22,.72),(.55,1),(.84,.68),(1,.01)):
            rings.append([Vec(x+dx*f-dz/span*width*r*math.cos(t),y+(ty-y)*f+.007*r*math.sin(t),
                              z+dz*f+dx/span*width*r*math.cos(t)) for t in ANGLES[::4]])
        parts.append(skin(rings,lambda i,t:mix_color(color,0xb7a384,.23*abs(math.sin(t))**14)))
    for side in (-1,1):
        # Broad secondary flight feathers join the elbow to the wrist. Outer
        # primaries overlap at the bases and separate only at the tapered tips.
        stations=[(.055,.12,-.22),(.23,.19,-.29),(.46,.245,-.28),(.66,.20,-.23),(.78,.13,-.15),(.86,.06,-.08)]
        rings=[]
        for z,lead,trail in stations:
            rings.append([Vec((lead+trail)/2+(lead-trail)/2*math.cos(t),.025+.035*math.sin(t),side*z) for t in ANGLES])
        parts.append(skin(rings,0x574336))
        for j in range(9):
            z=.13+j*.069
            feather((.035,.017,side*z),(-.30+.065*z,.009,side*(z+.080)),.055,0x695240 if j%2 else 0x5a4638)
        for j in range(12):
            z=.10+j*.051
            feather((.13,.071,side*z),(-.16,.068,side*(z+.062)),.043,
                    0x80694f if j%2 else 0x75604d)
        for j,(z,x) in enumerate([(1.02,.142),(1.10,.075),(1.13,-.014),(1.11,-.114),(1.06,-.208),(.975,-.295),(.875,-.325)]):
            feather((.11-.033*j,.025,side*(.68-.018*j)),(x,-.025,side*z),.050,0x413832 if j%2 else 0x4b4036)
    for j in range(-4,5):
        feather((-.15,.014,j*.011),(-.54+.008*abs(j),.012,j*.043),.043,0xe6e1ce if j%2 else 0xf2eddb)
    parts.append(body([(-.40,.014,.006,.012),(-.24,.020,.049,.067),(-.07,.015,.084,.103),
                       (.07,.032,.090,.091),(.17,.060,.052,.060),(.244,.076,.051,.056),
                       (.30,.060,.046,.048)],lambda i,t:0xece8d9 if i>=4 else 0x584433))
    parts.append(body([(.265,.060,.03,.043),(.315,.060,.034,.043),(.35,.053,.027,.032),
                       (.379,.039,.016,.016),(.368,.007,.004,.004)],0xe6b142))
    for side in (-1,1):
        parts.append(ellipsoid(Vec(.261,.084,side*.052),(.011,.011,.007),0x57452c,''))
    # In flight the feet trail close to the belly, toes folded rearward.
    for side in (-1,1):
        z=side*.053
        parts.append(tube([(-.085,-.025,z,.030,.025),(-.12,-.062,z,.026,.021),
                           (-.155,-.075,z,.016,.013)],0x5e4838))
        parts.append(tube([(-.148,-.071,z,.015,.013),(-.184,-.073,z,.010,.012),
                           (-.200,-.063,z,.008,.011)],0xb9944a))
        for toe in (-1,0,1):
            tz=z+toe*.008
            parts.append(tube([(-.183,-.073,tz,.005,.004),(-.205,-.076,tz,.005,.004),
                               (-.210,-.070,tz,.003,.003),(-.205,-.066,tz,.001,.001)],0x645139))
    m=merge(parts)
    flap=(-.08,.25,.09)[phase];bank=(.06,-.12,.03)[phase]
    vertices=[]
    for x,y,z in m.vertices:
        y+=flap*max(0,abs(z)-.10)
        vertices.append(Vec(x,y*math.cos(bank)-z*math.sin(bank),y*math.sin(bank)+z*math.cos(bank)))
    return Mesh(tuple(vertices),m.triangles)


def black_bear(phase):
    lift=(0,.025,-.015)[phase]
    fur=0x413b34
    parts=[body([(-.58,.49,.06,.06),(-.48,.51,.25,.17),(-.28,.53,.31,.21),
                 (.04,.52,.27,.20),(.28,.56,.25,.18),(.41,.61+lift,.18,.14),
                 (.53,.64+lift,.15,.13),(.64,.60+lift,.09,.095),(.73,.58+lift,.053,.066)],
                lambda i,t:0x986f4a if i>6.3 else fur)]
    for side in (-1,1):
        def oval(center,radii,color):
            parts.append(ellipsoid(Vec(*center),radii,color,'',14,10,True))
        oval((.45,.80+lift,.097*side),(.056,.078,.042),fur)
        oval((.572,.678+lift,.109*side),(.017,.016,.012),0x171918)
        for hind in (False,True):
            x=-.35 if hind else .28
            knee=.065 if hind else -.035
            legz=side*.13
            parts.append(tube([(x,.51,legz,.116,.096),(x+knee,.32,legz,.095,.078),
                               (x-.04,.15,legz,.064,.062),(x-.032,.065,legz,.047,.055)],fur))
            oval((x-.005,.048,legz),(.102,.046,.064),0x36302c)
    oval((.729,.61+lift,0),(.035,.033,.058),0x242421)
    return merge(parts)


def rainbow_trout(phase):
    def scales(i,t):
        up=math.cos(t)
        if up>.15 and math.sin(i*41+round(t*10)*17)>.82:return 0x394a43
        return 0x647b65 if up>.32 else 0xb5828c if up>-.13 else 0xc3c4ad
    fish=body([(-.49,.18,.025,.02),(-.31,.18,.056,.037),(-.10,.19,.11,.063),
               (.13,.19,.118,.07),(.32,.18,.085,.062),(.45,.16,.029,.025)],scales)
    parts=[fish]
    for points in [[(-.31,.18),(-.57,.32),(-.53,.18),(-.57,.06)],
                   [(-.14,.28),(-.10,.39),(.025,.30)],[(.035,.11),(-.08,.045),(-.09,.13)]]:
        verts=tuple(Vec(x,y,0) for x,y in points)
        parts.append(Mesh(verts,tuple(Triangle(0,i,i+1,0x69766b,'') for i in range(1,len(verts)-1))))
    for side in (-1,1):
        parts.append(ellipsoid(Vec(.32,.205,side*.053),(.021,.021,.012),0x272c27,'',10,8,True))
    mesh=merge(parts)
    return Mesh(tuple(Vec(x,y,z+(0,.07,-.07)[phase]*max(0.,.30-x)**2) for x,y,z in mesh.vertices),mesh.triangles)


@lru_cache(maxsize=FOX_FRAMES+3)
def pose(species,index,obstacle):
    builders={'eagle':raptor,'bear':black_bear,'trout':rainbow_trout}
    model=builders[species](index) if species in builders else mammal(species,index)
    if obstacle:
        model=merge((model,ellipsoid(Vec(.13,.055,-.19) if species!='eagle' else Vec(-.45,-.95,-1.1),
                                     (.1,.065,.07) if species!='eagle' else (.22,.55,.12),'rock','rock')))
    # Smooth the rounded anatomy by accumulating adjacent triangle normals once
    # per pose. Per-material colours remain independent at triangle boundaries.
    normals=[[0.,0.,0.] for _ in model.vertices]
    for a,b,c,_,_ in model.triangles:
        p,q,r=(model.vertices[i] for i in (a,b,c))
        u,v,w=q.x-p.x,q.y-p.y,q.z-p.z
        i,j,k=r.x-p.x,r.y-p.y,r.z-p.z
        nx,ny,nz=v*k-w*j,w*i-u*k,u*j-v*i
        for vertex in (a,b,c):
            n=normals[vertex];n[0]+=nx;n[1]+=ny;n[2]+=nz
    points=array('f')
    for p,(nx,ny,nz) in zip(model.vertices,normals):
        length=math.sqrt(nx*nx+ny*ny+nz*nz)
        # Light the animal from above and in front of the inspection camera.
        diffuse=(-.35*nx+.78*ny-.51*nz)/length if length else 0
        points.extend((*p,.75+.24*diffuse))
    faces=array('I')
    for a,b,c,material,owner in model.triangles:
        color=material if isinstance(material,int) else 0x868477
        faces.extend((a,b,c,color))
    return points,faces
