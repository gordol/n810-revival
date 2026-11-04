"""Bounded deterministic cell effects. No per-particle tasks or retained history."""
import math
from paint import ink, Scene, inherit_background, shade_ink
from weather import detail_budget, wind_field
from functools import lru_cache

NAMES = ('matrix','rain','snow','leaves','flowers','flux','pnw','terrain','flurry')


def sample(index,seed=0,channel=0):
    """Independent stable 32-bit channels, avoiding viewport-modulo seed lattices."""
    value=(index+seed*0x9e3779b9+channel*0x85ebca6b)&0xffffffff
    value=((value^(value>>16))*0x7feb352d)&0xffffffff
    value=((value^(value>>15))*0x846ca68b)&0xffffffff
    return ((value^(value>>16))&0xffffffff)/4294967296


@lru_cache(maxsize=16)
def seasonal_plan(name,width,height,seed):
    count=min(192,max(8,detail_budget(width,height)//4))
    return tuple(((i+sample(i,seed,1))*width/count,
                  sample(i,seed,2)*(height+8),
                  (.75+sample(i,seed,3))*(.55 if name in ('snow','flowers') else 1),
                  -1 if sample(i,seed,4)<.5 else 1,
                  .15+sample(i,seed,5)*.7,
                  1+sample(i,seed,6)*3,2+i%4,sample(i,seed,7)*math.tau)
                 for i in range(count))


@lru_cache(maxsize=16)
def matrix_plan(width,height,seed):
    count=min(12,max(1,width//9))
    return tuple((min(width-1,int((i+.2+.6*sample(i,seed,1))*width/count)),
                  sample(i,seed,3)*(height+12),.6+sample(i,seed,4)*.8,
                  int(sample(i,seed,2)*100000)) for i in range(count))


def frame(name, width, height, step, ascii=False, weather=None, seed=0, nature_age=None, flurry_strands=48, flurry_sway=.6, flurry_speed=1.0, flux_density=1.0, flux_glow=.15, flux_arms=2,flurry_provider=None):
    """Return bounded cells as (glyph, palette-role) pairs."""
    if name == 'flurry':
        if flurry_provider is not None:return flurry_provider.frame(width,height,step,ascii,seed,flurry_strands,flurry_sway,flurry_speed)
        from flurry import frame as flurry_frame
        return flurry_frame(width,height,step,ascii,seed,flurry_strands,flurry_sway,flurry_speed)
    if name == 'terrain':
        from model_scene import frame as model_frame
        return model_frame(width,height,ascii,step/6 if nature_age is None else nature_age)
    if name == 'pnw': return pnw(width,height,step,ascii,weather,seed,nature_age)
    cells = {}
    if name == 'flux':
        from flux import frame as flux_frame
        return flux_frame(width,height,step,ascii,flux_density,flux_glow,flux_arms)
    elapsed=step/6
    for i,(origin,phase,speed,direction,drift,amplitude,period,angle) in enumerate(seasonal_plan(name,width,height,seed)):
        y=int(elapsed*speed+phase)%(height+8)
        if name=='rain':x=origin+elapsed*.2
        else:
            sway=amplitude*math.sin(elapsed/period+angle)
            x=origin+direction*elapsed*drift+sway
        if weather:
            phase_angle=origin/40+phase/25
            travel=.65*elapsed+.35/.7*(math.cos(phase_angle)-math.cos(.7*elapsed+phase_angle))
            x+=weather.wind_x*travel
            y=int(elapsed*speed+phase+weather.wind_y*travel)%(height+8)
        x=int(x)%width
        if y>=height:continue
        if name == 'rain':
            for age in range(2):
                if y-age >= 0: cells[x,y-age] = ('|' if ascii else '│',9)
        elif name == 'snow': cells[x,y] = ('.' if ascii else ('·','*')[i%5 == 0],5 if i%3 else 0)
        elif name == 'leaves': cells[x,y] = (('~','/','\\')[(int(elapsed*speed)+i)%3],8)
        elif name == 'flowers': cells[x,y] = ('*' if ascii else ('✿','❀','·')[i%3],7 if i%2 else 8)
        else: raise ValueError('unknown effect')
    return cells


@lru_cache(maxsize=8)
def mountain(width, height):
    """Sparse cached ridge and glacier marks, inspired by Rainier's broad summit."""
    ridge = ((0,.80),(.20,.73),(.34,.50),(.44,.25),(.49,.23),
             (.52,.27),(.55,.25),(.63,.54),(.76,.74),(1,.82))
    points = []
    samples = min(width,128)
    for i in range(samples):
        u = i/max(1,samples-1)
        left,right = next(((a,b) for a,b in zip(ridge,ridge[1:]) if a[0] <= u <= b[0]), (ridge[-2],ridge[-1]))
        fraction = (u-left[0])/(right[0]-left[0])
        v = left[1]+fraction*(right[1]-left[1])
        x,y = round(u*(width-1)),round(v*(height-1))
        glyph = '/' if right[1] < left[1] else '\\' if right[1] > left[1] else '_'
        points.append(((x,y),(glyph,10 if .33 < u < .65 else 9)))
        if .39 < u < .62 and i%2 == 0 and y+2 < height:
            points.append(((x,y+2),('_',10)))
    return tuple(points)


@lru_cache(maxsize=16)
def forest(width,height,seed):
    count=min(7,max(2,width//12))
    return tuple((round((i+.25+.5*sample(i,seed,11))*width/count),
                  height-1-int(sample(i,seed,12)*2),
                  min(5,max(2,height//4))+int(sample(i,seed,13)*2),
                  sample(i,seed,14)*math.tau,sample(i,seed,15)) for i in range(count))


def ridge_profile(u):
    ridge=((0,.80),(.20,.73),(.34,.50),(.44,.25),(.49,.23),(.52,.27),(.55,.25),(.63,.54),(.76,.74),(1,.82))
    left,right=next(((a,b) for a,b in zip(ridge,ridge[1:]) if a[0]<=u<=b[0]),(ridge[-2],ridge[-1]))
    return left[1]+(u-left[0])/(right[0]-left[0])*(right[1]-left[1])


@lru_cache(maxsize=4)
def painted_landscape(width,height,seed,light,season,ascii=False,light_side=1):
    """Filled elevation planes; RGB565 shading sampled twice per terminal row."""
    cells={}
    stride=max(1,math.ceil(math.sqrt(width*height/32768)))
    luminosity=.22+.78*light/7
    phase=sample(0,seed,32)*math.tau
    def mix(a,b,f):return tuple(x*(1-f)+y*f for x,y in zip(a,b))
    def pixel(x,y):
        u=x/max(1,width-1);v=y/max(1,height-1)
        summit=ridge_profile(u)
        foothill=.68+.035*math.sin(u*8+phase)
        treeline=.82+.02*math.sin(u*17+phase)
        sky=12+(1-v)*(5+light)
        if v<min(summit,foothill):return (sky,sky+1,sky+1)
        texture=.04*math.sin(x*.19+y*.7)+.025*math.sin(x*.71+y*1.1)
        if v<foothill:
            depth=(v-summit)/max(.02,foothill-summit)
            folds=math.sin(u*37+depth*7+phase)+.3*math.sin(u*91-depth*11)
            exposure=.74+.16*folds*light_side+texture
            snowline=(.60 if season==0 else .42)+.12*math.sin(u*16+phase)+.04*folds
            snow=max(0,min(1,(snowline-depth)*14+.5))
            rock=mix((94,105,105),(56,65,59),min(1,depth))
            color=mix(rock,(182,190,186),snow)
            color=tuple(c*exposure for c in color)
            haze=.12+.15*(1-depth)
            color=mix(color,(89,104,106),haze)
        elif v<treeline:
            texture+=.05*math.sin(x*.45+v*34)
            color=(27+texture*35,61+texture*80,49+texture*50)
            cluster=int(x/6)
            tip=.65+sample(cluster,seed,61)*.10
            center=cluster*6+3
            spread=min(3,max(0,(v-tip)*height*.8))
            if v>tip and abs(x-center)<=spread:
                color=tuple(c*(.63+.09*math.sin(v*height*1.4)) for c in color)
        else:
            depth=(v-treeline)/max(.05,1-treeline)
            color=mix((25,58,37),(38,78,41),depth)
            if season==3:color=mix(color,(84,77,36),.4)
            color=tuple(c*(1+texture) for c in color)
        if light<=3 and foothill<=v<treeline and abs(u-(.5+.10*light_side))<.16:
            color=tuple(c*.72 for c in color)
        return tuple(c*luminosity for c in color)
    for x in range(0,width,stride):
        for y in range(0,height,stride):
            upper=pixel(x,y)
            lower=pixel(x,y+.5)
            cells[x,y]=(':' if ascii else '▄',ink(*lower,background=upper))
    return cells


def pnw(width, height, step, ascii=False, weather=None, seed=0, nature_age=None, flurry_strands=48, flurry_sway=.6, flurry_speed=1.0, flux_density=1.0, flux_glow=.15, flux_arms=2):
    """Bounded ordered layers: sky, terrain, shadows, complete trees, weather."""
    t=step/6
    age=t if nature_age is None else max(0,nature_age)
    dayphase=(age/180+.12)%1
    daylight=dayphase<.5
    u=dayphase*2 if daylight else (dayphase-.5)*2
    sunx=round(u*(width-1))
    suny=round((.68-.57*math.sin(math.pi*u))*(height-1))
    season=(age/900)%1
    winter=(1+math.cos(season*math.tau))/2
    autumn=max(0,math.sin((season-.5)*math.tau))
    spring=max(0,math.sin(season*math.tau))
    ridge=mountain(width,height)
    def horizon(x):
        return min(ridge,key=lambda item:abs(item[0][0]-x))[0][1]
    sky={}
    def put(layer,x,y,char,color):
        if 0<=x<width and 0<=y<height:layer[x,y]=(char,color)
    if not daylight:
        for i in range(18):
            x=int(sample(i,17,1)*width);y=int(sample(i,17,2)*height*.5)
            if y<horizon(x):put(sky,x,y,'.' if ascii else '·',11 if (step//12+i)%7==0 else 5)
    if suny<horizon(sunx):put(sky,sunx,suny,('O' if ascii else '☼') if daylight else ('O' if (1+math.cos(age/480*math.tau))/2>.75 else ')'),8 if daylight else 10)
    cloud=.2 if weather is None else weather.cloud
    wind=1 if weather is None else weather.wind_x
    for i in range(1+round(cloud*3)):
        x=int(i*width/4+t*(.10+abs(wind)*.03))%(width+8)-4
        y=1+i%3
        for offset,char in enumerate(' .--. ' if ascii else ' ░▒▒░ '):
            if char!=' ':put(sky,x+offset,y,char,11 if daylight else 5)
    elevation=math.sin(math.pi*u) if daylight else 0
    moonfull=(1+math.cos(age/480*math.tau))/2
    light=round(2+5*elevation) if daylight else round(1+moonfull)
    painting=painted_landscape(width,height,seed,light,int(season*4),ascii,-1 if sunx<width/2 else 1)
    terrain={xy:(char,color if daylight else 5) for xy,(char,color) in ridge} if ascii else {}
    shadows={};trees={};ground={}
    for i,(x,base,mature,phase,maturity) in enumerate(forest(width,height,seed)):
        growth=.55+.45*(1-math.exp(-age/180-maturity))
        tall=max(2,round(mature*growth))
        sway=round(math.sin(t/17+phase)*(.53 if abs(wind)>3 else .2))
        # Build each whole tree before composing its shadow: no partial-budget trees.
        for level in range(tall):
            y=base-tall+level
            center=x+(sway if level<tall//2 else 0)
            species=int(sample(i,seed,19)*4)
            half=min(1 if species==0 else 2,level//2)
            for dx in range(-half,half+1):
                char='^' if level==0 else ('v' if species==2 and abs(dx)==half and half else '/' if dx<0 else '\\' if dx>0 else '|')
                snow=(winter>.8 or (weather is not None and weather.temperature<0)) and level<2
                color=10 if snow and daylight else ink(*(v*(.4+.6*light/7) for v in ((35,105,67),(42,82,54),(61,111,66),(45,119,88))[species]))
                put(trees,center+dx,y,char,color)
        put(trees,x,base,'|',8 if daylight else 5)
        if daylight and len(trees)>0:
            direction=1 if x>=sunx else -1
            for distance in range(1,5):
                xx=x+direction*distance
                underlying=painting.get((xx,base),(' ',13))
                put(shadows,xx,base,underlying[0],shade_ink(underlying[1]))
        if sample(i,seed,4)<autumn:put(ground,x+2,base,'~',8 if daylight else 5)
        elif sample(i,seed,5)<spring:put(ground,x+2,base,'*',7 if daylight else 5)
    water={};ferns={};wildlife={}
    # A stream emerges below the ridge; a short bright fall feeds a meander.
    streamx=round(width*(.65+.08*sample(0,seed,40)))
    start=max(1,min(height-2,horizon(streamx)+1))
    for y in range(start,height):
        x=streamx+round(math.sin(y*.45+seed%7)*(1+(y-start)/4))
        color=ink(52+light*5,90+light*9,99+light*10)
        put(water,x,y,'|' if y<start+3 else '~',color)
        if y<start+3 and (step+y)%3==0:put(water,x,y,':' if ascii else '┊',ink(110,150,155))
        if y>start+2:put(water,x+1,y,'.' if ascii else '·',ink(35,67,72))
    for i in range(min(10,max(3,width//12))):
        x=int(sample(i,seed,42)*(width-3))+1
        y=height-1-int(sample(i,seed,43)*max(1,height//6))
        sw=round(math.sin(t*.8+i)*.5)
        for dx,char in enumerate('\\|/'):
            put(ferns,x+dx+sw,y,char,ink(46,99+light*5,56))
        if spring>.5:put(ferns,x+1,y-1,'*',ink(147,117,132))
    # Tiny stylized visitors have bounded presence windows, not AI behavior.
    if (age+sample(0,seed,50)*90)%90<55:
        gx=round(width*.62);gy=max(1,horizon(gx)-1)
        for dx,char in enumerate('o/\\'):put(wildlife,gx+dx,gy,char,ink(155,153,134) if daylight else ink(45,46,44))
    if winter<.85 and (age+sample(1,seed,50)*70)%70<38:
        mx=max(0,streamx-7);my=height-2
        for dx,char in enumerate('(o)'):put(wildlife,mx+dx,my,char,ink(117,86,56) if daylight else ink(40,34,27))
    flight=(t+sample(2,seed,50)*100)%100
    if flight<65:
        ex=int(flight/65*(width+4))-3;ey=max(0,round(height*.14+math.sin(t/10)))
        for dx,char in enumerate('\\_/' if int(t)%6<4 else '-v-'):
            if ey<horizon(max(0,min(width-1,ex+dx))):put(wildlife,ex+dx,ey,char,ink(114,124,116) if daylight else ink(45,50,47))
    camp={}
    if not daylight and (age+sample(3,seed,50)*180)%240<180:
        cx=max(1,min(width-12,round(width*.26)));cy=max(2,height-3)
        for row,text in enumerate((' /\\ ','/___\\')):
            for dx,char in enumerate(text):
                if char!=' ':put(camp,cx+dx,cy+row,char,ink(105,81,49))
        firex=cx+8;firey=cy+1
        flicker=.88+.08*math.sin(t*1.4)+.04*math.sin(t*2.1)
        for dy in range(-2,2):
            for dx in range(-3,4):
                strength=max(0,1-math.sqrt((dx/4)**2+(dy/3)**2))*.28*flicker
                xy=(firex+dx,firey+dy)
                if xy not in painting:continue
                char,style=painting[xy]
                bg=((style>>16)&255,(style>>8)&255,style&255)
                glow=(bg[0]+55*strength,bg[1]+23*strength,bg[2]+5*strength)
                put(camp,*xy,char,ink(80,63,40,background=glow))
        put(camp,firex,firey,'*' if int(t/2)%2 else '^',ink(200*flicker,126*flicker,47))
    cells={**sky,**terrain,**water,**shadows,**trees,**ground,**ferns,**wildlife,**camp}
    if weather is not None and weather.precipitation!='none':
        for i in range(round(weather.intensity*32)):
            x=int((sample(i,91,1)*width+t*wind*.7)%width)
            y=int((sample(i,91,2)*height+t*(2 if weather.precipitation=='rain' else .7))%height)
            # Weather respects foreground tree silhouettes.
            if (x,y) not in trees and (x,y) not in wildlife:cells[x,y]=('|' if weather.precipitation=='rain' else '*',9 if daylight and weather.precipitation=='rain' else 10 if daylight else 5)
    cells={xy:(char,inherit_background(color,painting.get(xy,(' ',13))[1])) for xy,(char,color) in cells.items()}
    return Scene(painting,cells)
