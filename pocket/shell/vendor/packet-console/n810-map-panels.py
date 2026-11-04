"""Small shared visibility/focus state and terminal panel rectangles."""

class PanelState:
    def __init__(self,visible=(),focus='map',names=('packets','inspector')):
        self.names=tuple(names);self.visible=set(visible)&set(self.names)
        self.focus=focus if focus in self.visible else 'map'
    def toggle(self,name):
        if name not in self.names:raise ValueError('Unknown panel')
        if name in self.visible:
            self.visible.remove(name)
            if self.focus==name:self.focus='map'
        else:self.visible.add(name);self.focus=name
    def focus_next(self):
        choices=['map']+[name for name in self.names if name in self.visible]
        self.focus=choices[(choices.index(self.focus)+1)%len(choices)] if self.focus in choices else 'map'
        return self.focus
    def focus_map(self):self.focus='map'
    def map_only(self):self.visible.clear();self.focus='map'


def layout(width,height,visible=(),names=('packets','inspector'),top_rows=2,bottom_rows=2):
    """Whole-terminal map, tinted bars and up to two nonoverlapping panels."""
    if width<1 or height<1:return {}
    top=min(height,max(0,top_rows));bottom=min(height-top,max(0,bottom_rows))
    result={'map':(0,0,width,height),'top':(0,0,width,top),'bottom':(0,height-bottom,width,bottom)}
    order=tuple(names);names=[name for name in order if name in visible][:2]
    y=top+1;available=height-bottom-1-y
    if not names or width<24 or available<3:return result
    if len(names)==1:
        name=names[0];first=name==order[0]
        w=min(44 if first else 62,width-2);h=min(20,available) if first else available
        result[name]=(1 if first else width-w-1,y,w,h)
    elif width>=84:
        left=min(44,(width-3)//2);right=min(62,width-left-3)
        result[names[0]]=(1,y,left,min(20,available))
        result[names[1]]=(width-right-1,y,right,available)
    elif available>=5:
        first=(available-1)//2;second=available-first-1
        result[names[0]]=(1,y,width-2,first)
        result[names[1]]=(1,y+first+1,width-2,second)
    return result
