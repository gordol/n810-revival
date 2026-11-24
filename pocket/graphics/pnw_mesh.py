"""Regional wildlife silhouettes with tapered sections and articulated appendages."""
import math
from geometry import Mesh, Triangle, Vec
from pnw_species import group


def study(spec,phase,low=False):
    vertices=[];faces=[]
    form=spec.form
    back,belly,mark=spec.back,spec.belly,spec.mark
    motion=(0.,1.,-.7)[phase]
    sides=8 if low else 22

    def loft(stations,paint):
        start=len(vertices)
        for i,(x,y,z,ry,rz) in enumerate(stations):
            for j in range(sides):
                a=j*math.tau/sides
                vertices.append(Vec(x,y+ry*math.cos(a),z+rz*math.sin(a)))
            if not i:continue
            for j in range(sides):
                a=start+(i-1)*sides+j;b=start+(i-1)*sides+(j+1)%sides
                color=paint(i,(j+.5)*math.tau/sides) if callable(paint) else paint
                faces.extend((Triangle(a,b,a+sides,color,''),Triangle(b,b+sides,a+sides,color,'')))

    def oval(x,y,z,rx,ry,rz,paint):
        steps=5 if low else 12
        loft([(x-rx*math.cos(i*math.pi/steps),y,z,ry*math.sin(i*math.pi/steps),
               rz*math.sin(i*math.pi/steps)) for i in range(steps+1)],paint)

    def limb(a,b,r,t,color):
        ax,ay,az=a;bx,by,bz=b
        dx,dy,dz=bx-ax,by-ay,bz-az
        length=math.sqrt(dx*dx+dy*dy+dz*dz)
        if length==0:return
        dx,dy,dz=dx/length,dy/length,dz/length
        span=math.hypot(dx,dy)
        ux,uy=(-dy/span,dx/span) if span else (1.,0.)
        vx,vy,vz=-dz*uy,dz*ux,dx*uy-dy*ux
        start=len(vertices)
        for (x,y,z),rad in ((a,r),(b,t)):
            for i in range(6):
                u=rad*math.cos(i*math.tau/6);v=rad*math.sin(i*math.tau/6)
                vertices.append(Vec(x+ux*u+vx*v,y+uy*u+vy*v,z+vz*v))
        for i in range(6):
            j=(i+1)%6
            faces.extend((Triangle(start+i,start+j,start+6+i,color,''),Triangle(start+j,start+6+j,start+6+i,color,'')))

    def panel(points,color):
        start=len(vertices);vertices.extend(Vec(*p) for p in points)
        faces.extend(Triangle(start,start+i,start+i+1,color,'') for i in range(1,len(points)-1))

    def coat(i,a):return back if math.cos(a)>-.1 else belly
    kind=group(form)
    if kind=='Birds':
        owl='owl' in form
        water=form in ('duck','merganser')
        tall=form in ('wader','heron')
        height=.43 if tall else .23 if not water else .15
        neck=.25 if form=='heron' else .08 if tall else .0
        hy=height+.16+neck+.017*motion
        hx=.16 if owl else .25
        def plumage(i,a):
            if owl:
                flank=abs(math.sin(a))
                if key_spots and (i+round(a*4))%4==0:return 0xd7ccaf
                if flank>.35 and math.sin(i*2.5+8*math.cos(a))>.50:return mark if form=='owl' and spec.name=='Barred owl' else back
                return belly if math.cos(a)<.15 else back
            if form in ('raven','crow') and math.cos(a)>.35:
                return 0x41434a if i%3==0 else back
            return coat(i,a)
        key_spots=spec.name=='Northern spotted owl'
        oval(-.02,height,0,.27,.19 if owl else .13,.143 if owl or water else .11,plumage)
        limb((.11,height+.04,0),(hx,hy,0),.098,.076,back)
        oval(hx,hy,0,.145 if owl else .10,.135 if owl else .103,.14 if owl else .095,mark if form in ('duck','crested','woodpecker') else back)
        if owl:
            # A forward-facing facial disk surrounding the eyes and a short hooked bill.
            oval(hx+.087,hy,0,.068,.116,.129,belly)
            limb((hx+.14,hy-.009,0),(hx+.17,hy-.045,0),.029,.014,0xb19c72)
            limb((hx+.17,hy-.045,0),(hx+.165,hy-.072,0),.014,.002,0x696046)
        bill=.19 if form in ('heron','kingfisher','hummer','merganser') else .125 if form in ('crow','raven','woodpecker','wader') else .057
        if not owl:limb((hx+.075,hy-.013,0),(hx+.095+bill,hy-.022,0),.034 if not form=='hummer' else .012,.003,0x393737)
        for side in (-1,1):
            eye_x=hx+(.127 if owl else .055)
            eye_z=side*(.078 if owl else .083)
            if owl:
                oval(eye_x-.01,hy,eye_z,.042,.064,.055,belly)
                oval(eye_x+.016,hy+.009,eye_z,.020,.034,.028,0xd0ab60 if form=='tufted owl' else 0x664e38)
            oval(eye_x+(.032 if owl else 0),hy+.015,eye_z,.012,.017,.014,0x212324)
            if not low:
                oval(eye_x+(.043 if owl else .005),hy+.023,eye_z+side*.009,.004,.004,.004,0xdcd9c6)
            if owl:
                limb((eye_x+.027,hy+.039,eye_z*.51),(eye_x+.002,hy+.053,eye_z*1.46),.010,.005,back)
            if form in ('crested','tufted owl','woodpecker','kingfisher'):
                limb((hx-.045,hy+.074,side*.064),(hx-.094,hy+.175,side*.078),.039,.001,mark)
            tail=.34 if form in ('raven','crow','crested','wren','woodpecker') else .20
            for i in range(5):
                z=side*(i+.5)*.013
                limb((-.20,height+.04,z),(-.21-tail+.02*i,height+(.20 if form=='wren' else -.055),z*1.6),.024,.009,back)
            for i in range(6):
                z=side*(.082+.007*i)
                limb((.07,height+.08-.013*i,z),(-.30+.019*i,height+.005-.015*i,z*1.05),.042,.008,mark if i==3 and form in ('finch','songbird','climber') else back)
            foot=(.018,.025,side*.062)
            limb((-.02,height,side*.063),foot,.018,.009,0x665e50)
            for toe in (-1,1):limb(foot,(.09,.007,foot[2]+toe*.025),.009,.002,0x685f50)
    elif kind=='Fish':
        sculpin=form=='sculpin'
        def scales(i,a):
            up=math.cos(a)
            if up>.05 and (i+int(a*8))%5==0:return mark
            return back if up>.03 else belly
        loft([(x,.16,.09*motion*max(0.,-x)**1.4,h,w) for x,h,w in
              [(-.43,.030,.02),(-.30,.049,.03),(-.11,.095,.053),(.13,.105,.089 if sculpin else .057),
               (.27,.077,.097 if sculpin else .055),(.38,.023,.046 if sculpin else .018)]],scales)
        tip=.04*motion
        panel([(-.38,.16,tip),(-.54,.29,tip),(-.5,.16,tip),(-.55,.049,tip)],back)
        panel([(-.13,.245,0),(-.095,.345,0),(.045,.26,0)],back)
        for side in (-1,1):
            oval(.273,.185,side*(.081 if sculpin else .048),.017,.018,.010,0x252620)
            panel([(.15,.14,.042*side),(.05,.075,.14*side),(.07,.15,.07*side)],mark)
    elif form in ('snake','lizard','skink','newt','slug'):
        snake=form=='snake';slug=form=='slug'
        points=[]
        for i in range(22):
            t=i/21
            width=(.058 if snake else .091)*min(1.,.03+4*t, .25+9*(1-t))
            if not snake and not slug:width*=min(1.,.08+2.3*t)
            z=(.09 if snake else .025)*math.sin(t*9+motion*.4)
            points.append((t-.5,width*.76+.008,z,width*.75,width))
        loft(points,lambda i,a:mark if math.cos(a)>.88 and form in ('snake','skink') else coat(i,a))
        hz=points[-1][2]
        oval(.45,.09,hz,.083,.046,.055,back)
        for side in (-1,1):
            ez=hz+side*.038
            if slug:limb((.45,.105,ez),(.51,.17,ez+side*.037),.01,.006,back)
            oval(.48 if not slug else .51,.111 if not slug else .17,ez if not slug else ez+side*.037,.007,.007,.007,0x2d3028)
            if not snake and not slug:
                for x in (-.04,.29):
                    limb((x,.085,side*.05),(x-.03,.035,side*.13),.023,.013,back)
                    limb((x-.03,.035,side*.13),(x+.04,.01,side*.16),.014,.005,back)
    elif form in ('frog','toad'):
        oval(-.05,.12,0,.245,.12,.17,coat)
        oval(.14,.16+motion*.009,0,.17,.095,.175,back)
        for j in range(4):
            bx=-.19+j*.085
            for side in (-1,1):
                oval(bx,.201+.019*math.sin(j),side*.074,.028,.009,.017,mark)
        for side in (-1,1):
            oval(.11,.155,side*.161,.026,.026,.008,mark)
            oval(.19,.23,side*.107,.051,.047,.047,mark)
            oval(.205,.242,side*.141,.034,.029,.019,0xb69c57)
            oval(.216,.246,side*.156,.021,.008,.008,0x302e25)
            for a,b,r,t in [((-.15,.11,.10),(.01,.055,.21),.058,.042),((.01,.055,.21),(-.20,.035,.22),.04,.019),
                            ((.13,.13,.10),(.08,.04,.21),.029,.018),((.08,.04,.21),(.21,.014,.22),.018,.009)]:
                limb((a[0],a[1],a[2]*side),(b[0],b[1],b[2]*side),r,t,back)
    elif kind=='Invertebrates' or form=='bat':
        span=.36 if form=='bee' else .55
        if form=='dragonfly':
            for i in range(10):
                oval(-.44+i*.048,.18,0,.035,.017+.001*i,.02+i*.001,mark if i%3==0 else belly)
        else:oval(-.075,.18,0,.19,.058 if form in ('bee','bat') else .028,.046,coat)
        oval(.10,.19,0,.09,.074,.066,back)
        oval(.19,.19,0,.047,.055,.054,mark)
        for side in (-1,1):
            lift=.16*motion
            for fore in (False,True):
                root=.11 if fore else -.035
                tip=.22 if fore else -.31
                narrow=form=='dragonfly'
                pts=[(root,.20,.03*side),(tip,.23+lift,span*side),((tip-.055 if narrow else tip-.18),.20+lift,span*.89*side),
                     (root-.09,.19,.055*side)]
                panel(pts,0xc6d6cc if narrow or form=='bee' else back)
                for j in range(1,5):
                    t=j/5
                    limb(pts[0],(pts[1][0]*(1-t)+pts[2][0]*t,.225+lift,span*(1-.11*t)*side),.005,.002,mark)
                if form=='swallowtail' and not fore:
                    limb(pts[2],(tip-.25,.19+lift,span*.91*side),.021,.002,back)
            for i in range(3 if form!='bat' else 1):
                limb((.085-i*.055,.155,.025*side),(.104-i*.09,.07,.109*side),.009,.003,mark)
    else:
        ungulate=form in ('deer','elk')
        height=.49 if ungulate else .19 if form in ('weasel','otter','vole','mouse') else .26
        oval(-.04,height,0,.31,.14,.12,coat)
        hy=height+(.25 if ungulate else .08)+.012*motion
        limb((.14,height+.02,0),(.25,hy,0),.109,.074,back)
        oval(.27,hy,0,.14,.086,.084,back)
        oval(.37,hy-.03,0,.078,.054,.055,belly)
        tail=.47 if form in ('otter','weasel','mouse','raccoon','skunk') else .26 if form=='beaver' else .08
        loft([(-.3-tail,height*.48,.017*motion,.009,.009),(-.31-tail*.6,height*.64,0,.023,.065 if form=='beaver' else .028),
              (-.25,height,0,.048,.053)],mark)
        for side in (-1,1):
            oval(.319,hy+.024,side*.071,.014,.015,.012,0x282620)
            ear=.19 if form=='hare' else .10 if ungulate else .043
            limb((.225,hy+.052,side*.047),(.194,hy+.06+ear,side*.063),.030,.006,back)
            for x in (-.21,.15):
                knee=x+(.065 if x<0 else -.018)
                legz=side*.081
                limb((x,height,legz),(knee,height*.49,legz),.053,.030,back)
                limb((knee,height*.49,legz),(x-.028,.036,legz),.03,.018,belly)
                oval(x-.001,.024,legz,.053,.024,.025,mark)
    return Mesh(tuple(vertices),tuple(faces))
