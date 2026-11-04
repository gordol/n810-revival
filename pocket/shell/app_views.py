"""Distinct application workspaces composed from shared character widgets."""
import calendar
import math
import re
import time
from functools import lru_cache
from app_widgets import Canvas,SelectList,TextInput,Transcript,DataTable,tabs,toolbar_hit


class View:
    def __init__(self,app,host=None):
        self.app,self.host=app,host;self.width,self.height=68,22
        self.revision=0;self._cached=None;self._signature=None
    @property
    def body_height(self):
        dock=getattr(self,'docks',None)
        return max(6,self.height-6) if dock and dock.foreign(self.app.name) else self.height
    def changed(self):self.revision+=1
    def lines(self):
        foreign=self.docks.foreign(self.app.name) if getattr(self,'docks',None) else None
        source_revision=self.docks.views[foreign.source].revision if foreign else 0
        signature=(self.width,self.height,self.revision,source_revision,tuple(self.detached(name) for name in ('Packet Inspector','Chat History')))
        if signature!=self._signature:
            c=Canvas(self.width,self.height);self.draw(c)
            pane=self.docks.foreign(self.app.name) if getattr(self,'docks',None) else None
            if pane:
                y=self.body_height;c.rule(y);c.put(1,y,' '+pane.title+' / from '+pane.source+' ')
                for n,line in enumerate(self.docks.rows(pane)[:4]):c.put(1,y+1+n,line)
            c.put(0,self.height-1,' '*self.width)
            c.put(1,self.height-1,'PREVIEW / fixtures',max(1,self.width-2))
            self._cached=c.lines();self._signature=signature
        return self._cached
    def spans(self):
        spans=[]
        def area(x,y,w,h,role):
            spans.extend((row,x,w,role) for row in range(max(0,y),min(self.body_height,y+h)))
        if isinstance(self,ChatView):
            split=self.split()
            area(0,2,split,self.body_height-4,'rail')
            area(split+1,2,self.width-split-1,self.body_height-8,'panel')
            area(split+1,self.body_height-5,self.width-split-1,3,'inset')
        elif isinstance(self,RadioView):
            half=self.width//2
            area(1,3,max(1,half-2),3,'inset');area(half+1,3,max(1,self.width-half-2),3,'inset')
            area(1,9,self.width-2,max(0,self.body_height-13),'panel')
        elif isinstance(self,DirectoryView):
            for i,_ in enumerate(self.matches()):area(1,4+i*2,self.width-2,2,'panel')
            area(0,1,self.width,1,'inset')
        elif isinstance(self,NetsView):
            area(1,2,min(24,self.width-2),6,'panel')
            area(1,9,self.width-2,4,'panel')
        elif isinstance(self,ConnectivityView):
            for i in range(3):area(1,4+i*2,self.width-2,2,'panel')
        if getattr(self,'docks',None) and self.docks.foreign(self.app.name):
            spans.extend((row,0,self.width,'inset') for row in range(self.body_height,self.height-1))
        spans.extend([(0,0,self.width,'toolbar'),(self.body_height-2,0,self.width,'muted'),(self.body_height-1,0,self.width,'muted')])
        for row,line in enumerate(self.lines()):
            if line.lstrip().startswith('>'):spans.append((row,0,self.width,'selected'))
            for match in re.finditer(r'\[[^]]+\]',line):spans.append((row,match.start(),len(match.group()),'control'))
        if isinstance(self,ChatView):
            split=self.split()
            spans.append((self.body_height-4,split+1,max(1,self.width-split-2),'input' if self.focus==2 else 'control'))
            spans.append((0,0,split if self.focus==0 else self.width,'selected'))
        return tuple(spans)

    def detach(self,name):
        if getattr(self,'docks',None):
            from app_docks import PANES
            self.docks.place(next(p for p in PANES if p.window==name),'Floating');return
        if self.host:
            w=self.host.window(name);w.desktop=self.host.desktop
            self.host.activate(name)
        self.changed()
    def detached(self,name):
        if getattr(self,'docks',None):
            from app_docks import PANES
            pane=next(p for p in PANES if p.window==name)
            return self.docks.locations[name]!=pane.source
        return bool(self.host and self.host.window(name).opened and self.host.window(name).visible)
    def attach(self,name):
        if getattr(self,'docks',None):
            from app_docks import PANES
            pane=next(p for p in PANES if p.window==name)
            self.docks.place(pane,pane.source);return
        if self.host:
            w=self.host.window(name);self.host.invalidate(w.rect);w.opened=False;w.visible=False
            self.host.activate(self.app.name)
        self.changed()


@lru_cache(maxsize=8)
def map_plane(width,height,pan_x,pan_y,zoom,walk):
    rows=[]
    for y in range(height):
        row=[]
        for x in range(width):
            u=(x-width/2)/max(1,width)*zoom+pan_x
            v=(y-height/2)/max(1,height)*zoom+pan_y
            ridge=math.sin(u*9+v*3)*.32+math.cos(v*11-u*4)*.25
            stream=.12*math.sin(v*6)+.05
            if abs(u-stream)<.018*zoom:char='~'
            elif abs(v-.35*u-.1)<.012*zoom:char='=' if x%3 else '+'
            elif ridge>.44:char='^'
            elif ridge>.30:char=':'
            elif ridge>.12 and (x+y)%4==0:char='.'
            else:char=' '
            row.append(char)
        rows.append(''.join(row))
    return tuple(rows)


class MapView(View):
    def __init__(self,app,host=None):
        super().__init__(app,host);self.selection=SelectList(tuple(i.name for i in app.items))
        self.focus=0;self.pan_x=self.pan_y=0.;self.zoom=1.;self.packets=True;self.inspector=False
        self.walk=app.name=='Walk Test'
        self.map_center=(47.17,-122.52);self.map_renderer=None;self.map_image=None;self.map_preset=0;self.terrain=True;self.roads=True;self._layer=None;self._pan_drag=None
    def lines(self):
        if self.map_renderer:
            from offline_map import PRESETS
            _,origin,span=PRESETS[self.map_preset]
            center=(origin[0]-self.pan_y*span/111.32,origin[1]+self.pan_x*span/(111.32*math.cos(math.radians(origin[0]))))
            self.map_center=center
            mh,_,_=self.layout()
            image=self.map_renderer.frame(center,span*self.zoom,max(1,self.width-2),mh,self.terrain,self.roads)
            if image is not self.map_image:self.map_image=image;self.changed()
        return super().lines()
    def layer(self):
        self.lines()
        if self.map_image is None:return None
        image=self.map_image
        key=(id(image),self._signature)
        if getattr(self,'_layer_key',None)!=key:
            from offline_map import Plane
            cells={}
            for y in range(image.height):
                line=self._cached[y+2]
                for x in range(image.width):
                    char=line[x+1] if x+1<len(line) else ' '
                    base=image.cells[y*image.width+x]
                    if char!=base[0]:
                        under=base[1];bg=((under>>16)&255,(under>>8)&255,under&255)
                        from paint import ink
                        cells[y*image.width+x]=(char,ink(245,220,130,background=bg))
            self._layer=(1,2,image.width,image.height,Plane(image.cells,cells));self._layer_key=key
        return self._layer
    @property
    def index(self):return self.selection.index
    def key(self,key):
        if key in ('\t','backtab'):self.focus=1-self.focus
        elif key=='I' and not self.walk:self.detach('Packet Inspector');self.inspector=False
        elif key=='B' and self.host:self.host.activate('Terrain 3D')
        elif key=='g':self.map_preset=(self.map_preset+1)%3;self.pan_x=self.pan_y=0.;self.zoom=1.
        elif key=='t':self.terrain=not self.terrain
        elif key=='r':self.roads=not self.roads
        elif key=='x':self.inspector=not self.inspector
        elif key=='p':self.packets=not self.packets
        elif key=='v':self.packets=self.inspector=False;self.focus=0
        elif key in ('+','-','='):self.zoom=max(.25,min(4,self.zoom*(.8 if key in ('+','=') else 1.25)))
        elif key=='f':self.pan_x=self.pan_y=0.;self.zoom=1.
        elif self.focus==1 and self.selection.key(key):pass
        elif self.focus==0 and key in ('left','right','up','down'):
            if key in ('left','right'):self.pan_x+=(-.08 if key=='left' else .08)*self.zoom
            else:self.pan_y+=(-.08 if key=='up' else .08)*self.zoom
        elif key in ('\r','\n'):self.focus=1-self.focus
        else:return False
        self.changed();return True
    def layout(self):
        bottom=4 if self.packets else 0
        inspect=4 if self.inspector and not self.detached('Packet Inspector') and not self.walk else 0
        return max(2,self.body_height-4-bottom-inspect),bottom,inspect
    @property
    def pointer_captured(self):return self._pan_drag is not None
    def actions(self):return (('[p Packets]','p'),('[x Inspector]','x'),('[I Float]','I'),('[B 3D]','B'),('[f Fit]','f'))
    def pointer(self,column,row,width,button=0,released=False):
        self.width=width
        if released:self._pan_drag=None;return True
        mh,_,_=self.layout()
        if button&32:
            if self._pan_drag:
                x,y,px,py=self._pan_drag
                self.pan_x=px-(column-x)*self.zoom/max(1,width-3)
                self.pan_y=py-(row-y)*self.zoom*2/max(1,width-3)
                self.changed();return True
            return False
        if button&64:
            if self.packets and row>=self.body_height-5:
                self.focus=1;self.selection.key('down' if button&1 else 'up');self.changed();return True
            return self.key('-' if button&1 else '+')
        if button!=0:return False
        if row==0:
            key=toolbar_hit(self.actions(),column)
            return self.key(key) if key else True
        if row>=2+mh:
            self.focus=1;self.selection.pointer(row-(self.body_height-5),3)
        elif row>=2:
            self.focus=0;self._pan_drag=(column,row,self.pan_x,self.pan_y)
        self.changed();return True
    def spans(self):
        self.lines()
        if getattr(self,'_span_signature',None)==self._signature:return self._span_cache
        result=list(super().spans());mh,_,_=self.layout()
        for y in range(2,min(self.body_height-2,2+mh)):
            result.append((y,1,max(1,self.width-2),'map'))
            line=self.lines()[y]
            for match in re.finditer(r'[~]+|[\^:]+|[=+]+|[@*][ A-Z0-9-]*',line):
                char=match.group()[0]
                result.append((y,match.start(),len(match.group()),'water' if char=='~' else 'terrain' if char in '^:' else 'road' if char in '=+' else 'station'))
        self._span_signature=self._signature;self._span_cache=tuple(result)
        return self._span_cache

    def inspector_lines(self):
        item=self.app.items[self.index]
        return (item.name+' / '+item.summary,)+item.details+('Raw fixture: '+item.name+'>DEMO:sample payload',)+item.evidence
    def draw(self,c):
        if self.walk:c.put(1,0,'HISTORY  < '+self.app.items[self.index].name+' >   [Fit]')
        else:c.put(1,0,' '.join(label for label,_ in self.actions()))
        mh,bottom,inspect=self.layout();w=max(1,self.width-2)
        if self.map_renderer:
            from offline_map import PRESETS
            name,origin,span=PRESETS[self.map_preset]
            c.put(1,1,f'{name} / {span*self.zoom:g} km / offline terrain')
            image=self.map_image
            if image:
                for y in range(image.height):c.put(1,2+y,''.join(char for char,_ in image.cells[y*image.width:(y+1)*image.width]),w)
            else:c.put(2,3,self.map_renderer.error or 'Preparing offline terrain...')
        else:
            c.put(1,1,'Illustrative map / no GIS adapter')
            for y,line in enumerate(map_plane(w,mh,self.pan_x,self.pan_y,self.zoom,self.walk)):c.put(1,2+y,line,w)
        markers=tuple('rx '+str(i+1) for i in range(3 if self.index==0 else 2)) if self.walk else tuple(item.name for item in self.app.items)
        for i,label in enumerate(markers):
            px=2+round((.18+i*.25-self.pan_x)/self.zoom*max(1,w-4))
            py=3+round((.16+i*.20-self.pan_y)/self.zoom*max(1,mh-3))
            if self.map_renderer:
                lat,lon=47.17+(i-1)*.005,-122.52+(i-1)*.008
                cy,cx=self.map_center;scale=(w-1)/(span*self.zoom)
                px=1+round((w-1)/2+(lon-cx)*111.32*math.cos(math.radians(cy))*scale)
                py=2+round((mh-1)/2-(lat-cy)*111.32*scale/2)
            if 1<=px<self.width-2 and 2<=py<2+mh:
                c.put(px,py,('@' if i==(0 if self.walk else self.index) else '*')+' '+label,min(13,self.width-px-1))
                if self.walk:
                    for d in range(1,5):
                        if px-d>0 and py+d//2<2+mh:c.put(px-d,py+d//2,':')
        y=2+mh
        if inspect:
            c.rule(y);c.put(1,y,' INSPECTOR / same selected packet ')
            for i,line in enumerate(self.inspector_lines()[:3]):c.put(1,y+1+i,line)
        if bottom:
            y=self.body_height-6;c.rule(y)
            c.put(1,y,(' SESSIONS ' if self.walk else ' PACKETS ')+('< focused >' if self.focus else 'Tab to focus'))
            for i,item in enumerate(self.app.items[:3]):c.put(1,y+1+i,('> ' if i==self.index else '  ')+item.name+'  '+item.summary)
        c.put(0,self.body_height-2,' '*self.width)
        c.put(1,self.body_height-2,'Tab focus  +/- zoom  g place  t terrain  r roads')


class ChatView(View):
    def __init__(self,app,host=None):
        super().__init__(app,host);self.threads=SelectList(tuple(i.name for i in app.items));self.focus=0
        self.drafts={item.name:TextInput() for item in app.items};self.transcript=Transcript()
        self.saved={};self.notice='Local draft only'
    @property
    def index(self):return self.threads.index
    @property
    def draft(self):return self.drafts[self.app.items[self.index].name]
    def messages(self):
        item=self.app.items[self.index]
        return ((item.name+'  sample 13:42',item.details[0].split(': ',1)[-1]),('You  local draft',self.saved.get(item.name,'No message sent.')),(item.name+'  delivery evidence','No receipt'))
    def key(self,key):
        if key in ('\t','backtab'):self.focus=(self.focus+(-1 if key=='backtab' else 1))%3
        elif key=='\x1b':self.focus=0
        elif self.focus==2 and key in ('\r','\n'):
            self.saved[self.app.items[self.index].name]=self.draft.text;self.notice='Draft saved in this demo session; not sent'
        elif self.focus==2 and self.draft.key(key):pass
        elif key=='T':self.detach('Chat History')
        elif self.focus==0 and self.threads.key(key):self.transcript.scroll=0
        elif self.focus==1 and self.transcript.key(key):pass
        else:return False
        self.changed();return True
    def split(self):return max(10,min(20,self.width//4))
    def pointer(self,column,row,width,button=0,released=False):
        self.width=width
        if released:return False
        split=self.split()
        if row==0 and column>=split:self.detach('Chat History')
        elif column<split:
            self.focus=0
            if button&64:self.threads.key('down' if button&1 else 'up')
            elif row>=3:self.threads.pointer(row-3,max(1,self.body_height-6))
        elif row>=self.body_height-5:self.focus=2
        else:
            self.focus=1
            if button&64:self.transcript.key('down' if button&1 else 'up')
        self.changed();return True
    def draw(self,c):
        split=self.split();right=max(1,self.width-split-2)
        c.put(1,0,'THREADS',split-2);c.put(split+1,0,self.app.items[self.index].name+'   [T Float]')
        c.rule(1)
        self.threads.draw(c,1,3,split-2,max(1,self.body_height-6))
        for y in range(2,self.body_height-2):c.put(split,y,'|')
        if self.detached('Chat History'):c.put(split+2,3,'Transcript floated',right-1)
        else:self.transcript.draw(c,split+2,3,right-1,max(1,self.body_height-9),self.messages())
        c.rule(self.body_height-6,split+1,right)
        c.put(split+2,self.body_height-5,'DRAFT'+(' <typing>' if self.focus==2 else ' / Tab to edit'),right-1)
        c.put(split+2,self.body_height-4,self.draft.draw(right-2),right-1)
        c.put(split+2,self.body_height-3,self.notice,right-1)
        c.put(0,self.body_height-2,' '*self.width)
        c.put(1,self.body_height-2,'Tab focus   Enter save draft   Esc done')


class DirectoryView(View):
    def __init__(self,app,host=None):
        super().__init__(app,host);self.query=TextInput();self.editing=False;self.category=0;self.index=0
    def matches(self):
        rows=[i for i,item in enumerate(self.app.items) if self.query.text.lower() in (item.name+' '+item.summary).lower()]
        if self.category==1:rows=[i for i in rows if i<2]
        elif self.category==2:rows=[i for i in rows if i==2]
        return rows
    def key(self,key):
        if self.editing:
            if key in ('\x1b','\r','\n','\t'):self.editing=False
            elif not self.query.key(key):return False
            self.index=0
        elif key=='/':self.editing=True
        elif key in ('[',']'):self.category=(self.category+(-1 if key=='[' else 1))%3;self.index=0
        elif key in ('up','down'):self.index=max(0,min(max(0,len(self.matches())-1),self.index+(-1 if key=='up' else 1)))
        else:return False
        self.changed();return True
    def pointer(self,column,row,width,button=0,released=False):
        if released:return False
        if row==0:self.category=(self.category+1)%3;self.index=0
        elif row==1:self.editing=True
        elif button&64:return self.key('down' if button&1 else 'up')
        elif 4<=row<4+len(self.matches())*2:self.index=min(len(self.matches())-1,(row-4)//2)
        self.changed();return True
    def draw(self,c):
        tabs(c,('All heard','Services','Relays'),self.category)
        c.put(1,1,'Search / '+(self.query.draw(max(1,self.width-13)) if self.editing else self.query.text or 'press / to filter'))
        c.rule(2);rows=self.matches();self.index=min(self.index,max(0,len(rows)-1))
        for n,index in enumerate(rows):
            item=self.app.items[index];y=4+n*2
            c.put(1,y,('> ' if n==self.index else '  ')+item.name+'  / observed fixture')
            c.put(3,y+1,item.summary)
        y=min(self.body_height-7,5+len(rows)*2)
        if rows:
            item=self.app.items[rows[self.index]];c.rule(y);c.put(1,y,' ADVERTISED / '+item.name)
            for n,line in enumerate(item.details[:3]):c.put(2,y+1+n,line)
            c.put(2,y+4,'Evidence: fixture / freshness unknown')
        else:c.put(2,4,'No matching stations or services.')
        c.put(0,self.body_height-2,' '*self.width)
        c.put(1,self.body_height-2,'/ Search   [] Category   Esc done')


class NetsView(View):
    def __init__(self,app,host=None):
        super().__init__(app,host);self.index=0;self.reminders=set();self.month=10
    def key(self,key):
        if key in ('up','down'):self.index=max(0,min(len(self.app.items)-1,self.index+(-1 if key=='up' else 1)))
        elif key in ('left','right'):self.month=max(1,min(12,self.month+(-1 if key=='left' else 1)))
        elif key=='r':
            if self.index in self.reminders:self.reminders.remove(self.index)
            else:self.reminders.add(self.index)
        else:return False
        self.changed();return True
    def pointer(self,column,row,width,button=0,released=False):
        if released:return False
        if button&64:return self.key('down' if button&1 else 'up')
        if row==0:return self.key('left' if column<width//2 else 'right')
        if row>=9:self.index=min(len(self.app.items)-1,max(0,(row-9)//2))
        self.changed();return True
    def draw(self,c):
        c.put(1,0,'< '+calendar.month_name[self.month]+' 2026 >   AGENDA / examples')
        for y,line in enumerate(calendar.month(2026,self.month).splitlines()[1:]):c.put(2,y+2,line,22)
        if self.width>=47:
            c.put(27,3,'SCHEDULE EVIDENCE')
            c.wrap(27,5,'Unconfirmed. Date, time and zone needed.',self.width-28)
        c.rule(8);c.put(1,8,' SAMPLE AGENDA / no dated events ')
        for i,item in enumerate(self.app.items):
            c.put(1,9+i*2,('> ' if i==self.index else '  ')+item.name)
            c.put(3,10+i*2,'Time unconfirmed / reminder '+('mock on' if i in self.reminders else 'off'))
        if self.body_height>=19:
            c.rule(14);c.put(2,15,self.app.items[self.index].summary)
            c.put(2,16,'Reminder demo / not scheduled.')
        c.put(0,self.body_height-2,' '*self.width)
        c.put(1,self.body_height-2,'Arrows browse   r Reminder')


class RadioView(View):
    def __init__(self,app,host=None):
        super().__init__(app,host);self.page=0
        self.table=DataTable(('BANK','MEMORY','RX MHz'),(('Local','01 Sample','---.---'),('Local','02 Sample','---.---'),('Travel','01 Sample','---.---')))
    def key(self,key):
        if key in ('[',']','\t','backtab'):self.page=1-self.page
        elif self.table.key(key):pass
        else:return False
        self.changed();return True
    def pointer(self,column,row,width,button=0,released=False):
        if released:return False
        if row==0:self.page=1-self.page
        elif button&64:return self.key('down' if button&1 else 'up')
        elif row>=10:self.table.pointer(row-10,max(1,self.body_height-13))
        self.changed();return True
    def draw(self,c):
        tabs(c,('On radio','Saved presets'),self.page)
        c.put(1,2,'DISCONNECTED / read-only preview')
        half=max(12,self.width//2)
        c.put(2,3,'VFO A');c.put(half+1,3,'VFO B')
        c.put(2,4,'---.--- MHz');c.put(half+1,4,'---.--- MHz')
        c.put(2,5,'Memory: unknown');c.put(half+1,5,'Memory: unknown')
        c.put(2,6,'Signal [........] unknown')
        c.put(2,7,'Battery --%  /  sample age unknown')
        c.rule(8);c.put(1,8,' '+('MEMORY SNAPSHOT' if self.page==0 else 'SAVED PRESETS')+' / fixture rows ')
        self.table.draw(c,1,9,max(1,self.width-2),max(1,self.body_height-13))
        c.put(0,self.body_height-3,' '*self.width)
        c.put(1,self.body_height-3,'Selected: '+self.table.rows[self.table.index]+' / not tuned')
        c.put(0,self.body_height-2,' '*self.width)
        c.put(1,self.body_height-2,'[] View   Arrows memory   Read only')


class ConnectivityView(View):
    def __init__(self,app,host=None):
        super().__init__(app,host);self.selection=SelectList(tuple(i.name for i in app.items))
    def key(self,key):
        if not self.selection.key(key):return False
        self.changed();return True
    def pointer(self,column,row,width,button=0,released=False):
        if released:return False
        if button&64:return self.key('down' if button&1 else 'up')
        if row>=4:self.selection.pointer((row-4)//2,len(self.app.items))
        self.changed();return True
    def draw(self,c):
        c.put(1,0,'LINK HEALTH / observed state')
        c.put(2,2,'[ Feed ? ] -- [ Current state ] -- [ Views ]')
        for i,item in enumerate(self.app.items):
            y=4+i*2;c.put(1,y,('> ' if i==self.selection.index else '  ')+item.name)
            c.put(4,y+1,'[ ? ] UNKNOWN / no adapter sample')
        c.rule(11);c.put(1,11,' OBSERVATION LOG / fixture ')
        for i,line in enumerate(self.app.items[self.selection.index].details):c.put(2,12+i,line)
        c.put(0,self.body_height-3,' '*self.width)
        c.put(1,self.body_height-3,'Unknown / awaiting observations')
        c.put(0,self.body_height-2,' '*self.width)
        c.put(1,self.body_height-2,'Arrows source   Read only')


class DetachedView:
    def __init__(self,owner,name):self.owner,self.name=owner,name;self.width=48;self.height=16
    def key(self,key):
        if key in ('\r','\n','\x1b'):self.owner.attach(self.name);return True
        if self.name=='Packet Inspector' and self.owner.selection.key(key):self.owner.changed();return True
        if self.name=='Chat History' and self.owner.transcript.key(key):self.owner.changed();return True
        return False
    def pointer(self,column,row,width,button=0,released=False):
        if not released and row==0:return self.key('\r')
        if button&64 and not released:return self.key('down' if button&1 else 'up')
        return False
    def spans(self):return ((0,1,max(1,self.width-2),'control'),(self.height-1,0,self.width,'muted'))
    def lines(self):
        c=Canvas(self.width,self.height);c.put(1,0,'[ Reattach to '+self.owner.app.name+' ]');c.rule(1)
        if self.name=='Packet Inspector':
            y=3
            for line in self.owner.inspector_lines():y=c.wrap(1,y,line,max(1,self.width-2))
        else:self.owner.transcript.draw(c,1,3,max(1,self.width-2),max(1,self.height-5),self.owner.messages())
        c.put(1,self.height-1,'Enter reattach / shared selection / fixture')
        return c.lines()


def forms(apps,host=None):
    classes={'APRS':MapView,'Walk Test':MapView,'Conversations':ChatView,'Directory':DirectoryView,'Nets':NetsView,'Radio':RadioView,'Connectivity':ConnectivityView}
    result={a.name:classes[a.name](a,host) for a in apps}
    if host is not None:
        from offline_map import Renderer
        renderer=Renderer();host.app_renderers=(renderer,)
        result['APRS'].map_renderer=result['Walk Test'].map_renderer=renderer
        result['Terrain 3D']=BirdView(result['APRS'],renderer,host)
    result['Packet Inspector']=DetachedView(result['APRS'],'Packet Inspector')
    result['Chat History']=DetachedView(result['Conversations'],'Chat History')
    from app_docks import Docks,editor
    docks=Docks(host,result)
    for view in result.values():
        if isinstance(view,View):view.docks=docks
    if 'Terrain 3D' not in result:result['Terrain 3D']=BirdView(result['APRS'],None,host)
    result['Layout Edit']=editor(docks,tuple(a.name for a in apps))
    return result



class BirdView:
    def __init__(self,owner,renderer,host=None):
        self.owner,self.renderer,self.host=owner,renderer,host
        self.width,self.height=62,20;self.yaw=0.;self.tilt=.75;self.exaggeration=1;self.scenic=True
        self.image=None;self._layer=None;self._identity=None;self._drag=None;self.transition=None;self.show_inset=True;self.spin=False;self._spin_start=0.;self._spin_yaw=0.
    def mix(self):
        target=0. if self.scenic else 1.
        if self.transition:
            start,end,began=self.transition;t=min(1,(time.monotonic()-began)/2.5)
            if t>=1:self.transition=None;return end
            return start+(end-start)*(t*t*(3-2*t))
        return target
    def inset(self):
        return max(1,self.width-min(32,self.width//3)-2),3,max(8,min(32,self.width//3)),max(4,min(12,(self.height-6)//3))
    def key(self,key):
        if key in ('left','right','up','down'):self.spin=False
        if key in ('left','right'):self.yaw=round(self.yaw+(-.2 if key=='left' else .2),2)
        elif key in ('up','down'):self.tilt=round(max(.3,min(1.3,self.tilt+(.1 if key=='up' else -.1))),2)
        elif key=='v':
            start=self.mix();self.scenic=not self.scenic;self.transition=(start,0. if self.scenic else 1.,time.monotonic())
        elif key=='i':self.show_inset=not self.show_inset
        elif key=='s':
            self.spin=not self.spin;self._spin_start=time.monotonic();self._spin_yaw=self.yaw
        elif key=='e':self.exaggeration={1:2,2:4,4:1}[self.exaggeration]
        elif key=='g':return self.owner.key(key)
        elif key=='f':
            self.yaw=0.;self.tilt=.75;self.exaggeration=1;self.scenic=True;self.transition=None;self.spin=False
            return self.owner.key(key)
        elif key in ('+','-','='):return self.owner.key(key)
        else:return False
        return True
    @property
    def pointer_captured(self):return self._drag is not None
    def actions(self):return (('[v View]','v'),('[f Fit]','f'),('[g Place]','g'),('[e Height]','e'),('[i Map]','i'),('[s Spin]','s'))
    def pointer(self,column,row,width,button=0,released=False):
        if released:self._drag=None;return True
        if button&64:return self.key('-' if button&1 else '+')
        if button&32:
            if self._drag:
                x,y,yaw,tilt=self._drag
                self.yaw=round(yaw+(column-x)*.025,3)
                self.tilt=round(max(.3,min(1.3,tilt-(row-y)*.025)),3)
                return True
            return False
        if button==0 and row==0:
            key=toolbar_hit(self.actions(),column)
            return self.key(key) if key else True
        if button==0 and row>=2:self.spin=False;self._drag=(column,row,self.yaw,self.tilt);return True
        return False
    def lines(self):
        from offline_map import PRESETS
        name,_,span=PRESETS[self.owner.map_preset]
        if self.spin:self.yaw=self._spin_yaw+(time.monotonic()-self._spin_start)*.12
        self.owner.lines();mh,_,_=self.owner.layout()
        if self.renderer:
            image=self.renderer.frame3d(self.owner.map_center,span*self.owner.zoom,self.owner.width-2,mh,self.width,max(1,self.height-4),self.yaw,self.tilt,self.exaggeration,self.scenic,round(self.mix()*16)/16)
            # Retain the last complete surface while the next camera view prepares.
            if image is not None:self.image=image
            self.updating=image is None or bool(self.renderer.pending)
        c=Canvas(self.width,self.height)
        c.put(1,0,' '.join(label for label,_ in self.actions()))
        c.put(1,1,f'{name} / '+('Perspective' if self.scenic else 'Birds-eye')+f' / Z {self.exaggeration}x'+(' / updating' if getattr(self,'updating',False) else ''))
        if self.image:
            from offline_map import ScaledPlane
            plane=ScaledPlane(self.image.cells,self.image.width,self.image.height,self.width,max(1,self.height-4))
            for y in range(max(1,self.height-4)):c.put(0,y+2,''.join(plane[y*self.width+x][0] for x in range(self.width)))
            if self.show_inset and self.owner.map_image:
                ix,iy,iw,ih=self.inset();c.put(ix,iy-1,'[ 2D / same patch ]',iw)
                image=self.owner.map_image
                for y in range(ih):c.put(ix,iy+y,''.join(image.cells[min(image.height-1,y*image.height//ih)*image.width+min(image.width-1,x*image.width//iw)][0] for x in range(iw)))
        else:c.put(1,3,(self.renderer.error if self.renderer else None) or 'Preparing terrain mesh...')
        c.put(1,self.height-2,'Drag orbit  Wheel zoom  Arrows tilt/orbit')
        c.put(1,self.height-1,'Offline elevation / demo light / coarse mesh')
        return c.lines()
    def layer(self):
        if self.image is None:return None
        identity=(id(self.image),id(self.owner.map_image),self.width,self.height,self.show_inset)
        if identity!=self._identity:
            from offline_map import Plane,ScaledPlane
            self._identity=identity;plane=ScaledPlane(self.image.cells,self.image.width,self.image.height,self.width,max(1,self.height-4));overlay={}
            image=self.owner.map_image
            if self.show_inset and image:
                ix,iy,iw,ih=self.inset()
                for y in range(ih):
                    for x in range(iw):
                        if 0<=iy+y-2<self.height-4 and ix+x<self.width:
                            overlay[(iy+y-2)*self.width+ix+x]=image.cells[min(image.height-1,y*image.height//ih)*image.width+min(image.width-1,x*image.width//iw)]
                from paint import ink
                for x,char in enumerate('[ 2D / same patch ]'[:iw]):overlay[(iy-3)*self.width+ix+x]=(char,ink(180,220,220,background=(18,27,29)))
            self._layer=(0,2,self.width,max(1,self.height-4),Plane(plane,overlay))
        return self._layer
    def spans(self):return ((0,0,self.width,'control'),(1,0,self.width,'toolbar'),(self.height-2,0,self.width,'muted'),(self.height-1,0,self.width,'muted'))
