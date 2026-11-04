"""A retained miniature of desktop membership and window positions."""
from paint import ink,window_pane_ink


class Pager:
    def __init__(self):self.signature=None;self.overlay={};self.rects=[]
    def update(self,host):
        signature=(host.show_pager,host.width,host.work_height,host.pager_position,host.desktop,host.ascii,tuple((w.name,host.bounds(w),w.desktop,w.opened,w.visible,w.pinned) for w in host.windows))
        if signature==self.signature:return ()
        self.signature=signature;old=self.overlay;cells={};self.rects=[]
        if host.show_pager and host.width>=40 and host.work_height>=12:
            left=1 if host.pager_position.endswith('left') else max(0,host.width-30)
            top=1 if host.pager_position.startswith('top') else host.work_height-6
            for desktop in range(3):
                x=left+desktop*10;y=top;active=desktop==host.desktop
                self.rects.append((x,y,9,5,desktop))
                for dy in range(5):
                    for dx in range(9):
                        char=' '
                        if dy in (0,4):char='-' if host.ascii else '─'
                        if dx in (0,8):char='|' if host.ascii else '│'
                        if dx in (0,8) and dy in (0,4):char='+' if host.ascii else ('╭' if dx==0 else '╮') if dy==0 else ('╰' if dx==0 else '╯')
                        cells[x+dx,y+dy]=(char,active)
                cells[x+2,y]=(str(desktop+1),active)
                for w in host.windows:
                    if not w.opened or not w.visible or (w.desktop!=desktop and not w.pinned):continue
                    wx,wy,ww,wh=host.bounds(w)
                    xx=x+1+min(6,wx*7//host.width);yy=y+1+min(2,wy*3//max(1,host.work_height))
                    width=max(1,min(x+8-xx,round(ww*7/host.width)));height=max(1,min(y+4-yy,round(wh*3/max(1,host.work_height))))
                    for dy in range(height):
                        for dx in range(width):
                            if dx in (0,width-1) or dy in (0,height-1):cells[xx+dx,yy+dy]=('+' if host.ascii else '·',active)
        self.overlay=cells
        return {p for p in old.keys()|cells.keys() if old.get(p)!=cells.get(p)}
    def cell(self,under,x,y):
        value=self.overlay.get((x,y))
        if value is None:return under
        char,active=value;shaded=window_pane_ink(under.color,.32)
        if char==' ':return type(under)(under.char,shaded)
        bg=tuple((shaded>>s)&255 for s in (16,8,0))
        return type(under)(char,ink(*(155,180,185) if active else (85,105,110),background=bg))
    def hit(self,x,y):
        return next((d for xx,yy,w,h,d in self.rects if xx<=x<xx+w and yy<=y<yy+h),None)
