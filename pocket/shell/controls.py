"""Small reusable bound controls and panel presentations; event-loop-owned state."""
class Toggle:
    def __init__(self,label,get,set):self.label,self.get,self.set=label,get,set
    def read(self):return '[x]' if self.get() else '[ ]'
    def adjust(self,direction):self.set(not self.get())
    def row(self):return self.label,self.read,self.adjust

class Choice:
    def __init__(self,label,get,set,values):self.label,self.get,self.set,self.values=label,get,set,tuple(values)
    def read(self):return '< '+str(self.get())+' >'
    def adjust(self,direction):
        value=self.get();index=self.values.index(value) if value in self.values else 0
        self.set(self.values[(index+direction)%len(self.values)])
    def row(self):return self.label,self.read,self.adjust

class Slider:
    def __init__(self,label,get,set,minimum,maximum,step,format=lambda v:f'{v:g}'):
        self.label,self.get,self.set=label,get,set
        self.minimum,self.maximum,self.step,self.format=minimum,maximum,step,format
    def read(self):
        value=self.get();fill=round(8*(value-self.minimum)/(self.maximum-self.minimum))
        return '['+'='*fill+'-'*(8-fill)+'] '+self.format(value)
    def adjust(self,direction):self.set(round(max(self.minimum,min(self.maximum,self.get()+self.step*direction)),6))
    def row(self):return self.label,self.read,self.adjust

class TextPanel:
    def __init__(self,lines):self.content=tuple(lines);self.offset=0
    def key(self,key):
        if key not in ('up','down','pageup','pagedown'):return False
        self.offset=max(0,min(max(0,len(self.content)-1),self.offset+(-1 if key in ('up','pageup') else 1)))
        return True
    def lines(self):return self.content[self.offset:]

class StatusPanel:
    def __init__(self,rows):self.rows=rows
    def key(self,key):return False
    def lines(self):return tuple(f'{label}: {read()}' for label,read in self.rows)


def scene_controls(host):
    def bind(name):
        def set(value):
            host.set_preference(name,value);host.background_step=-1
            host.front=[None]*(host.width*host.height);host.invalidate((0,0,host.width,host.height))
        return lambda:getattr(host,name),set
    def choice(label,name,values):return Choice(label,*bind(name),values)
    def toggle(label,name):return Toggle(label,*bind(name))
    def slider(label,name,lo,hi,step,format):return Slider(label,*bind(name),lo,hi,step,format)
    return {'arrival':[slider('Arrival time','arrival_duration',.25,12,.25,lambda v:f'{v:g} s')],
            'flux':[choice('Rendering pace','flux_performance',('balanced','fast demo')),slider('Arms','flux_arms',0,4,1,lambda v:f'{v:g}'),slider('Density','flux_density',.5,4,.5,lambda v:f'{v:g}x'),slider('Glow','flux_glow',0,1,.05,lambda v:f'{v*100:.0f}%')],
            'windows':[toggle('Snap windows','snap_windows'),slider('Window opacity','window_opacity',0,1,.05,lambda v:f'{v*100:.0f}%')],
            'flurry':[slider('Strands','flurry_strands',8,192,8,lambda v:f'{v:g}'),slider('Sway','flurry_sway',0,1,.1,lambda v:f'{v*100:.0f}%'),slider('Speed','flurry_speed',.25,2,.25,lambda v:f'{v:g}x')],
            'sky':[choice('Terrain light','light_mode',('dynamic','day','night')),choice('Moon phase','moon_phase',('auto','full','waxing','crescent','new','waning')),choice('Season','season',('auto','spring','summer','autumn','winter')),toggle('Foliage','show_foliage'),toggle('Animals','show_animals'),toggle('Flowers','show_flowers'),slider('Mesh glow','terrain_grid',0,.35,.025,lambda v:f'{v*100:.0f}%')],
            'view':[slider('Parallax','parallax',0,.03,.005,lambda v:'off' if v==0 else f'{v*100:g}%'),slider('Overview zoom','overview_zoom',1,2.5,.15,lambda v:f'{v:g}x')],
            'shadows':[toggle('Window shadows','shadow_enabled'),slider('Size','shadow_size',1,4,1,lambda v:f'{v:g} cells'),slider('Strength','shadow_opacity',0,.85,.05,lambda v:f'{v*100:g}%'),choice('Direction','shadow_direction',('SE','S','SW','W','NW','N','NE','E')),toggle('Terrain shadows','terrain_shadows')]}


class Button:
    def __init__(self,label,action):self.label,self.action=label,action
    def read(self):return '[ Run ]'
    def adjust(self,direction):self.action()
    def row(self):return self.label,self.read,self.adjust

class Progress:
    def __init__(self,label,get):self.label,self.get=label,get
    def read(self):
        value=max(0,min(1,self.get()));fill=round(value*12)
        return '['+'='*fill+'-'*(12-fill)+f'] {round(value*100)}%'
    def row(self):return self.label,self.read,lambda d:None

class RadioList:
    def __init__(self,get,set,values):self.get,self.set,self.values=get,set,tuple(values)
    def rows(self):
        return [(str(value),lambda value=value:'(*)' if self.get()==value else '( )',lambda direction,value=value:self.set(value)) for value in self.values]

class SplitPane:
    """Two child views, one divider and local focus; no child windows or threads."""
    def __init__(self,left,right,width=54,ratio=.35):
        self.left,self.right,self.width,self.ratio=left,right,width,ratio
        self.focus=0

    def sizes(self):
        available=max(3,self.width-1)
        left=max(1,min(available-1,round(available*self.ratio)))
        return left,available-left

    def key(self,key):
        if key in ('\t','backtab'):
            self.focus=(self.focus+(-1 if key=='backtab' else 1))%3
            return True
        if self.focus==1:
            if key in ('left','right'):
                self.ratio=max(.2,min(.8,self.ratio+(-.05 if key=='left' else .05)))
                return True
            return False
        return (self.left if self.focus==0 else self.right).key(key)

    def pointer(self,column,row,width,button=0,released=False):
        self.width=width
        left,right=self.sizes()
        if released:return False
        if button==0:
            self.focus=0 if column<left else 1 if column==left else 2
        if self.focus==1:
            if button&64:self.key('left' if button&1 else 'right')
            return True
        child=self.left if self.focus==0 else self.right
        if hasattr(child,'pointer'):
            return child.pointer(column if self.focus==0 else column-left-1,row-1,left if self.focus==0 else right,button,released) if row>0 else True
        return child.key('down' if button&1 else 'up') if button&64 else True

    def lines(self):
        left,right=self.sizes()
        for child,width in ((self.left,left),(self.right,right)):
            if hasattr(child,'width'):child.width=width
        a=('> Navigation' if self.focus==0 else '  Navigation',)+self.left.lines()
        b=('> Content' if self.focus==2 else '  Content',)+self.right.lines()
        rows=tuple((a[i] if i<len(a) else '')[:left].ljust(left)+(':' if self.focus==1 else '|')+(b[i] if i<len(b) else '')[:right] for i in range(max(len(a),len(b))))
        return rows+('', 'Tab: pane / divider | divider: arrows or wheel')
