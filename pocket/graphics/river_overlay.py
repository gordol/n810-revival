"""Cell-aligned GPU overlays; drawing and touch use the same rectangles."""
import ctypes as C
import textwrap


def hit(bounds,x,y):
    left,top,width,height=bounds
    return left<=x<left+width and top<=y<top+height


def tools(width,height,lens,binoculars=False,zoom=1.,regional=False):
    w=min(13,(width-3)//2)
    optics=lens or binoculars
    if regional:
        buttons=[('book','Guidebook',(width-w-1,3,w,2))]
    else:
        buttons=[('camera','Put away' if lens else 'Camera',(1,1,w,2)),
                 ('book','Guidebook',(width-w-1,1,w,2))]
    y=1 if regional else 3
    buttons.append(('binoculars','Lower' if binoculars else 'Binoculars',(1,y,w,2)))
    if optics:
        buttons.append(('zoom',f'Zoom {zoom:.1f}x',(width-w-1,y,w,2)))
    if not regional and not optics:buttons.append(('map','Map',(width-w-1,y,w,2)))
    if lens:buttons.append(('shutter','Take photo',((width-w)//2,height-3,w,3)))
    return buttons


def album_tools(width,height):
    third=width//3
    return [('prev','< Prev',(0,height-2,third,2)),('back','Book',(third,height-2,third,2)),
            ('next','Next >',(2*third,height-2,width-2*third,2))]


class Ink:
    def __init__(self,ctx,rect):
        self.ctx=ctx
        self.x,self.y=rect[:2]

    def fill(self,box,color):
        x,y,w,h=box
        self.ctx.check(self.ctx.lib.pocket_scene_rect(self.ctx.handle,self.x+x*8,self.y+y*16,w*8,h*16,color))

    def label(self,x,y,text,color):
        data=text.encode('utf-32-le')
        self.ctx.check(self.ctx.lib.pocket_scene_text(self.ctx.handle,self.x+x*8,self.y+y*16,C.c_char_p(data),len(text),color))

    def button(self,box,text):
        x,y,w,h=box
        self.fill((x+.08,y+.04,w-.16,h-.08),0x274A40F5)
        self.fill((x,y,w,.09),0xA5C5ABFF)
        self.label(x+(w-len(text[:w]))/2,y+(h-1)/2,text[:w],0xFFF6DA)


def book_layout(width,height):
    left=1 if width<44 else 3
    top=0 if height<15 else 1
    w=width-2*left
    h=height-2*top
    button_h=2
    middle=w//2
    at=top+h-2*button_h
    buttons=[('prev','< Prev',(left,at,middle,button_h)),('next','Next >',(left+middle,at,w-middle,button_h)),
             ('album','Album',(left,at+button_h,middle,button_h)),('close','Close',(left+middle,at+button_h,w-middle,button_h))]
    return (left,top,w,h),buttons


def draw_book(ink,book,width,height,photo):
    (x,y,w,h),buttons=book_layout(width,height)
    ink.fill((x-.4,y,.4,h),0x473C2EE8)
    ink.fill((x+w,y,.4,h),0x473C2EE8)
    ink.fill((x,y+h,w,.2),0x473C2EE8)
    ink.fill((x,y,w,h),0xF6E6C8C9)
    ink.fill((x,y,.65,h),0x805F43EA)
    ink.fill((x+.66,y,.22,h),0xCDB589F0)
    ink.label(x+1.5,y+.2,'My guidebook',0x493A28)
    counter=f'{book.page+1}/{len(book.entries)}' if book.entries else ''
    ink.label(x+w-len(counter)-1,y+.2,counter,0x493A28)
    ink.fill((x+1.5,y+1.35,w-3,.07),0x96784AC0)
    if book.entries:
        name,key,clue=book.entries[book.page]
    else:
        key=None
        name,clue='First discovery','Take a wildlife photo or walk up to a plant.'
    lines=textwrap.wrap(name,max(1,w-4))
    for i,line in enumerate(lines):ink.label(x+2,y+1.6+i,line,0x243B31)
    start=y+2+len(lines)
    end=buttons[0][2][1]-1
    if book.preview and end>start:
        photo(book.preview,(x+2,start,w-4,end-start))
    elif end>start:
        notes=textwrap.wrap(clue,w-4)[:int(end-start)]
        for i,line in enumerate(notes):
            ink.label(x+2,start+i,line,0x443D2E)
        sketch_top=start+len(notes)+.5
        if key in ('blueberry','conifer','fern') and end-sketch_top>=3:
            sketch=ink.ctx.lib.pocket_scene_plant_sketch
            sketch.argtypes=[C.c_void_p]+[C.c_int]*5
            ink.ctx.check(sketch(ink.ctx.handle,int(ink.x+(x+2)*8),int(ink.y+sketch_top*16),
                                 (w-4)*8,int((end-sketch_top)*16),('blueberry','conifer','fern').index(key)+1))
    ink.label(x+2,end,'for ella',0x5F503A)
    for action,label,box in buttons:ink.button(box,label)
