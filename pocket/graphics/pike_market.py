"""Original street-scale interpretation of the Pike Street entrance.

Reference: Pike Place Market PDA, 2021 press kit, cover photograph.
The frame faces down Pike Street; the Main Arcade runs across the approach.
Dimensions and colors are visual estimates in metres.
"""
import math
import random

HEADING=math.radians(-122)
S,C=math.sin(HEADING),math.cos(HEADING)

def offset(center,right,forward):
    return center[0]+C*right+S*forward,center[1]-S*right+C*forward

def arrival(center):
    return *offset(center,0,-38),HEADING,-.16

# Connected strokes in a 4 by 6 grid, from the bottom left of each letter.
GLYPHS={
    'H':('0006','4046','0343'),
    'P':('00063645443303',),'U':('060111314146',),'B':('000636455433034241303000',),
    'L':('060040',),'I':('0646','2620','0040'),'C':('4536160501113141',),
    'M':('0006234640',),'A':('002640','1232'),'R':('00063645543303','2340'),
    'K':('0006','0346','1340'),'E':('46060040','0333'),'T':('0646','2620'),
    'D':('000626453541204000',),'O':('113141453616050111',),
    '0':('113141453616050111',),'1':('15262620','1040'),
    '2':('0516364544030040',),'3':('063645443323334241303000',),
    '4':('3603134330','0333'),'5':('460603334241303000',),'6':('3646160501113141423303',),
    '7':('064620',),'8':('1131414233130405163645443313020111',),
    '9':('4131160505163645413030',),
    'N':('00064046',),'F':('000646','0333'),'S':('453616050413334241303000',),
}

def build(center,height,quad):
    level=height(*center)
    def point(u,y,v):
        x,z=offset(center,u,v)
        return x,level+y,z
    def panel(points,color,material=0.):
        quad([point(*p) for p in points],color,material)
    def wall(left,right,bottom,top,depth,color,material=0.):
        panel(((left,bottom,depth),(right,bottom,depth),(right,top,depth),(left,top,depth)),color,material)
    def block(left,right,bottom,top,front,back,color,material=0.):
        wall(left,right,bottom,top,front,color,material)
        for side,shade in ((left,.68),(right,.80)):
            panel(((side,bottom,front),(side,bottom,back),(side,top,back),(side,top,front)),
                  tuple(c*shade for c in color),material)
        wall(left,right,bottom,top,back,color)
        panel(((left,top,front),(right,top,front),(right,top,back),(left,top,back)),color)
    def stroke(x,y,ex,ey,depth,r,color,material=0.):
        length=math.hypot(ex-x,ey-y)
        dx,dy=r*(ey-y)/length,r*(x-ex)/length
        panel(((x-dx,y-dy,depth),(x+dx,y+dy,depth),
               (ex+dx,ey+dy,depth),(ex-dx,ey-dy,depth)),color,material)
    def lettering(words,x,y,depth,size,color):
        for i,letter in enumerate(words):
            for path in GLYPHS.get(letter,()):
                pts=[(x+size*(i*.81+int(path[j])/6),y+size*int(path[j+1])/6)
                     for j in range(0,len(path),2)]
                for a,b in zip(pts,pts[1:]):
                    if a!=b:
                        stroke(*a,*b,depth,size*.077,tuple(v*.50 for v in color))
                        stroke(*a,*b,depth-.018,size*.045,color,.247)

    iron=(.16,.19,.18)
    trim=(.28,.34,.31)
    red=(.96,.075,.055)
    # A continuous sheltered arcade intersects the approach at its foot.
    block(-28,57,-5,3.5,8.8,17,(.18,.135,.10))
    block(-28,57,3.55,4.05,-1.,16,(.36,.40,.36))
    wall(-28,57,3.38,3.68,-1.08,(.74,.69,.52))
    rng=random.Random(1937)
    for i in range(-7,15):
        u=i*4.
        block(u-.12,u+.12,-2,3.6,-.95,-.70,trim)
        wall(u-1.98,u+1.98,.6,2.85,8.65,(.34,.23,.16))
        for y in (1.1,1.74,2.38):
            block(u-1.75,u+1.75,y,y+.09,8.1,8.7,trim)
            for k in range(7):
                xx=u-1.53+.45*k
                block(xx,xx+.3,y+.09,y+rng.uniform(.25,.51),8.21,8.60,
                      rng.choice(((.68,.48,.25),(.51,.31,.22),(.76,.62,.39))))
        wall(u-.38,u+.38,2.8,2.94,3.7,(.99,.84,.54),.247)
        if i in (0,1):continue  # Open passage into the arcade.
        block(u-1.65,u+1.65,-1,1.02,4.5,6,(.44,.29,.16))
        for k,tone in enumerate(((.76,.33,.12),(.49,.58,.19),(.80,.58,.16))):
            xx=u-1.6+k
            block(xx,xx+.92,1.02,1.12,4.56,5.78,(.51,.37,.21))
            for _ in range(18):
                cx,cz=xx+rng.uniform(.09,.83),rng.uniform(4.66,5.67)
                r=rng.uniform(.065,.12)
                y=1.13+r*.4
                panel(((cx-r,y,cz),(cx,y+r,cz-.04),(cx+r,y,cz),(cx,y-r,cz+.04)),tone)
    # The OSM shop point registers this bay. A front ice bed faces the
    # customers, with a separate wrapping counter behind the fishmongers.
    # The operator's counter photograph shows hanging enamel lamps, green
    # overhead beams, and small upright product cards across sloping ice.
    for z in (1.5,4.6,7.5):
        block(-2.1,7.2,3.32,3.54,z,z+.19,(.19,.29,.24))
    for u,v in ((.55,2.9),(2.4,4.85),(4.85,3.45),(5.6,6.65)):
        block(u-.017,u+.017,2.98,3.51,v-.017,v+.017,iron)
        for j in range(16):
            a,b=j*math.tau/16,(j+1)*math.tau/16
            panel(((u+.035*math.cos(a),2.99,v+.035*math.sin(a)),
                   (u+.035*math.cos(b),2.99,v+.035*math.sin(b)),
                   (u+.28*math.cos(b),2.74,v+.28*math.sin(b)),
                   (u+.28*math.cos(a),2.74,v+.28*math.sin(a))),(.67,.70,.63))
            panel(((u,2.735,v),(u+.28*math.cos(a),2.735,v+.28*math.sin(a)),
                   (u+.28*math.cos(b),2.735,v+.28*math.sin(b)),(u,2.735,v)),(.99,.93,.78),.247)
    block(.9,4.65,-1,.82,4.42,5.47,(.27,.34,.34))
    block(.88,4.68,.82,.96,4.41,5.51,(.83,.88,.86))
    for i in range(9):
        u=1.12+i*.39
        for left,right in ((-.11,.09),(.09,.18)):
            panel(((u+left,.98,4.54),(u+right,1.06,4.88),(u+.04,.98,5.27),(u-.03,.96,4.96)),
                  (.45,.54,.51) if left<0 else (.66,.71,.66))
    for i in range(5):
        x=1.23+i*.72
        wall(x,x+.24,.98,1.20,4.73,(.98,.91,.74))
        wall(x+.025,x+.20,1.12,1.15,4.72,(.29,.24,.20))
    block(1.4,5.6,-1,1.,6.9,7.8,(.48,.40,.32))
    wall(.4,6.,2.37,2.96,6.85,(.24,.22,.18))
    lettering('PIKE PLACE FISH',.64,2.46,6.81,.40,(.93,.85,.68))
    # Cream masonry walls, bay windows, lintels and projecting cornices.
    for left,right,front,floors,color in ((-29,-7,5.,4,(.69,.67,.57)),
                                         (6.6,32,3.2,3,(.68,.62,.50))):
        top=4.1+3.05*floors
        block(left,right,3.85,top,front,front+13,color,.241)
        for dy,overhang in ((0,.32),(.34,.55)):
            block(left-overhang,right+overhang,top+dy,top+dy+.2,front-overhang,front+13,trim)
        bays=round((right-left)/3.5)
        for i in range(bays):
            u=left+(i+.5)*(right-left)/bays
            for row in range(floors):
                y=4.6+3.05*row
                wall(u-.81,u+.81,y,y+1.98,front-.06,(.21,.23,.21))
                wall(u-.68,u+.68,y+.12,y+1.85,front-.09,(.26+.025*(i%3),.34,.35),.244)
                wall(u-.045,u+.045,y+.1,y+1.9,front-.12,trim)
                wall(u-.72,u+.72,y+1.12,y+1.20,front-.12,trim)
                block(u-.95,u+.95,y-.12,y,front-.23,front,color)
    block(6.9,25.5,13.72,14.92,3.22,3.53,(.14,.39,.36))
    lettering('MEET THE PRODUCER',7.65,13.88,3.16,.87,(.83,.88,.76))
    # Hanging baskets break the long canopy edge. Drooping stems cluster
    # around each bowl, with shade under the foliage and blooms at the tips.
    for i in (-6,-4,-2,2,4,6,9,12):
        u=i*3.75
        wall(u-.022,u+.022,2.56,3.52,-1.46,iron)
        for j in range(38):
            a=rng.random()*math.tau
            r=.63*math.sqrt(rng.random())
            du,dv=r*math.cos(a),r*math.sin(a)
            x=u+du
            y=2.65-r*.33-rng.random()*.35
            z=-1.46+dv
            panel(((u,2.67,-1.46),(x-.12,y,z),(x,y-.16,z),(x+.12,y,z)),
                  rng.choice(((.19,.34,.14),(.27,.42,.17),(.22,.38,.15))))
            if j%3:
                wall(x-.065,x+.065,y-.16,y-.04,z-.07,
                     rng.choice(((.78,.16,.30),(.91,.49,.54),(.63,.18,.44))))
    # Rounded street edges from cross-sections of Seattle's 2023 building
    # outlines near Pike Street. Storefronts face into the approach.
    for edge,outer,color,top in ((-15.,-28.,(.57,.38,.28),9.6),
                                 (8.5,27.,(.72,.63,.50),11.8)):
        side=1 if edge>0 else -1
        block(min(edge,outer),max(edge,outer),-3,top,-27,1.,color,.241)
        for v in range(-25,1,3):
            def shopfront(y0,y1,near,far,inset,tone,material=0.):
                u=edge-side*inset
                panel(((u,y0,near),(u,y0,far),(u,y1,far),(u,y1,near)),tone,material)
            shopfront(.12,2.8,v,v+2.73,.055,(.20,.27,.27))
            shopfront(.86,2.65,v+.16,v+2.54,.085,(.33,.42,.42),.244)
            shopfront(.91,2.68,v+1.27,v+1.34,.11,trim)
            for y in (4.4,7.5):
                shopfront(y,y+1.66,v+.38,v+2.41,.065,(.27,.30,.28))
                shopfront(y+.13,y+1.18,v+.49,v+2.29,.085,(.37,.42,.40),.244)
            if side>0 or v<-10:
                cloth=(.27,.37,.30) if side>0 else (.51,.25,.19)
                u=edge-side*1.4
                panel(((edge,3.67,v),(u,3.15,v),(u,3.15,v+3),(edge,3.67,v+3)),cloth)
                shopfront(2.95,3.15,v,v+3,1.4,cloth)
        block(min(edge,outer)-.2,max(edge,outer)+.2,top,top+.22,-27.23,1.23,trim)
    # The clock and lettering rise from the roof behind the entrance fascia.
    for x in (-6.,-2.,2.,6.):
        stroke(x,4.05,x,13.9,2.5,.058,iron)
        panel(((x-.085,4.05,6),(x+.085,4.05,6),(x+.085,13.9,2.5),(x-.085,13.9,2.5)),iron)
    for y in (4.3,7.3,10.4,13.6):
        stroke(-6,y,6,y,2.5,.056,iron)
    for x in (-6,-2,2):
        stroke(x,4.3,x+4,10.4,2.5,.046,iron)
        stroke(x+4,10.4,x,13.6,2.5,.046,iron)
    lettering('PUBLIC',-4.95,11.05,2.32,2.22,red)
    lettering('MARKET',-6.15,8.05,2.32,2.08,red)
    lettering('CENTER',-4.98,5.03,2.32,2.22,red)
    cx,cy=4.45,9.27
    for j in range(60):
        a,b=j*math.tau/60,(j+1)*math.tau/60
        def rim(t,r):return cx+r*math.sin(t),cy+r*math.cos(t)
        panel(((cx,cy,2.2),(*rim(a,1.78),2.2),(*rim(b,1.78),2.2),(cx,cy,2.2)),(.94,.91,.82))
        stroke(*rim(a,1.78),*rim(b,1.78),2.14,.061,red)
        if j%5==0:stroke(*rim(a,1.29),*rim(a,1.57),2.1,.07,red)
    for hour in range(1,13):
        a=hour*math.tau/12
        number=str(hour)
        lettering(number,cx+1.20*math.sin(a)-.12*len(number),
                  cy+1.20*math.cos(a)-.18,2.07,.36,red)
    for dx,dy in ((-.50,.66),(.83,.39)):stroke(cx,cy,cx+dx,cy+dy,2.08,.085,red)
    block(-6.8,7.3,3.50,4.98,-1.35,-.71,(.21,.33,.29))
    wall(-6.61,7.11,3.62,4.87,-1.39,(.94,.89,.71))
    lettering('FARMERS MARKET',-5.26,3.73,-1.45,1.,red)
    # The cross street stays open along the arcade, including its north end.
    for left,right,front,back in ((-10,10,-54,-9),(-35,65,-9,-1)):
        for v in range(front,back,2):
            pts=[]
            for u,dv in ((left,0),(right,0),(right,2),(left,2)):
                x,z=offset(center,u,min(back,v+dv))
                pts.append((x,height(x,z)+.065,z))
            quad(pts,(.43,.37,.32),.237)
