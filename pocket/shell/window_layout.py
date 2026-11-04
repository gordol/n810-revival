"""Small edge magnets for window placement; no persistent window groups."""
def snap(rect,others,viewport,distance=2):
    x,y,w,h=rect;vw,vh=viewport
    xs=[0,vw-w];ys=[0,vh-h]
    for ox,oy,ow,oh in others:
        if y<oy+oh+distance and oy<y+h+distance:xs.extend((ox-w,ox+ow,ox,ox+ow-w))
        if x<ox+ow+distance and ox<x+w+distance:ys.extend((oy-h,oy+oh,oy,oy+oh-h))
    def nearest(value,candidates,limit):
        near=[v for v in candidates if 0<=v<=limit and abs(v-value)<=distance]
        return min(near,key=lambda v:abs(v-value)) if near else value
    return nearest(x,xs,vw-w),nearest(y,ys,vh-h),w,h
