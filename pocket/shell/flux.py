"""Colored Clifford attractor with bounded glow and a shared dim backdrop."""
import math
from flurry import backdrop,ascii_backdrop
from paint import ink,Scene
from weather import detail_budget
from build_trace import checkpoint


def frame(width,height,step,ascii=False,density_scale=1.0,glow_strength=.15,arms=2):
    import paint
    if paint.NATIVE_SCENES is not None and type(arms) is int and 0<=arms<=4 and math.isfinite(step) and math.isfinite(density_scale) and 0<=glow_strength<=1:
        from native_scene import flux
        return flux(paint.NATIVE_SCENES,width,height,step,ascii,density_scale,glow_strength,arms)
    return reference_frame(width,height,step,ascii,density_scale,glow_strength,arms)


def reference_frame(width,height,step,ascii=False,density_scale=1.0,glow_strength=.15,arms=2):
    t=step/90
    a,b,c,d=-1.4+.12*math.sin(t),1.6,1+.15*math.cos(t*.7),.7
    x,y=.1,.1
    density={}
    budget=round(detail_budget(width,height)*max(.5,min(4,density_scale)))
    for i in range(budget+32):
        if i%256==0:checkpoint()
        x,y=math.sin(a*y)+c*math.cos(a*x),math.sin(b*x)+d*math.cos(b*y)
        if i<32:continue
        xx=min(width-1,max(0,int((x+2.2)/4.4*width)))
        yy=min(height-1,max(0,int((y+2)/4*height)))
        density[xx,yy]=density.get((xx,yy),0)+1
    heads=dict(density)
    trails={}
    for index,((x,y),hits) in enumerate(heads.items()):
        if index%128==0:checkpoint()
        angle=math.sin(x/max(1,width)*5+t*.3)+y/max(1,height)*3
        dx,dy=math.cos(angle),math.sin(angle)*.5
        glyph='-' if abs(dy)<.25 else '/' if dx*dy<0 else '\\'
        for distance in range(1,max(0,min(4,int(arms)))+1):
            xy=round(x-dx*distance),round(y-dy*distance)
            if 0<=xy[0]<width and 0<=xy[1]<height and xy not in heads:
                weight=(1-distance/(arms+1))*.65
                density[xy]=max(density.get(xy,0),weight)
                trails[xy]=glyph
    glow={}
    for index,((x,y),hits) in enumerate(density.items()):
        if index%128==0:checkpoint()
        strength=min(1.7,.45+math.log1p(hits)*.35)
        for dx,dy,weight in ((0,0,1),(-1,0,.18),(1,0,.18),(0,-1,.12),(0,1,.12)):
            xy=x+dx,y+dy
            if 0<=xy[0]<width and 0<=xy[1]<height:
                glow[xy]=min(2.2,glow.get(xy,0)+strength*weight*(1 if dx==dy==0 else glow_strength))
    base=ascii_backdrop(width,height) if ascii else backdrop(width,height)
    overlay={}
    for index,((x,y),amount) in enumerate(glow.items()):
        if index%128==0:checkpoint()
        phase=x/max(1,width)*2.4+y/max(1,height)*1.7+t*.12
        rgb=tuple(65+85*(.5+.5*math.sin(phase+shift)) for shift in (0,2.1,4.2))
        under=base[x,y][1]
        bg=((under>>16)&255,(under>>8)&255,under&255)
        bottom=tuple(min(240,b+c*amount*(1.15 if (x,y) in heads else .65)) for b,c in zip(bg,rgb))
        if (x,y) in density:
            glyph=trails.get((x,y),('+' if heads.get((x,y),0)>=3 else '.' if ascii else '·'))
            overlay[x,y]=(glyph,ink(*bottom,background=tuple(b+c*amount*.08*glow_strength for b,c in zip(bg,rgb))))
        elif glow_strength>0:
            overlay[x,y]=(' ',ink(*bg,background=tuple(b+c*amount*.20 for b,c in zip(bg,rgb))))
    return Scene(base,overlay)
