"""Offline world overview rendered into Pocket's native map plane."""
from functools import lru_cache
import json
import math
from pathlib import Path

from app_widgets import Canvas, TextInput

WATER, LAND, BOX = 0x285568, 0xb6c398, 0xffca51


def clamp(value, low, high):
    return min(high,max(low,value))


@lru_cache(maxsize=1)
def overview():
    data=json.loads(Path(__file__).with_name('world_picker').joinpath('world.json').read_text())
    rings=[]
    for path in data['land'].strip('Z').split('ZM'):
        points=[]
        for pair in path.lstrip('M').split():
            lon,y=map(float,pair.split(','))
            points.append((lon,-y))
        xs,ys=zip(*points)
        rings.append(((min(xs),min(ys),max(xs),max(ys)),points))
    return rings,data['places']


@lru_cache(maxsize=2)
def coast(width,height,lon,lat,step):
    """Scan-convert the bundled polygon rings at two samples per Pocket cell."""
    west=lon-width*step/2
    north=lat+height*step/2
    cuts=[[] for _ in range(height)]
    for (w,s,e,n),points in overview()[0]:
        if e<west or w>west+width*step or n<north-height*step or s>north:continue
        x0,y0=points[-1]
        for x1,y1 in points:
            top,bottom=sorted(((north-y0)/step,(north-y1)/step))
            for row in range(max(0,math.ceil(top-.5)),min(height,math.ceil(bottom-.5))):
                y=north-(row+.5)*step
                x=x0+(x1-x0)*(y-y0)/(y1-y0)
                cuts[row].append(clamp(math.ceil((x-west)/step-.5),0,width))
            x0,y0=x1,y1
    raster=[bytearray(width) for _ in cuts]
    for row,values in zip(raster,cuts):
        values.sort()
        for start,end in zip(values[::2],values[1::2]):
            row[start:end]=bytes([1])*(end-start)
    return raster


class Picker:
    controls=('Find','−','+','Box','Use area','Back')

    def __init__(self,bounds):
        self.width,self.height=40,14
        self.lon=self.lat=0.
        self.span=360.
        self.bounds=self.anchor=self.contact=None
        self.drawing=self.searching=False
        self.query=TextInput('',limit=80)
        self.notice='Tap to center · + to zoom · Box to select'
        self._key=self.plane=None
        self.cities=overview()[1]
        try:w,s,e,n=map(float,bounds.split())
        except ValueError:return
        if -180<=w<e<=180 and -90<s<n<90:
            self.bounds=(w,s,e,n)
            self.lon,self.lat=(w+e)/2,(s+n)/2
            self.span=clamp(max(e-w,(n-s)*2)*1.6,.001,360)

    @property
    def rows(self):return max(1,self.height-4)

    @property
    def step(self):
        return self.span/min(self.width,4*self.rows)

    def project(self,lon,lat):
        return (int(math.floor((lon-self.lon)/self.step+self.width/2)),
                int(math.floor((self.lat-lat)/(2*self.step)+self.rows/2)))

    def location(self,x,y):
        return (clamp(self.lon+(x+.5-self.width/2)*self.step,-180,180),
                clamp(self.lat-(y+.5-self.rows/2)*2*self.step,-89.999999,89.999999))

    def matches(self):
        query=self.query.text.casefold().strip()
        return [p for p in self.cities if query in (p[0]+', '+p[1]).casefold()][:self.height-4]

    def choose_city(self,city):
        self.lon,self.lat=city[2:4]
        self.span=.5
        self.searching=False
        self.notice=city[0]+' · Box to select'

    def action(self,name):
        self.contact=None
        if name=='Back':return 'back'
        if name=='Find':
            self.searching=True;self.drawing=False;self.anchor=None
        elif name in ('+','−'):
            self.span=clamp(self.span*(.5 if name=='+' else 2),.001,360)
        elif name=='Box':
            self.drawing=True;self.anchor=None
            self.notice='Tap the first corner'
        elif name=='Use area':
            if self.bounds and not self.drawing:return 'use'
            self.notice='Tap Box, then two opposite corners'
        return None

    def select(self,point):
        if self.anchor is None:
            self.anchor=point;self.notice='Tap the opposite corner';return
        w,e=sorted((self.anchor[0],point[0]))
        s,n=sorted((self.anchor[1],point[1]))
        if e>w and n>s:
            self.bounds=(w,s,e,n);self.anchor=None;self.drawing=False
            self.notice='Tap Use area to keep the highlighted box'

    def pointer(self,x,y,button,released):
        if self.searching:
            if button==0 and not released:
                choices=self.matches()
                if y==0:self.searching=False
                elif 2<=y<2+len(choices):self.choose_city(choices[y-2])
            return
        if y<2 and button==0 and not released:
            return self.action(self.controls[clamp(x*len(self.controls)//self.width,0,len(self.controls)-1)])
        if button!=0:return
        if not released and 2<=y<2+self.rows:
            self.contact=(x,y-2)
        elif released and self.contact:
            start=self.contact;self.contact=None
            end=(clamp(x,0,self.width-1),clamp(y-2,0,self.rows-1))
            if self.drawing:
                if self.anchor is None and start!=end:self.select(self.location(*start))
                self.select(self.location(*end))
            elif start==end:
                self.lon,self.lat=self.location(*end)
            else:
                self.lon=clamp(self.lon+(start[0]-end[0])*self.step,-180,180)
                self.lat=clamp(self.lat+(end[1]-start[1])*2*self.step,-90,90)

    def key(self,key):
        if self.searching:
            if key in ('escape','\x1b'):self.searching=False
            elif key in ('\r','\n'):
                choices=self.matches()
                if choices:self.choose_city(choices[0])
            else:self.query.key(key)
            return
        commands={'/':'Find','+':'+','=':'+','-':'−','b':'Box','u':'Use area','escape':'Back','\x1b':'Back'}
        if key in commands:return self.action(commands[key])
        if key in ('\r','\n') and self.drawing:self.select((self.lon,self.lat))
        if key in ('left','right'):self.lon=clamp(self.lon+(1 if key=='right' else -1)*self.step*3,-180,180)
        if key in ('up','down'):self.lat=clamp(self.lat+(1 if key=='up' else -1)*self.step*3,-89.999999,89.999999)

    def render(self,width,height):
        self.width,self.height=width,height
        canvas=Canvas(width,height)
        if self.searching:
            self.plane=self._key=None
            canvas.put(0,0,'[ Back ]    Find city')
            canvas.put(0,1,'City: '+self.query.text)
            for row,city in enumerate(self.matches(),2):canvas.put(1,row,city[0]+', '+city[1])
            return canvas.lines()
        for index,name in enumerate(self.controls):
            start=(index*width+5)//6
            end=((index+1)*width+5)//6
            label="Use" if name=="Use area" and end-start<len(name) else name
            canvas.put(start,0,label.center(end-start),end-start)
        canvas.put(0,height-2,self.notice)
        if self.bounds:canvas.put(0,height-1,' '.join(f'{v:.5f}' for v in self.bounds))
        else:canvas.put(0,height-1,f'{self.lon:.4f}, {self.lat:.4f} · Natural Earth')
        key=(width,height,self.lon,self.lat,self.span,self.bounds,self.anchor)
        if key==self._key:return canvas.lines()
        self._key=key
        rows=self.rows
        raster=coast(width,rows*2,self.lon,self.lat,self.step)
        cells=[('▀',(1<<48)|((LAND if a else WATER)<<24)|(LAND if b else WATER))
               for y in range(rows) for a,b in zip(raster[2*y],raster[2*y+1])]
        labels=[]
        for name,country,lon,lat,pop in self.cities:
            x,y=self.project(lon,lat)
            label='·'+name
            if not (0<=y<rows and 0<=x<=width-len(label)):continue
            if any(abs(y-yy)<=1 and x<=end+1 and x+len(label)>=start-1 for start,end,yy in labels):continue
            labels.append((x,x+len(label),y))
            for i,ch in enumerate(label):cells[y*width+x+i]=(ch,(1<<48)|(0xffffff<<24)|0x23414a)
            if len(labels)>=max(1,min(width//12,rows//3)):break
        if self.bounds:
            w,s,e,n=self.bounds
            left,top=self.project(w,n);right,bottom=self.project(e,s)
            for y in range(max(0,top),min(rows,bottom+1)):
                for x in range(max(0,left),min(width,right+1)):
                    if y in (top,bottom) or x in (left,right):cells[y*width+x]=(' ',(1<<48)|BOX)
        if self.anchor:
            x,y=self.project(*self.anchor)
            if 0<=x<width and 0<=y<rows:cells[y*width+x]=('+',(1<<48)|(0x182729<<24)|BOX)
        self.plane=(0,2,width,rows,tuple(cells))
        return canvas.lines()
