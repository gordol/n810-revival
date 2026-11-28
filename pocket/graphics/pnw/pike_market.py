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

# Shared by the drawn pavement, camera and actors. Local rectangles are
# tessellated on a two-metre grid; interpolate the same diagonal as quad().
FLOORS=((-10,10,-54,-9),(-35,65,-9,-1),(-28,57,-1,9))

def floor_vertex(center,height,u,v):
    raw=height(*offset(center,u,v))
    # The arcade counters stand on one continuous raised slab. Its entrance meets the sloping
    # brick street over the final metres; the unmodified DEM stays underneath.
    across=max(0.,min(1.,(u+28.)/4.,(57.-u)/4.))
    entry=min(1.,max(0.,(v+3.)/4.))
    return raw+.065+across*entry*max(0.,height(*center)-raw)

def floor_height(center,height,x,z):
    dx,dz=x-center[0],z-center[1]
    u,v=C*dx-S*dz,S*dx+C*dz
    for left,right,front,back in FLOORS:
        if left<=u<=right and front<=v<=back:
            u0=left+2*min((right-left-1)//2,int((u-left)//2))
            v0=front+2*min((back-front-1)//2,int((v-front)//2))
            u1,v1=min(right,u0+2),min(back,v0+2)
            a,b=(u-u0)/(u1-u0),(v-v0)/(v1-v0)
            h0=floor_vertex(center,height,u0,v0)
            h2=floor_vertex(center,height,u1,v1)
            if a>=b:
                hm=floor_vertex(center,height,u1,v0)
                return (1-a)*h0+(a-b)*hm+b*h2
            hm=floor_vertex(center,height,u0,v1)
            return (1-b)*h0+(b-a)*hm+a*h2
    return height(x,z)

def arrival(center):
    return *offset(center,0,-38),HEADING,-.16

def rental_site(center):
    return offset(center,4,-36)

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
        wall(left,right,bottom,top,back,color,material)
        panel(((left,top,front),(right,top,front),(right,top,back),(left,top,back)),color,material)
    def stroke(x,y,ex,ey,depth,r,color,material=0.):
        length=math.hypot(ex-x,ey-y)
        dx,dy=r*(ey-y)/length,r*(x-ex)/length
        panel(((x-dx,y-dy,depth),(x+dx,y+dy,depth),
               (ex+dx,ey+dy,depth),(ex-dx,ey-dy,depth)),color,material)
    def lettering(words,x,y,depth,size,color):
        from pnw.market_visit import lettering as typeset
        typeset(words,x,y,depth,size,lambda points,tone:panel(points,tone,.247),color)

    def turned(x,y,z,radius,depth,profile,color,sides=12,material=0.):
        """Bake a ring profile into the same static market mesh as the counter."""
        for j in range(sides):
            a,b=math.tau*j/sides,math.tau*(j+1)/sides
            def rim(t,r,h):return x+radius*r*math.cos(t),y+h,z+depth*r*math.sin(t)
            for (r,h),(rr,hh) in zip(profile,profile[1:]):
                shade=.84+.12*math.cos(a+.6)+.060*(rr<r)
                panel((rim(a,r,h),rim(b,r,h),rim(b,rr,hh),rim(a,rr,hh)),tuple(shade*c for c in color),material)

    def ticket(x,z,y,name):
        wall(x-.19,x+.19,y,y+.18,z,(.72,.11,.075))
        wall(x-.18,x+.18,y+.01,y+.17,z-.004,(.98,.93,.82))
        lettering(name,x-.16,y+.065,z-.008,min(.060,.36/len(name)),(.12,.18,.28))
        block(x-.013,x+.013,y-.13,y,z,z+.018,(.60,.43,.26))

    def merchandise(u,kind):
        title={'produce':"SOSIO'S FRUIT & PRODUCE",'fish':'PURE FOOD FISH','spice':'MarketSpice','cherries':'CHUKAR CHERRIES'}[kind]
        backing={'produce':(.10,.21,.16),'fish':(.17,.19,.20),'spice':(.22,.13,.08),'cherries':(.49,.10,.11)}[kind]
        wall(u-1.76,u+1.76,2.00,2.61,6.36,backing)
        lettering(title,u-1.58,2.16,6.34,min(.32,4./len(title)),(.98,.83,.56))
        if kind in ('spice','cherries'):
            for row in range(3):
                y=1.03+.26*row
                z=4.75+.38*row
                block(u-1.61,u+1.61,1.02,y+.045,z-.18,z+.19,backing)
                for j in range(15):
                    x=u-1.43+.202*j
                    color=((.62,.22,.09),(.43,.24,.09),(.74,.45,.12))[(j//4+row)%3] if kind=='spice' else (.46,.105,.12)
                    turned(x,y+.045,z,.078,.078,((.92,0),(1,.13),(.88,.15),(.94,.16)),color,10)
                    turned(x,y+.201,z,.079,.079,((1,0),(1,.018),(0,.018)),(.79,.68,.44),10)
                    wall(x-.042,x+.042,y+.08,y+.15,z-.078,(.91,.84,.64))
            return
        labels=('Porcini','Chanterelles','Pears','Apples') if kind=='produce' else ('Manila clams','Mussels','Rockfish','Salmon')
        for j,label in enumerate(labels):
            x=u-1.57+.79*j
            block(x,x+.74,1.02,1.12,4.55,5.88,(.27,.32,.22) if kind=='produce' else (.72,.77,.76))
            panel(((x,1.12,4.55),(x+.74,1.12,4.55),(x+.74,1.25,5.88),(x,1.25,5.88)),
                  (.85,.91,.93) if kind=='fish' else (.24,.34,.20))
            for row in range(5):
                for k in range(4):
                    xx=x+.10+.17*k+rng.uniform(-.025,.025)
                    zz=4.69+.22*row+rng.uniform(-.04,.04)
                    y=1.12+.13*(zz-4.55)/1.33
                    if kind=='fish':
                        turned(xx,y-.016,zz,.095,.12,((1,0),(.87,.03),(0,.041)),(.87,.93,.94),7)
                    if kind=='produce':
                        profile=(((.34,0),(.43,.085),(1,.10),(.77,.14),(0,.15)),
                                 ((.23,0),(.35,.065),(.96,.115),(1,.13),(.48,.116),(0,.093)),
                                 ((.29,0),(.78,.016),(.96,.038),(1,.066),(.86,.093),(.53,.126),(.34,.16),(.18,.174),(0,.172)),
                                 ((.38,0),(.70,.012),(.90,.030),(1,.057),(.98,.084),(.85,.110),(.63,.128),(.38,.137),(.17,.133),(0,.123)))[j]
                        tone=((.61,.42,.25),(.94,.56,.15),(.69,.73,.25),(.84,.18,.10))[j]
                        radius=rng.uniform(.077,.095)
                        blush=rng.uniform(.79,1.04)
                        skin=(tone[0]*blush,tone[1]*rng.uniform(.83,1.12),tone[2])
                        turned(xx,y,zz,radius,.081,profile,skin,16,.259)
                        if j>=2 and row%2==1 and k<3:
                            turned(xx+.078,y+.084,zz+.094,radius*.96,.079,profile,skin,16,.259)
                        if j>=2:
                            turned(xx,y+profile[-1][1]-.004,zz,.004,.005,((1,0),(.63,.023),(0,.024)),(.34,.23,.11),6)
                    elif j<2:
                        tone=(.66,.60,.46) if j==0 else (.12,.16,.21)
                        turned(xx,y,zz,.072,.091,((.77,0),(1,.018),(.75,.038),(0,.048)),tone,10)
                    elif k==0:
                        # Fish laid across the length of the tray, with a tapered tail and dark back.
                        tone=(.91,.33,.19) if j==2 else (.56,.66,.70)
                        for a,b in zip((0,.08,.22,.43,.54),(.08,.22,.43,.54,.64)):
                            def section(t,angle):
                                r=.025+.066*math.sin(math.pi*t/.64)**.72
                                return xx+t,y+.035+r*math.sin(angle),zz+r*math.cos(angle)
                            for h in range(10):
                                t=h*math.tau/10
                                panel((section(a,t),section(b,t),section(b,t+.6283),section(a,t+.6283)),
                                      tuple(v*(.80+.18*math.cos(t)) for v in tone))
                        turned(xx+.055,y+.107,zz-.018,.012,.013,((1,0),(.8,.006),(0,.009)),(.09,.10,.10),8)
                        panel(((xx+.57,y+.06,zz),(xx+.69,y+.065,zz-.07),(xx+.66,y+.07,zz),(xx+.69,y+.068,zz+.07)),tone)
            ticket(x+.37,4.64,1.25,label)
        if kind=='produce':
            block(u-.012,u+.012,2.47,3.55,5.08,5.11,(.34,.33,.29))
            for k in range(32):
                a,b=k*math.tau/32,(k+1)*math.tau/32
                def dial(t,r):return u+r*math.cos(t),2.29+r*math.sin(t),5.08
                panel((dial(a,0),dial(a,.19),dial(b,.19),dial(a,0)),(.89,.85,.70))
                if k%2==0:stroke(*dial(a,.14)[:2],*dial(a,.17)[:2],5.075,.006,(.20,.18,.14))
            stroke(u,2.29,u+.08,2.40,5.07,.008,(.62,.15,.10))
            for dx in (-.18,.18):stroke(u,2.10,u+dx,1.78,5.09,.008,(.46,.45,.40))
            turned(u,1.73,5.09,.23,.17,((.55,0),(1,.052),(0,.049)),(.68,.69,.64))

    # A fictional curbside rental stand beside the market entrance.
    pad=floor_height(center,height,*rental_site(center))-level
    wall(3.3,4.8,pad+1.12,pad+1.55,-35.8,(.08,.24,.22))
    lettering('CYCLE HIRE',3.38,pad+1.23,-35.82,.18,(.93,.89,.69))
    block(3.96,4.03,pad,pad+1.12,-35.82,-35.75,(.26,.28,.27))
    for i in range(4):
        u,v=3.15+i*.57,-36.9+i*.16
        bike=i<2
        radius=.32 if bike else .11
        frame=(.18,.47,.34) if bike else (.83,.43,.13)
        for axle in (u-.54,u+.54):
            for k in range(20):
                a,b=k*math.tau/20,(k+1)*math.tau/20
                stroke(axle+radius*math.cos(a),pad+radius*(1+math.sin(a)),
                       axle+radius*math.cos(b),pad+radius*(1+math.sin(b)),v,.026,(.11,.13,.14))
        stroke(u-.54,pad+radius,u,pad+radius,v,.042,frame)
        stroke(u,pad+radius,u+.48,pad+.81,v,.027,frame)
        stroke(u+.54,pad+radius,u+.47,pad+1.04,v,.021,frame)
        block(u+.44,u+.5,pad+1.02,pad+1.06,v-.21,v+.21,(.12,.14,.14))
        if bike:
            stroke(u-.54,pad+radius,u-.16,pad+.84,v,.025,frame)
            stroke(u,pad+radius,u-.16,pad+.84,v,.025,frame)
            stroke(u-.16,pad+.80,u+.48,pad+.81,v,.025,frame)
            block(u-.28,u-.10,pad+.84,pad+.89,v-.075,v+.075,(.15,.13,.11))

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
        if 3<=i<=12:
            # Daylight above the low sill on the opposite side of the aisle.
            wall(u-1.95,u+1.95,1.02,3.19,.30,(.27,.35,.33))
            for pane in range(4):
                left=u-1.88+pane*.95
                wall(left,left+.88,1.10,2.72,.315,(.57,.69,.73),.244)
                wall(left,left+.88,2.77,3.11,.315,(.69,.77,.79),.244)
            block(u-1.92,u+1.92,.89,1.04,.30,.57,(.46,.45,.38))
        wall(u-1.98,u+1.98,.6,2.85,8.65,(.34,.23,.16),.257)
        for y in (1.1,1.74,2.38):
            block(u-1.75,u+1.75,y,y+.09,8.1,8.7,trim,.257)
            for k in range(7):
                xx=u-1.53+.45*k
                top=y+rng.uniform(.29,.49)
                carton=rng.choice(((.51,.28,.12),(.36,.12,.10),(.66,.49,.22),(.25,.36,.23)))
                block(xx,xx+.3,y+.09,top,8.21,8.60,carton)
                wall(xx+.025,xx+.275,y+.12,top-.022,8.203,(.83,.75,.57))
                for line in range(3):
                    yy=y+.145+.028*line
                    wall(xx+.055,xx+.24-line*.018,yy,yy+.009,8.198,carton)
                wall(xx+.04,xx+.26,top-.076,top-.037,8.198,carton)
        wall(u-.38,u+.38,2.8,2.94,3.7,(.99,.84,.54),.247)
        if i==-2:
            wall(u-1.6,u+1.6,2.34,2.95,5.9,(.18,.25,.22))
            lettering('DownUnder',u-1.33,2.45,5.87,.34,(.95,.87,.70))
            continue
        if i in (0,1):continue  # Open passage into the arcade.
        block(u-1.65,u+1.65,.72,1.02,4.5,6,(.25,.29,.24),.257)
        for leg in (-1.47,1.47):
            block(u+leg-.04,u+leg+.04,-1,.72,4.57,4.66,trim,.257)
        block(u-1.61,u+1.61,.28,.32,4.66,5.9,(.36,.32,.24),.257)
        feature={-3:'spice',3:'fish',5:'produce',6:'cherries'}.get(i)
        if feature:
            merchandise(u,feature)
            continue
        if i in (-1,2):
            flowers=i==-1
            sign='FLOWERS' if flowers else 'HONEY'
            wall(u-1.2,u+1.2,1.82,2.27,6.15,(.21,.34,.25))
            lettering(sign,u-1.,1.87,6.13,.31,(.98,.92,.74))
            for j in range(8 if flowers else 16):
                x=u-1.28+(j%8)*.36
                z=4.85+(j//8)*.40
                r=.13 if flowers else .087
                for k in range(10):
                    a,b=k*math.tau/10,(k+1)*math.tau/10
                    ax,az=x+r*math.cos(a),z+r*math.sin(a)
                    bx,bz=x+r*math.cos(b),z+r*math.sin(b)
                    top=1.29 if flowers else 1.21
                    shade=.78+.18*math.cos(a)
                    tone=(.45,.53,.50) if flowers else (.90,.48,.09)
                    panel(((ax,1.02,az),(bx,1.02,bz),(bx,top,bz),(ax,top,az)),tuple(c*shade for c in tone))
                    panel(((ax,top,az),(bx,top,bz),(x,top,z),(x,top,z)),(.32,.39,.34) if flowers else (.83,.71,.39))
                if flowers:
                    # Folded florist paper flares out above the lip of each bucket.
                    for fold in range(8):
                        a,b=fold*math.tau/8,(fold+1)*math.tau/8
                        def wrap(t,r,h):return x+r*math.cos(t),h,z+r*math.sin(t)
                        panel((wrap(a,.08,1.23),wrap(b,.08,1.23),
                               wrap(b,.177,1.44+.07*((fold+1)%2)),wrap(a,.177,1.44+.07*(fold%2))),
                              (.94,.91,.82) if fold%2 else (.84,.83,.78))
                    for k in range(9):
                        theta=k*2.40+j
                        ex=x+.16*math.cos(theta)
                        ez=z+.15*math.sin(theta)
                        ey=1.53+.08*math.sin(k*1.7)
                        panel(((x-.008,1.25,z),(x+.008,1.25,z),(ex+.008,ey,ez),(ex-.008,ey,ez)),(.21,.39,.16))
                        for petal in range(6):
                            a=petal*math.tau/6
                            dx,dz=.059*math.cos(a),.059*math.sin(a)
                            panel(((ex,ey,ez),(ex+dx*.55-dz*.40,ey+.011,ez+dz*.55+dx*.40),
                                   (ex+dx,ey+.025,ez+dz),(ex+dx*.55+dz*.40,ey+.011,ez+dz*.55-dx*.40)),
                                  ((.86,.26,.43),(.94,.71,.23),(.80,.54,.84))[j%3])
            continue
        for k,tone in enumerate(((.76,.33,.12),(.49,.58,.19),(.80,.58,.16))):
            xx=u-1.6+k
            block(xx,xx+.92,1.02,1.12,4.56,5.78,(.51,.37,.21))
            for _ in range(18):
                cx,cz=xx+rng.uniform(.09,.83),rng.uniform(4.66,5.67)
                r=rng.uniform(.065,.12)
                y=1.13+r*.4
                panel(((cx-r,y,cz),(cx,y+r,cz-.04),(cx+r,y,cz),(cx,y-r,cz+.04)),tone)
    # Freestanding directory faces the arriving visitor beside the entrance.
    block(-3.03,-2.97,0,1.08,-1.90,-1.80,trim)
    block(-3.73,-2.27,1.,1.96,-1.94,-1.83,(.22,.30,.27))
    lettering('Directory',-3.60,1.66,-1.95,.21,(.99,.91,.70))
    for j in range(3):
        wall(-3.58,-2.92+.16*(j%2),1.48-.14*j,1.51-.14*j,-1.95,(.80,.75,.57))
        wall(-2.78,-2.44,1.48-.14*j,1.51-.14*j,-1.95,(.67,.76,.70))
    # Pendant globes and the surviving Loback sign seen down the Main Arcade.
    # Two continuous sloping soffits carry the warm lamps on either side of the aisle.
    panel(((-28,3.53,1.02),(57,3.53,1.02),(57,3.53,4.20),(-28,3.53,4.20)),(.83,.74,.61),.258)
    for z,direction in ((1.02,-1),(4.20,1)):
        lip=z+.48*direction
        panel(((-28,3.53,z),(57,3.53,z),(57,3.22,lip),(-28,3.22,lip)),(.84,.73,.55),.258)
        for n in range(71):
            u=-27.6+n*1.19
            turned(u,3.26,z+.31*direction,.048,.048,((.35,0),(1,.037),(.73,.075)),(.96,.85,.64),8)
            wall(u-.036,u+.036,3.283,3.33,z+.31*direction-.045,(1.,.91,.69),.247)
    for u in range(-26,57,2):
        turned(u,2.85,5.15,.18,.18,((1,0),(.83,.052),(.28,.125),(.22,.14)),(.19,.25,.22))
        block(u-.012,u+.012,2.99,3.55,5.14,5.16,iron)
        panel(((u-.12,2.85,5.06),(u+.12,2.85,5.06),(u+.12,2.85,5.24),(u-.12,2.85,5.24)),(1.,.92,.75),.247)
    for u in range(-24,54,4):
        block(u-.018,u+.018,2.96,3.55,2.67,2.71,iron)
        for k in range(12):
            a,b=k*math.tau/12,(k+1)*math.tau/12
            def bulb(t,r,y):return u+r*math.cos(t),y,2.69+r*math.sin(t)
            panel((bulb(a,.10,2.65),bulb(b,.10,2.65),bulb(b,.21,2.82),bulb(a,.21,2.82)),(.96,.84,.59),.247)
            panel((bulb(a,.21,2.82),bulb(b,.21,2.82),bulb(b,.09,2.99),bulb(a,.09,2.99)),(.96,.86,.65),.247)
    block(-12,-11.87,2.55,3.4,.30,4.35,(.16,.13,.11))
    from pnw.market_visit import lettering as sign_text
    def sign_panel(points,color):
        panel(tuple((-11.86-z,y,.48+x) for x,y,z in points),color,.247)
    def viewpoint_panel(points,color):
        panel(tuple((6.03-z,y,1.2+x) for x,y,z in points),color,.247)
    block(5.91,6.00,2.61,3.42,1.02,4.25,(.16,.20,.24))
    sign_text('WATERFRONT',0,3.04,0,.27,viewpoint_panel,(.55,.69,1.))
    sign_text('VIEWPOINT',.17,2.78,0,.22,viewpoint_panel,(.58,.72,1.))
    # Visitors approach the hanging signs along the arcade from either end.
    def reverse_sign(x,right,words,y,size,tone):
        sign_text(words,0,y,0,size,lambda pts,c:panel([(x+z,h,right-u) for u,h,z in pts],c,.247),tone)
    reverse_sign(5.90,4.12,'WATERFRONT',3.04,.27,(.55,.69,1.))
    reverse_sign(5.90,3.95,'VIEWPOINT',2.78,.22,(.58,.72,1.))
    reverse_sign(5.90,3.72,'& PUBLIC SEATING',2.63,.115,(.68,.78,1.))
    sign_text('& PUBLIC SEATING',.48,2.63,0,.115,viewpoint_panel,(.68,.78,1.))
    block(15.9,16.,2.43,3.48,1.45,3.65,(.11,.105,.13))
    for words,y,size,tone in (("LOWELL'S",3.16,.25,(1.,.70,.16)),('RESTAURANT',2.94,.17,(.96,.93,.86)),
                              ('COCKTAILS',2.74,.16,(1.,.21,.27)),('WATER VIEW',2.54,.16,(.39,.57,1.))):
        reverse_sign(15.88,3.50,words,y,size,tone)
        sign_text(words,0,y,0,size,lambda pts,c:panel([(16.02-z,h,1.55+x) for x,h,z in pts],c,.247),tone)
    sign_text('QUALITY ALWAYS',.69,2.64,0,.14,sign_panel,(1.,.58,.33))
    sign_text('LOBACK MEAT CO',0,2.86,0,.31,sign_panel,(.95,.35,.18))
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
    wall(.43,5.98,2.53,2.93,6.84,(.82,.79,.63))
    lettering('PIKE PLACE FISH CO.',.57,2.56,6.81,.32,(.18,.24,.21))
    lettering('We pack fish to keep fresh',.84,2.39,6.81,.12,(.89,.85,.67))
    for i,label in enumerate(('Oysters','Salmon','Crab','Halibut','Prawns')):
        x=1.23+i*.72
        lettering(label,x+.01,1.048,4.709,.043,(.24,.18,.14))
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
            for y in ((4.4,) if side>0 else (4.4,7.5)):
                shopfront(y,y+1.66,v+.38,v+2.41,.065,(.27,.30,.28))
                shopfront(y+.13,y+1.18,v+.49,v+2.29,.085,(.37,.42,.40),.244)
            if side>0 or v<-10:
                cloth=(.27,.37,.30) if side>0 else (.51,.25,.19)
                u=edge-side*1.4
                panel(((edge,3.67,v),(u,3.15,v),(u,3.15,v+3),(edge,3.67,v+3)),cloth)
                shopfront(2.95,3.15,v,v+3,1.4,cloth)
        block(min(edge,outer)-.2,max(edge,outer)+.2,top,top+.22,-27.23,1.23,trim)
    # Corner Market has a five-bay gable on Pike Street. The arched
    # sash and brick spandrels repeat around the corner facing Pike Place.
    stone=(.76,.72,.62)
    sash=(.45,.25,.18)
    for front,bays,width in ((True,5,3.7),(False,9,3.1)):
        def facade(u,y,offset):
            return (8.5+u,y,-27.-offset) if front else (8.5-offset,y,-27.+u)
        def span(a,b,y,h,offset,tone,material=0.):
            panel((facade(a,y,offset),facade(b,y,offset),facade(b,h,offset),facade(a,h,offset)),tone,material)
        for j in range(bays):
            u=(j+.5)*width
            r=width*.38
            crest=11.98+(1.25*max(0.,1.-abs(j-2)*.5) if front else 0.)
            span(u-width*.5,u+width*.5,6.35,crest,.12,(.54,.29,.20),.251)
            span(u-width*.5,u-width*.5+.18,3.5,crest,.14,stone)
            span(u-width*.5,u+width*.5,6.47,7.03,.16,stone)
            span(u-r,u+r,7.34,8.30,.17,(.28,.39,.44),.244)
            for k in range(16):
                a,b=k*math.pi/16,(k+1)*math.pi/16
                def arch(t,rad,d):return facade(u+rad*math.cos(t),8.30+rad*math.sin(t),d)
                panel((facade(u,8.30,.17),arch(a,r,.17),arch(b,r,.17),facade(u,8.30,.17)),(.28,.39,.44),.244)
                panel((arch(a,r,.18),arch(a,r+.17,.18),arch(b,r+.17,.18),arch(b,r,.18)),stone)
            for frac in (-.53,0,.53):
                span(u+r*frac-.028,u+r*frac+.028,7.34,8.3+r*math.sqrt(1-frac*frac),.19,sash)
            span(u-r,u+r,8.24,8.30,.19,sash)
            if front:
                span(u-r,u+r,4.15,6.03,.16,(.28,.36,.38),.244)
                span(u-.04,u+.04,4.15,6.03,.18,sash)
            for stripe in range(8):
                a=(j+stripe/8)*width;b=a+width/8
                cloth=(.89,.88,.75) if stripe%2 else (.10,.38,.32)
                panel((facade(a,3.68,.13),facade(b,3.68,.13),facade(b,3.16,1.43),facade(a,3.16,1.43)),cloth)
                span(a,b,2.94,3.16,1.43,cloth)
    wall(8.5,27.,6.32,7.05,-27.22,stone)
    lettering('CORNER MARKET',12.25,6.40,-27.24,.52,sash)
    # The clock and lettering rise from the roof behind the entrance fascia.
    for x in (-6.,-2.,2.,6.):
        stroke(x,4.05,x,13.9,2.5,.058,iron)
        panel(((x-.085,4.05,6),(x+.085,4.05,6),(x+.085,13.9,2.5),(x-.085,13.9,2.5)),iron)
    for y in (4.3,7.3,10.4,13.6):
        stroke(-6,y,6,y,2.5,.056,iron)
    for x in (-6,-2,2):
        stroke(x,4.3,x+4,10.4,2.5,.046,iron)
        stroke(x+4,10.4,x,13.6,2.5,.046,iron)
    def neon(words,x,y,z,size):
        from pnw.market_visit import sign_art
        glyphs=sign_art()['glyphs']
        width=sum(glyphs[c][0] for c in words)
        sx=min(size/200,len(words)*size*.8/width)
        for c in words:
            advance,paths=glyphs[c]
            for path in paths:
                pts=[(x+u*sx,y+v*size/200) for u,v in zip(path[::2],path[1::2])]
                for a,b in zip(pts,pts[1:]+pts[:1]):
                    if a!=b:stroke(*a,*b,z,.020*size,(1.,.38,.17),.247)
            x+=advance*sx
    lettering('PUBLIC',-4.95,11.05,2.32,2.22,(.49,.055,.055))
    neon('PUBLIC',-4.95,11.05,2.28,2.22)
    lettering('MARKET',-6.15,8.05,2.32,2.08,(.49,.055,.055))
    neon('MARKET',-6.15,8.05,2.28,2.08)
    lettering('CENTER',-4.98,5.03,2.32,2.22,(.49,.055,.055))
    neon('CENTER',-4.98,5.03,2.28,2.22)
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
    lettering('FARMERS MARKET',-5.26,3.73,-1.45,1.,(.49,.055,.055))
    neon('FARMERS MARKET',-5.26,3.73,-1.48,1.)
    for y in (3.67,4.82):stroke(-6.55,y,7.05,y,-1.46,.021,(1.,.27,.12),.247)
    # The cross street stays open along the arcade, including its north end.
    for left,right,front,back in FLOORS:
        for v in range(front,back,2):
            for u in range(left,right,2):
                pts=[]
                for du,dv in ((0,0),(2,0),(2,2),(0,2)):
                    x,z=offset(center,min(right,u+du),min(back,v+dv))
                    pts.append((x,floor_vertex(center,height,min(right,u+du),min(back,v+dv)),z))
                if front<-1:quad(pts,(.43,.37,.32),.237)
                else:quad(pts,(.65,.48,.34),.256)
