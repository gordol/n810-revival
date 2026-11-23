"""Inspection meshes for Pacific Northwest wildlife. Coordinates are view units."""
import math
from geometry import Mesh, Triangle, Vec, merge
from marmot_art import ellipsoid

NAMES={'marmot':'Hoary marmot','eagle':'Bald eagle','chipmunk':"Townsend's chipmunk",
       'squirrel':'Douglas squirrel','pika':'American pika','goat':'Mountain goat'}


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
    # Elliptical sections run continuously from rump to muzzle.
    return skin([[Vec(x,y+h*math.cos(t),w*math.sin(t)) for t in ANGLES]
                 for x,y,h,w in stations],paint)


ANGLES=tuple(i*math.tau/40 for i in range(40))


def tube(path,color):
    """Fur tails, pinnae and horns taper along a curved centreline in the XY plane."""
    rings=[]
    for i,(x,y,z,r,w) in enumerate(path):
        before,after=path[max(0,i-1)],path[min(len(path)-1,i+1)]
        dx,dy=after[0]-before[0],after[1]-before[1]
        length=math.hypot(dx,dy) or 1
        rings.append([Vec(x-dy/length*r*math.cos(t),y+dx/length*r*math.cos(t),z+w*math.sin(t)) for t in ANGLES])
    return skin(rings,color)


def mammal(species,phase):
    # x, centre height, vertical radius, half breadth, rear to front.
    profiles={
        'marmot':[(-.42,.21,.01,.02),(-.39,.22,.13,.11),(-.29,.235,.195,.156),(-.14,.245,.20,.165),
                  (.015,.26,.18,.15),(.14,.295,.15,.122),(.22,.335,.125,.106),(.29,.338,.105,.102),(.35,.310,.073,.085),(.40,.293,.045,.057),(.417,.295,.014,.036)],
        'chipmunk':[(-.30,.15,.01,.012),(-.27,.165,.082,.061),(-.20,.17,.112,.084),(-.09,.169,.114,.091),
                    (.04,.18,.10,.078),(.13,.21,.079,.065),(.19,.24,.075,.071),(.24,.239,.065,.065),(.30,.216,.039,.048),(.337,.215,.012,.024)],
        'squirrel':[(-.28,.17,.014,.018),(-.26,.185,.105,.08),(-.18,.20,.145,.105),(-.08,.204,.14,.10),
                    (.045,.235,.117,.085),(.13,.272,.092,.073),(.19,.296,.086,.080),(.26,.285,.067,.067),(.31,.257,.036,.047),(.337,.253,.011,.023)],
        'pika':[(-.26,.15,.015,.02),(-.23,.173,.101,.085),(-.16,.183,.14,.116),(-.045,.184,.153,.13),
                (.072,.207,.129,.115),(.145,.224,.115,.103),(.215,.216,.084,.087),(.263,.187,.046,.059),(.283,.187,.014,.032)],
        'goat':[(-.48,.34,.022,.03),(-.44,.35,.119,.09),(-.31,.37,.158,.117),(-.12,.39,.152,.13),
                (.05,.405,.177,.135),(.14,.445,.177,.12),(.23,.478,.128,.091),(.30,.515,.10,.085),(.365,.499,.08,.075),(.428,.46,.056,.055),(.472,.445,.028,.038)]}
    stations=profiles[species]
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
        if species=='marmot' and 3<=i<=6 and d<1.65:return 0xb7b4a8
        if species=='squirrel' and i<6 and 1.47<d<1.66:return 0x423b31
        return belly if d>1.74 else base
    lift=(.0,.025,-.019)[phase]
    stations=[(x,y+lift*max(0,i-3)/6,h,w) for i,(x,y,h,w) in enumerate(stations)]
    parts=[body(stations,coat)]
    def oval(x,y,z,rx,ry,rz,color):
        parts.append(ellipsoid(Vec(x,y,z),(rx,ry,rz),color,'',16,10,True))
    end=stations[-1]
    oval(end[0],end[1]+.002,0,.014,.015,end[3]*.92,0x342d29)
    head=stations[-4];ear=stations[-5];rump=stations[2];shoulder=stations[5]
    for side in (-1,1):
        z=side*head[3]*.90
        oval(head[0]+.012,head[1]+head[2]*.30,z,.018,.019,.011,0x211d18)
        oval(head[0]+.017,head[1]+head[2]*.36,z+side*.009,.004,.004,.002,0xe8e4d8)
        size={'marmot':.033,'chipmunk':.032,'squirrel':.052,'pika':.061,'goat':.052}[species]
        ex,ey,ez=ear[0],ear[1]+ear[2]*.74,side*ear[3]*.65
        oval(ex,ey,ez,size*.7,size,.020,belly if species=='pika' else base)
        oval(ex+.001,ey+.003,ez+side*.013,size*.49,size*.71,.008,0x7b6255)
        for hind,joint in ((True,rump),(False,shoulder)):
            x,y,h,w=joint
            stride=side*(.019 if phase==1 else -.006)*(1 if hind else -1)
            leg_z=side*w*.61
            foot=0x38322c if species in ('goat','marmot') else belly
            knee=x+(.035 if hind else -.023)
            parts.append(tube([(x,y,leg_z,.060 if hind else .037,.042),
                               (knee,.14 if species=='goat' else .075,leg_z,.034,.03),
                               (knee+stride,.035,leg_z,.016,.018)],base))
            oval(knee+stride+.022,.028,leg_z,.034 if species=='goat' else .054,.019,.024,foot)
        if species=='goat':
            parts.append(tube([(ear[0]+.037,ey+.033,ez,.022,.018),(ear[0]+.029,ey+.12,ez,.016,.012),
                               (ear[0]-.004,ey+.19,ez,.008,.007),(ear[0]-.032,ey+.208,ez,.001,.001)],0x3d3832))
    tails={'marmot':[(-.34,.21,.067),(-.43,.135,.068),(-.51,.081,.056),(-.60,.066,.034),(-.66,.061,.003)],
           'chipmunk':[(-.26,.16,.033),(-.36,.20,.043),(-.44,.29,.047),(-.54,.34,.04),(-.64,.35,.018),(-.67,.34,.002)],
           'squirrel':[(-.22,.16,.049),(-.35,.18,.087),(-.43,.30,.112),(-.43,.47,.106),(-.35,.58,.089),(-.23,.59,.068),(-.15,.54,.038),(-.14,.50,.004)],
           'goat':[(-.44,.38,.03),(-.50,.42,.031),(-.535,.45,.008)]}
    if species in tails:
        tail=tails[species]
        parts.append(tube([(x,y+lift*i/len(tail),.012,r,r*.86) for i,(x,y,r) in enumerate(tail)],
                          0x665341 if species=='marmot' else base))
    if species=='goat':
        parts.append(tube([(.37,.447,0,.04,.037),(.35,.375,0,.027,.025),(.32,.32,0,.003,.004)],0xd0c8b5))
    return merge(parts)


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
        parts.append(skin(rings,color))
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
        for j,(z,x) in enumerate([(1.02,.142),(1.10,.075),(1.13,-.014),(1.11,-.114),(1.06,-.208),(.975,-.295),(.875,-.325)]):
            feather((.11-.033*j,.025,side*(.68-.018*j)),(x,-.025,side*z),.050,0x413832 if j%2 else 0x4b4036)
    for j in range(-4,5):
        feather((-.15,.014,j*.011),(-.54+.008*abs(j),.012,j*.043),.043,0xe6e1ce if j%2 else 0xf2eddb)
    parts.append(body([(-.37,.01,.004,.01),(-.24,.015,.074,.083),(-.07,.024,.104,.121),
                       (.07,.037,.102,.101),(.17,.060,.083,.079),(.244,.071,.062,.061),
                       (.30,.060,.046,.048)],lambda i,t:0xece8d9 if i>=4 else 0x584433))
    parts.append(body([(.265,.060,.03,.043),(.315,.060,.034,.043),(.35,.053,.027,.032),
                       (.369,.036,.018,.016),(.362,.014,.004,.004)],0xe6b142))
    for side in (-1,1):
        parts.append(ellipsoid(Vec(.261,.084,side*.052),(.011,.011,.007),0x57452c,''))
    m=merge(parts)
    flap=(-.08,.25,.09)[phase];bank=(.06,-.12,.03)[phase]
    vertices=[]
    for x,y,z in m.vertices:
        y+=flap*max(0,abs(z)-.10)
        vertices.append(Vec(x,y*math.cos(bank)-z*math.sin(bank),y*math.sin(bank)+z*math.cos(bank)))
    return Mesh(tuple(vertices),m.triangles)
