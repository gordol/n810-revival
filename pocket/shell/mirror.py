"""Window geometry for the opt-in real-PTY desktop easter egg."""
from collections import namedtuple

Plan=namedtuple('Plan','rect child delay lines')


def koan(width,height):
    lines=('When the last window closes,','who is looking out?')
    return ('',)*max(0,(height-2-len(lines))//2)+tuple(line.center(width-2)[:width-2] for line in lines)


def plan(width,height,depth,delay=.4):
    w=max(12,min(width-2,round(width*(.90,.86,.92,.88)[depth%4])))
    h=max(4,min(height-1,round(height*(.84,.82,.85,.83)[depth%4])))
    x=max(0,min(width-w,(width-w)//2+(-1,1,0,1)[depth%4]))
    y=max(0,min(height-h,(height-h)//2+(0,-1,1,0)[depth%4]))
    child=w-2>=40 and h-2>=14 and (w-2)*(h-2)<=262144
    lines=() if child else koan(w,h)
    return Plan((x,y,w,h),child,delay*(1,.9,1.1,.95)[depth%4],lines)
