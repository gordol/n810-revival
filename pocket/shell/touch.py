"""Pure single-stylus mapping to existing Input mouse tuples. No device I/O/imports."""
def cell(x,y,x_range,y_range,columns,rows,rotation=0):
    if columns<1 or rows<1 or rotation not in (0,90,180,270):raise ValueError('invalid touch viewport')
    xmin,xmax=x_range;ymin,ymax=y_range
    dx=xmax-xmin;dy=ymax-ymin
    if dx<=0 or dy<=0:raise ValueError('invalid calibrated touch ranges')
    nx=max(0,min(dx,x-xmin));ny=max(0,min(dy,y-ymin))
    if rotation==90:nx,ny,dx,dy=dy-ny,nx,dy,dx
    elif rotation==180:nx,ny=dx-nx,dy-ny
    elif rotation==270:nx,ny,dx,dy=ny,dx-nx,dy,dx
    return min(columns-1,nx*columns//dx),min(rows-1,ny*rows//dy)


class Stylus:
    """Accept complete SYN_REPORT snapshots; coalesce motion, preserve press/release."""
    def __init__(self,x_range,y_range,columns,rows,rotation=0,project=None):
        cell(x_range[0],y_range[0],x_range,y_range,columns,rows,rotation)
        self.geometry=(x_range,y_range,columns,rows,rotation);self.project=project;self.down=False;self.last=None
    def report(self,x,y,pressed):
        if x is None or y is None:return None
        point=self.project(x,y) if self.project is not None else cell(x,y,*self.geometry)
        if not self.down and not pressed:self.last=point;return None
        if not self.down:
            self.down=True;self.last=point;return ('mouse',0,*point,False)
        if not pressed:
            self.down=False;self.last=point;return ('mouse',0,*point,True)
        if point==self.last:return None
        self.last=point;return ('mouse',32,*point,False)
    def batch(self,reports):
        output=[]
        for x,y,pressed in reports:
            event=self.report(x,y,pressed)
            if event is None:continue
            if event[1]==32 and output and output[-1][1]==32:output[-1]=event
            else:output.append(event)
        return output
