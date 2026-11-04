"""Small cached portal animation for real first-load waits, not fake progress."""
from functools import lru_cache
import math
from paint import ink,shade_ink,pane_ink,rgb


def glow_at(xx,yy,phase):
    radius=max(.055,math.hypot(xx,yy));angle=math.atan2(yy,xx)
    depth=math.log(radius)*7-phase
    volume=.5+.5*math.cos(depth+math.sin(angle*3+math.sin(phase)*.3)*.55)
    glow=(.25+.75*math.exp(-radius*radius*.8))*(.35+.65*volume)
    band=max(0,math.cos(math.log(radius)*12-phase*2+math.sin(angle)*.25))**20
    arm=max(0,math.cos(angle*3+radius*4-phase))**24
    light=glow+.12*band+.10*arm
    rgb=tuple(8+light*(35+65*(.5+.5*math.cos(angle+phase+shift+radius*2))) for shift in (0,2.1,4.2))
    return rgb,band*arm


@lru_cache(maxsize=8)
def portal(step,width=64,height=20):
    phase=(step%32)/32*math.tau
    def color(x,y):return glow_at(x/width*2-1,y/height*2-1,phase)
    stars={}
    for i in range(40):
        angle=i*2.399963229728653
        travel=((step%32)/32+i*.61803398875)%1
        radius=.045+travel*travel*1.45
        x=round((1+math.cos(angle)*radius)*width/2)
        y=round((1+math.sin(angle)*radius)*height/2)
        if 0<=x<width and 0<=y<height:
            fade=.55*min(1,travel*8,(1-travel)*12)
            stars[x,y]=(travel,fade)
    cells=[]
    for y in range(height):
        for x in range(width):
            upper,glint=color(x+.5,y+.2);lower,_=color(x+.5,y+.8)
            glyph='/' if glint>.80 and (x+y)%4==0 else '▄'
            if (x,y) in stars:
                travel,fade=stars[x,y]
                xx,yy=x-width/2,y-height/2
                glyph='·' if travel<.55 else ('─' if abs(xx)>abs(yy)*2 else '│' if abs(yy)>abs(xx)*2 else '╲' if xx*yy>0 else '╱')
                lower=tuple(c*(1-fade)+v*fade for c,v in zip(lower,(220,210,185)))
            cells.append((glyph,ink(*lower,background=upper)))
    return tuple(cells)


@lru_cache(maxsize=2)
def _ambient_reference(step,width=64,height=32):
    """Dim drifting light against black, with no radial tunnel or opaque wash."""
    phase=step/32*math.tau;cells=[];columns=[]
    # These coefficients depend on x and phase, not the row. Keep their original
    # expression order so the cached frame remains bit-for-bit identical.
    for x in range(width):
        xx=x/max(1,width-1)
        curve=.5+.20*math.sin(xx*4+math.sin(phase))+.08*math.sin(xx*9-phase)
        coefficients=tuple(12+10*math.cos(phase+xx*2+s) for s in (0,2.1,4.2))
        columns.append((curve,coefficients))
    for y in range(height):
        yy=y/max(1,height-1)
        for curve,coefficients in columns:
            glow=math.exp(-((yy-curve)/.065)**2)
            fg=tuple(3+glow*c for c in coefficients)
            # The black background packs to zero; retain paint.rgb's exact
            # foreground clamping and RGB565 rounding without repacking black.
            cells.append(('▄',(1<<48)|(rgb(*fg)<<24)))
    return tuple(cells)


@lru_cache(maxsize=2)
def ambient(step,width=64,height=32):
    if step==0:
        from loader_ambient import lookup
        cached=lookup(width,height)
        if cached is not None:return cached
    return _ambient_reference(step,width,height)


def box_rows(height,centered=False):
    if not centered:return max(0,height-7),max(0,height-2)
    top=max(0,(height-6)//2)
    return top,min(height-1,top+5)


def prepare(width,height,step,ascii=False,events=(),decoration=('╭','╮','╰','╯','─','│'),wire=None,wire_progress=1,centered=False):
    """Share immutable frame inputs; keep the scalar cell arithmetic unchanged."""
    sw,sh=min(64,width),min(32,height)
    ambient_cells=ambient(0,sw,sh)
    frame=('+','+','+','+','-','|') if ascii else decoration
    overlay=constructs(width,height,tuple((e.kind,e.count) for e in events),frame,centered) if events else {}
    left,right=width//5-2,width//5+max(4,width*3//5)+1
    box_top,box_bottom=box_rows(height,centered)
    neighbor_color=ink(9,6,12,background=(0,0,0))
    wire_phase=(step%32)/32;tint_phase=round(wire_phase,4)
    low,high=getattr(wire,'depth_range',(0,1));span=max(1,high-low)
    depths=getattr(wire,'depth',{});contours=getattr(wire,'contours',())
    strength=max(0,min(1,wire_progress));strength=strength*strength*(3-2*strength)
    @lru_cache(maxsize=256)
    def text_color(text,bg):return ink(*text,background=bg)
    def draw(x,y):
        xx,yy=min(sw-1,x*sw//width),min(sh-1,y*sh//height)
        glyph,color=ambient_cells[yy*sw+xx]
        if wire and (x,y) in wire:
            opacity=1 if (x,y) in contours else strength
            glyph=wire[x,y] if opacity>0 else ' '
            distance=max(0,min(1,(depths.get((x,y),0)-low)/span))
            gap=abs(distance-wire_phase);gap=min(gap,1-gap)
            glint=max(0,1-gap/.10);bucket=round(distance*128)/128
            base=edge_tint(bucket,0,(0,0,0))
            color=blend_ink(1<<48,blend_ink(base,edge_tint(bucket,tint_phase,(0,0,0)),glint),opacity)
        elif wire and ((x-1,y) in wire or (x+1,y) in wire):
            color=neighbor_color
        if events:
            if left<=x<=right and box_top<=y<=box_bottom:
                color=pane_ink(color,.32)
                if (x,y) in overlay:
                    glyph=overlay[x,y]
                    bg=((color>>16)&255,(color>>8)&255,color&255)
                    text=(235,220,185) if glyph not in '▄░·:+.┊┬─' else (225,170,110)
                    if glyph in '▄░':
                        phase=(x/max(1,width)+step/32)*math.tau
                        text=tuple(155+65*math.cos(phase+shift) for shift in (0,2.1,4.2))
                    if glyph in frame and glyph!=' ':
                        glint=max(0,math.cos((x+y)/max(1,width+height)*math.tau-step/32*math.tau))**12
                        text=(90+140*glint,75+120*glint,55+100*glint)
                    return (glyph if not ascii or ord(glyph)<128 else '#'),text_color(text,bg)
        return ((':' if glyph=='▄' else '.' if glyph=='·' else '+' if glyph in '─│' else '/' if glyph=='╱' else chr(92) if glyph=='╲' else glyph) if ascii else glyph),color
    return draw



def cell(width,height,x,y,step,ascii=False,events=(),decoration=('╭','╮','╰','╯','─','│'),wire=None,wire_progress=1):
    return prepare(width,height,step,ascii,events,decoration,wire,wire_progress)(x,y)


def changed_points(width,height,wire,previous_wire=None,step=None,previous_step=None):
    result=set()
    for edges in ((wire,) if wire is previous_wire else (wire,previous_wire)):
        if edges:
            low,high=getattr(edges,'depth_range',(0,1));span=max(1,high-low)
            for x,y in edges:
                if wire is previous_wire and step is not None and previous_step is not None:
                    d=max(0,min(1,(getattr(edges,'depth',{}).get((x,y),0)-low)/span))
                    current=abs(d-(step%32)/32);previous=abs(d-(previous_step%32)/32)
                    if min(current,1-current,previous,1-previous)>.11:continue
                result.update(((x-1,y),(x,y),(x+1,y)))
    left,right=width//5-2,width//5+max(4,width*3//5)+1
    result.update((x,y) for y in range(max(0,height-7),height-1) for x in range(max(0,left),min(width,right+1)))
    return ((x,y) for x,y in result if 0<=x<width and 0<=y<height)


def frame(width,height,step,ascii=False,events=(),decoration=('╭','╮','╰','╯','─','│'),wire=None,wire_progress=1,centered=False):
    """Share ambient cell values; shade only sparse wires and the small overlay."""
    sw,sh=min(64,width),min(32,height)
    base=ambient(0,sw,sh)
    rows=[tuple(base[yy*sw+min(sw-1,x*sw//width)] for x in range(width)) for yy in range(sh)]
    result=[value for y in range(height) for value in rows[min(sh-1,y*sh//height)]]
    special=set()
    if wire:
        for x,y in wire:
            special.update(((x-1,y),(x,y),(x+1,y)))
    if events:
        left,right=width//5-2,width//5+max(4,width*3//5)+1
        top,bottom=box_rows(height,centered)
        special.update((x,y) for y in range(top,bottom+1) for x in range(max(0,left),min(width,right+1)))
    if ascii:
        result=[(':' if char=='▄' else char,color) for char,color in result]
    draw=prepare(width,height,step,ascii,events,decoration,wire,wire_progress,centered)
    for x,y in special:
        if 0<=x<width and 0<=y<height:
            result[y*width+x]=draw(x,y)
    return result


@lru_cache(maxsize=4)
def constructs(width,height,events,decoration=('╭','╮','╰','╯','─','│'),centered=False):
    """Nodes appear only for milestones that the worker has actually published."""
    names=('source','height field','terrain','instances','world','camera','coverage','lighting','cells')
    ready=dict(events);result={}
    # A tiny completion strip reflects real work without naming internal objects.
    top,bottom=box_rows(height,centered)
    left=width//5;length=max(4,width*3//5);row=max(0,bottom-1) if centered else max(0,height-3)
    completed=len(names) if 'ready' in ready else sum(name in ready for name in names)
    filled=round(length*completed/len(names))
    for x in range(length):
        result[left+x,row]='▄' if x<filled else '┊' if x%4==0 else '─'
        # Empty blocks are edge-only; published milestones fill them from within.
        result[left+x,max(0,row-1)]='░' if x<filled else '┬' if x%4==0 else '─'
    captions={'request':'Preparing world','source':'Terrain decoded','height field':'Forming terrain','terrain':'Terrain formed','instances':'Instances placed','world':'World assembled','camera':'Camera placed','projecting':'Projecting','coverage':'Surfaces projected','lighting':'Lighting','cells':'Composing','ready':'Ready'}
    caption=captions.get(events[-1][0],'Preparing world') if events else 'Preparing world'
    start=max(0,(width-len(caption))//2)
    for x,char in enumerate(caption[:width]):result[start+x,max(0,row-2)]=char
    # Use the same decoration as the window manager, over the tinted underlay.
    tl,tr,bl,br,horizontal,vertical=decoration
    l,r=max(0,left-2),min(width-1,left+length+1)
    for x in range(l+1,r):
        result[x,top]=horizontal;result[x,bottom]=horizontal
    for y in range(top+1,bottom):
        result[l,y]=vertical;result[r,y]=vertical
    for point,char in (((l,top),tl),((r,top),tr),((l,bottom),bl),((r,bottom),br)):
        result[point]=char
    if filled<length:
        for dx,dy,char in ((0,-1,'+'),(1,0,':'),(-1,0,'.')):
            x,y=left+filled+dx,row+dy
            if 0<=x<width and 0<=y<height:result[x,y]=char
    return result


@lru_cache(maxsize=4096)
def chromatic(color,bucket):
    import colorsys
    colors=[]
    for rgb in (((color>>40)&255,(color>>32)&255,(color>>24)&255),((color>>16)&255,(color>>8)&255,color&255)):
        h,s,v=colorsys.rgb_to_hsv(*(c/255 for c in rgb))
        if bucket==0:h,s=.34,max(s,.45)
        else:h=(h+bucket/9)%1;s=max(s,.3)
        colors.append(tuple(c*255 for c in colorsys.hsv_to_rgb(h,s,v)))
    return ink(*colors[0],background=colors[1])


def arrival_glow(viewport,point,progress):
    return ' ',1<<48,(0,0,0)


def edge_color(wire,point,progress,bg):
    depth=getattr(wire,'depth',{}).get(point,0)
    low,high=getattr(wire,'depth_range',(0,1))
    distance=max(0,min(1,(depth-low)/max(1,high-low)))
    return edge_tint(round(distance*128)/128,round(progress,4),bg)


@lru_cache(maxsize=4096)
def edge_tint(distance,progress,bg):
    near=1-distance
    phase=((progress+distance*.35)%1)*4
    palette=((240,180,90),(230,115,100),(190,125,180),(115,190,150))
    index=int(phase);blend=.5-.5*math.cos((phase-index)*math.pi)
    a,b=palette[index%4],palette[(index+1)%4]
    brightness=.40+.60*near
    rgb=tuple((x+(y-x)*blend)*brightness for x,y in zip(a,b))
    glint=1+.18*max(0,math.cos(phase*math.pi))**12
    return ink(*(min(250,c*glint) for c in rgb),background=bg)


def grid_color(point,background):
    """Cool retained construction ink, distinct from earth and warm ignition."""
    x,y=point;t=.5+.5*math.sin((x-y)*.025)
    return ink(90+70*t,170-50*t,190+40*t,background=background)


def surface_grid_ink(color, point, strength):
    """Tint both half-cell samples at their own luminance, preserving relief."""
    t=.5+.5*math.sin((point[0]-point[1])*.025)
    hue=(.78+.12*t,1.04-.08*t,1.16+.08*t)
    result=1<<48
    for shift in (24,0):
        rgb=tuple((color>>(shift+s))&255 for s in (16,8,0))
        luminance=.2126*rgb[0]+.7152*rgb[1]+.0722*rgb[2]
        for value,factor,channel in zip(rgb,hue,(16,8,0)):
            target=min(255,luminance*factor*1.08)
            result|=round(value+(target-value)*strength)<<(shift+channel)
    return result


class Arrival:
    """One continuous world reveal, followed by retained window layers."""
    def __init__(self,width,height,windows=(),ghosts=()):
        self.width=width;self.height=height
        self.cursor=0
        self.landscape=((0,0,width,height),0,.34)
        self.windows=[(rect,.36+i/max(1,len(windows))*.10,.25) for i,rect in enumerate(windows)]
        self.pieces=(self.landscape,*self.windows)
        self.ghosts={}
        for name,desktop,(x,y,w,h) in ghosts:
            # Preview actual retained window geometry, without changing ownership.
            left=max(0,x);right=min(width-1,x+w-1);top=max(0,y);bottom=min(height-1,y+h-1)
            if right-left<4 or bottom<=top:continue
            for xx in range(left+1,right):self.ghosts[xx,top]='─';self.ghosts[xx,bottom]='─'
            for yy in range(top+1,bottom):self.ghosts[left,yy]='│';self.ghosts[right,yy]='│'
            for point,char in (((left,top),'╭'),((right,top),'╮'),((left,bottom),'╰'),((right,bottom),'╯')):self.ghosts[point]=char
            for dx,char in enumerate((' '+name+' / '+str(desktop+1)+' ')[:max(0,right-left-1)]):self.ghosts[left+1+dx,top]=char

    @staticmethod
    def phase(track,progress):
        _,delay,duration=track
        return max(0,min(1,(progress-delay)/duration))

    def world(self,x,y,progress):
        return self.phase(self.landscape,progress)

    def local(self,x,y,progress):
        for track in reversed(self.windows):
            (left,top,width,height),_,_=track
            if left<=x<left+width and top<=y<top+height:return self.phase(track,progress)
        return self.phase(self.landscape,progress)

    def dirty(self,previous,progress):
        return (track[0] for track in self.pieces
                if previous<0 or self.phase(track,previous)!=self.phase(track,progress)
                or (self.phase(track,progress)>0 and progress<1))

    def ghost_cell(self,cell,point,progress,ascii=False):
        if point not in self.ghosts or not .36<progress<.94:return cell
        appear=max(0,min(1,(progress-.36)/.16));fade=max(0,min(1,(progress-.68)/.26))
        strength=appear*appear*(3-2*appear)*(1-fade*fade*(3-2*fade))
        color=cell[1]
        if color<1<<48:return cell
        background=tuple((((color>>a)&255)+((color>>b)&255))//2 for a,b in ((40,16),(32,8),(24,0)))
        ink_color=edge_color(None,point,progress,background)
        ink_color=blend_ink(ink(*background,background=background),ink_color,strength*.8)
        char=self.ghosts[point]
        if ascii and ord(char)>127:char='+' if char in '╭╮╰╯' else '-' if char=='─' else '|'
        return char,ink_color

    def take(self,damage,budget):
        # Round-robin scan avoids repeatedly servicing the top while the bottom waits.
        ordered=sorted(damage)
        import bisect
        at=bisect.bisect_left(ordered,self.cursor)
        selected=(ordered[at:]+ordered[:at])[:budget]
        if selected:self.cursor=(selected[-1]+1)%(self.width*self.height)
        return selected


def blend_ink(a,b,amount):
    """Blend packed foreground and background without allocating scene buffers."""
    if amount<=0:return a
    if amount>=1:return b
    weight=round(amount*256);inverse=256-weight;mask=0xff00ff00ff
    # Three byte lanes per integer: no per-channel tuples, clamps, or RGB565
    # requantization at every intermediate fade step.
    low=((((a&mask)*inverse+(b&mask)*weight)>>8)&mask)
    high=((((((a>>8)&mask)*inverse+((b>>8)&mask)*weight)>>8)&mask)<<8)
    return (1<<48)|low|high


def arrival_finish(cell,point,viewport,wire,progress,is_ui=False):
    """Hold a shared glow, settle colors, then release the luminous edges."""
    if progress>=1:return cell
    char,color=cell
    if color<1<<48:
        if not is_ui:return cell
        # Palette-based chrome participates too; retain the exact palette at rest.
        if progress>=.995:return cell
        from paint import inherit_background
        color=inherit_background(color,ink(12,12,12,background=(12,12,12)))
    settle=max(0,min(1,(progress-.74)/.18));settle=settle*settle*(3-2*settle)
    color=blend_ink(color,chromatic(color&0xf0f0f0f0f0f0,round(progress*8,3)),.24*(1-settle))
    if wire is not None and point in wire and not is_ui:
        # Draw a thin structural line, not a colored terrain half-block.
        surface=tuple((((color>>a)&255)+((color>>b)&255))//2 for a,b in ((40,16),(32,8),(24,0)))
        edge=edge_color(wire,point,progress,surface)
        black=max(0,min(1,(progress-.82)/.10))
        black=black*black*(3-2*black)
        ghost=max(0,min(1,(progress-.92)/.08))
        ghost=ghost*ghost*(3-2*ghost)
        edge=blend_ink(edge,ink(0,0,0,background=surface),black)
        edge=blend_ink(edge,ink(*surface,background=surface),ghost)
        if progress<.995:return wire[point],edge
        return char,color
    edge=(wire is not None and point in wire and not is_ui and char not in (' ','▄','▀')) or (is_ui and char in '┌┐└┘─│╭╮╰╯╔╗╚╝═║')
    if edge:
        release=max(0,min(1,(progress-.90)/.10));release=release*release*(3-2*release)
        bg=((color>>16)&255,(color>>8)&255,color&255)
        color=blend_ink(color,edge_color(wire,point,progress,bg),.55*(1-release))
    return char,color


def land(cell,seed,progress,point=None,viewport=None,wire=None,background=None,ui_progress=None,overall_progress=None,live_ui=False):
    """Landscape edges, near-to-far surfaces, frames, text, then settled glass."""
    is_ui=background is not None and cell!=background
    if live_ui and is_ui:return cell
    if progress>=1 and (ui_progress is None or ui_progress>=1) and (overall_progress is None or not is_ui or overall_progress>=.90):
        return arrival_finish(cell,point,viewport,wire,overall_progress,is_ui) if overall_progress is not None else cell
    if point is None:
        return cell if seed/4294967296<progress else (' ',6)
    glow_char,glow,bg=arrival_glow(viewport,point,overall_progress if overall_progress is not None else progress)
    under=background if background is not None else cell
    low,high=getattr(wire,'depth_range',(0,1))
    surface=getattr(wire,'surface_depth',None)
    if surface:
        depths,pw,ph,width,height=surface;x,y=point
        depth=depths[min(ph-1,y*ph//height)*pw+min(pw-1,x*pw//width)]
    else:depth=getattr(wire,'depth',{}).get(point,(low+high)/2)
    if not math.isfinite(depth):depth=high
    distance=max(0,min(1,(depth-low)/max(1,high-low)))
    jitter=0
    fill_start=.12+(1-distance)*.54+jitter
    fill=max(0,min(1,(progress-fill_start)/.16))
    fill=fill*fill*(3-2*fill)
    fill*=fill
    filled=fill>0
    # The world is present from the opening frame; the tunnel is its underlight.
    # Keep distant surfaces faint until their depth reaches the fill front.
    visibility=min(.22,progress*.3)*(1-distance*.45)
    result=(under[0],blend_ink(glow,under[1],visibility)) if under[1]>=1<<48 else (glow_char,glow)
    if filled:
        char,color=under
        if color>=1<<48 and progress<.86:
            color=blend_ink(color,chromatic(color&0xf0f0f0f0f0f0,round(progress*8,3)),.28*(1-progress/.86))
        result=(char,blend_ink(result[1],color,fill)) if color>=1<<48 else (char,color)
    if wire and point in wire:
        edge=edge_color(wire,point,overall_progress if overall_progress is not None else progress,bg)
        # A bright ignition front runs along depth contours. Color remains behind it.
        front=max(0,1-abs(progress-fill_start)/.16)
        if front:
            fg=tuple(min(255,((edge>>shift)&255)*(1+.6*front)+65*front) for shift in (40,32,24))
            edge=ink(*fg,background=bg)
        amount=fill*(1-front*.65)
        result=(wire[point] if fill<1 else result[0]),blend_ink(edge,result[1],amount)
    elif wire and not filled and ((point[0]-1,point[1]) in wire or (point[0]+1,point[1]) in wire):
        result=(' ',ink(0,0,0,background=(9,5,12)))
    # Keep the changing landscape visible through the forming UI.
    is_ui=background is not None and cell!=background
    frame=cell[0] in '┌┐└┘─│╭╮╰╯╔╗╚╝═║'
    if ui_progress is not None:progress=ui_progress
    if is_ui:
        if result[1]>=1<<48:bg=((result[1]>>16)&255,(result[1]>>8)&255,result[1]&255)
        if frame and progress>.03+jitter:
            edge=edge_color(wire,point,progress,bg)
            strength=max(0,min(1,(progress-.03-jitter)/.12))
            invisible=ink(*bg,background=bg)
            result=(cell[0],blend_ink(invisible,edge,strength))
        elif cell[0] not in (' ','▄','▀') and progress>.50+jitter:
            strength=max(0,min(1,(progress-.50-jitter)/.14))
            result=(cell[0],blend_ink(ink(*bg,background=bg),ink(235,220,185,background=bg),strength))
        panel_fill=max(0,min(1,(overall_progress-.72)/.18)) if overall_progress is not None else max(0,min(1,(progress-.62)/.35))
        if panel_fill>0:
            char,color=cell
            if color>=1<<48:
                # Settle both foreground and translucent window fill continuously.
                t=panel_fill*panel_fill*(3-2*panel_fill)
                old=result[1]
                if old>=1<<48:
                    channels=[round(((old>>shift)&255)*(1-t)+((color>>shift)&255)*t) for shift in (40,32,24,16,8,0)]
                    color=ink(*channels[:3],background=channels[3:])
            result=(char,color)
        if frame and .90<progress<.995:
            x,y=point;width,height=viewport
            flare=max(0,1-abs((x+y)/max(1,width+height)-(progress-.90)/.095)*12)
            if flare:result=(cell[0],ink(180+70*flare,165+80*flare,130+95*flare,background=bg))
    return arrival_finish(result,point,viewport,wire,overall_progress,is_ui) if overall_progress is not None else result


class WorldReveal:
    """One phase's shared tint table and depth weights for unobscured terrain."""
    def __init__(self,world,overall,wire):
        self.world,self.overall=world,overall
        self.psy=(.28*max(0,1-world/.86)+.24*(1-max(0,min(1,(overall-.74)/.18))))
        self.bucket=round(overall*8,3);self.colors={};self.starts=getattr(wire,'starts',None)
    def cell(self,cell,index):
        char,color=cell
        if color<1<<48:return cell
        start=self.starts[index]
        if self.world<=start:return char,1<<48
        if self.world>=start+.16:return cell
        fill=(self.world-start)/.16
        fill=fill*fill*(3-2*fill)
        fill*=fill
        psy=.4*math.sin(fill*math.pi)
        key=color&0xf0f0f0f0f0f0
        tint=self.colors.get(key)
        if tint is None:tint=chromatic(key,self.bucket);self.colors[key]=tint
        return char,blend_ink(1<<48,blend_ink(color,tint,psy),fill)


def ripple_damage(wire,width,previous,current,plan):
    """Depth bands bound work; the effect itself uses continuous geometry depth."""
    old=plan.world(0,0,previous);new=plan.world(0,0,current)
    result=set()
    if new!=old:
        low=max(0,int((old-.16)*64)-1);high=min(63,int(new*64)+1)
        for band in wire.bands[low:high+1]:result.update(band)
    result.update(y*width+x for x,y in wire)
    if .34<current<.96 or .34<previous<.96:
        result.update(y*width+x for x,y in plan.ghosts)
    return result


class WireFrame(dict):
    __slots__=('depth','depth_range','surface_depth','contours','accents','starts','bands')
    def __init__(self):super().__init__();self.depth={};self.depth_range=(0,1);self.surface_depth=None;self.starts=None;self.bands=None;self.contours=set();self.accents=set()


def clip_line(ax,ay,bx,by,width,height):
    dx,dy=bx-ax,by-ay;low,high=0.,1.
    for p,q in ((-dx,ax),(dx,width-1-ax),(-dy,ay),(dy,height-1-ay)):
        if p==0:
            if q<0:return None
        else:
            t=q/p
            if p<0:low=max(low,t)
            else:high=min(high,t)
            if low>high:return None
    return ax+low*dx,ay+low*dy,ax+high*dx,ay+high*dy


def wire_budget(width,height):
    return min(32768,max(4096,width*height//6))


def bound_wire(result,width,height):
    """Keep coverage across the whole viewport; never stop at a scanline."""
    budget=wire_budget(width,height)
    if len(result)<=budget:return result
    selected=WireFrame();selected.surface_depth=result.surface_depth;selected.starts=result.starts;selected.bands=result.bands;selected.depth_range=result.depth_range
    contours=sorted(result.contours,key=lambda p:(p[1],p[0]))[:budget]
    remaining=sorted(result.keys()-set(contours),key=lambda p:(p[1],p[0]))
    keep=budget-len(contours)
    points=contours+[remaining[i*len(remaining)//keep] for i in range(keep)] if keep else contours
    for point in points:selected[point]=result[point];selected.depth[point]=result.depth[point]
    selected.contours=set(contours);selected.accents=result.accents&selected.keys()
    return selected


def scaffold(model,width,height):
    """Bounded transparent projected model edges before dense coverage exists."""
    from build_trace import checkpoint
    triangles=model.mesh.triangles
    stride=max(1,len(triangles)//1800)
    selected=range(0,len(triangles),stride)
    # The preview samples triangles, so projecting every dense-mesh vertex does
    # unused work. Keep original vertex IDs and edge order for identical wires.
    needed=set()
    for index in selected:
        checkpoint();needed.update(triangles[index][:3])
    ids=sorted(needed)
    projected=dict(zip(ids,model.camera.project_many(tuple(model.mesh.vertices[i] for i in ids))))
    result=WireFrame()
    for index in selected:
        checkpoint()
        tri=triangles[index]
        for ia,ib in ((tri.a,tri.b),(tri.b,tri.c),(tri.c,tri.a)):
            a,b=projected[ia],projected[ib]
            if min(a[2],b[2])<=0:continue
            line=clip_line(a[0]*width,a[1]*height,b[0]*width,b[1]*height,width,height)
            if line is None:continue
            ax,ay,bx,by=line;dx,dy=bx-ax,by-ay
            steps=max(1,min(48,round(max(abs(dx),abs(dy)))))
            glyph='─' if abs(dx)>abs(dy)*2 else '│' if abs(dy)>abs(dx)*2 else '╲' if dx*dy>0 else '╱'
            for i in range(steps+1):
                point=(round(ax+dx*i/steps),round(ay+dy*i/steps))
                result[point]=glyph;result.depth[point]=(a[2]+b[2])/2
    result=bound_wire(result,width,height)
    if result.depth:
        values=tuple(result.depth.values());result.depth_range=(min(values),max(values))
    return result


_last_completed_wire=None


def wire_preview(model,width,height,include_surfaces=False):
    """Reuse a completed preview only for the identical model and viewport."""
    from build_trace import checkpoint
    checkpoint()
    last=_last_completed_wire
    if last is not None and last[0] is model and last[1:4]==(width,height,include_surfaces):
        return last[4]
    return scaffold(model,width,height)


def wires(model,width,height,include_surfaces=False):
    global _last_completed_wire
    result=_wires(model,width,height,include_surfaces)
    # One reference to the most recently used existing LRU entry, not another
    # geometry cache. Publish only after the complete computation succeeds.
    _last_completed_wire=(model,width,height,include_surfaces,result)
    return result


def _clear_wires():
    global _last_completed_wire
    _last_completed_wire=None
    _wires.cache_clear()


@lru_cache(maxsize=2)
def _wires(model,width,height,include_surfaces=False):
    """Bounded transparent edges from the actual world mesh and visible coverage."""
    from geometry import raster
    from build_trace import checkpoint
    mesh,normals,materials,samples,depths,_,pw,ph,*_=raster(model,width,height,include_surfaces)
    projected=model.camera.project_many(mesh.vertices)
    result=WireFrame()
    result.surface_depth=(depths,pw,ph,width,height)
    finite=sorted(d for d in depths[::max(1,len(depths)//2048)] if math.isfinite(d))
    if finite:result.depth_range=(finite[len(finite)//10],finite[min(len(finite)-1,len(finite)*9//10)])
    from array import array
    low,high=result.depth_range;span=max(1,high-low)
    result.starts=array('f');result.bands=[[] for _ in range(64)]
    for y in range(height):
        checkpoint()
        for x in range(width):
            depth=depths[min(ph-1,y*ph//height)*pw+min(pw-1,x*pw//width)]
            distance=max(0,min(1,(depth-low)/span)) if math.isfinite(depth) else 1
            start=.12+(1-distance)*.54
            result.starts.append(start);result.bands[min(63,int(start*64))].append(y*width+x)
    # First establish the actual skyline using the filled scene's coverage.
    skyline=[]
    for x in range(width):
        xx=min(pw-1,x*pw//width)
        checkpoint()
        for y in range(height):
            yy=min(ph-1,y*ph//height);index=yy*pw+xx
            if samples[index] is not None:
                skyline.append((x,y,depths[index]));break
    for i,(x,y,depth) in enumerate(skyline):
        previous=skyline[max(0,i-1)][1];following=skyline[min(len(skyline)-1,i+1)][1]
        result[x,y]='─' if previous==following else '╱' if following<previous else '╲'
        result.depth[x,y]=depth;result.contours.add((x,y))
    # Use only the same frontmost coverage used by the filled renderer.
    # Raw hidden triangles made the preview resemble a different landscape.
    # Fine or partially clipped geometry can have no whole edge inside the view.
    # The retained visible coverage supplies barycentric distance to those edges.
    for y in range(height):
        checkpoint()
        for x in range(width):
            xx=min(pw-1,x*pw//width);yy=min(ph-1,y*ph//height)
            candidates=(samples[yy*pw+xx],samples[min(ph-1,yy+1)*pw+xx])
            for sample in candidates:
                if sample is None:continue
                ia,ib,ic,wa,wb,wc=sample
                weights=(wa,wb,wc);edge=min(range(3),key=weights.__getitem__)
                if weights[edge]>.055:continue
                u,v=((ib,ic),(ic,ia),(ia,ib))[edge]
                a,b=projected[u],projected[v]
                dx,dy=(b[0]-a[0])*width,(b[1]-a[1])*height
                length=math.hypot(dx,dy)
                px,py=(xx+.5)*width/pw,(yy+.5)*height/ph
                if length<1e-9 or abs(dx*(py-a[1]*height)-dy*(px-a[0]*width))/length>.48:continue
                char='─' if abs(dy)<abs(dx)*.25 else '│' if abs(dx)<abs(dy)*.4 else '╲' if dx*dy>0 else '╱'
                result.setdefault((x,y),char);result.depth.setdefault((x,y),depths[yy*pw+xx])
                # Retained accents follow terrain curvature, not screen-space patches.
                if materials[u]=='terrain' and materials[v]=='terrain' and sum(a*b for a,b in zip(normals[u],normals[v]))<.98:
                    result.accents.add((x,y))
                here=depths[yy*pw+xx];above=depths[max(0,yy-1)*pw+xx]
                if math.isfinite(above) and abs(here-above)>max(250,here*.08):result.contours.add((x,y))
                break
    return bound_wire(result,width,height)


wires.cache_clear=_clear_wires
wires.cache_info=_wires.cache_info
