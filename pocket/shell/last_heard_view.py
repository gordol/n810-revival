"""Compact last-heard presentation, over the same cached provider contract."""
from app_widgets import Canvas
from last_heard_model import direction
class LastHeard:
    def __init__(self,provider):self.provider=provider;self.width=56;self.height=18;self.mode='last';self._spans=()
    def key(self,key):
        if key in ('s','l'):self.mode='selected' if key=='s' else 'last';return True
        return False
    def pointer(self,x,y,width=None,button=0,released=False):
        if button!=0 or released or y!=self.height-2 or not 0<=x<min(self.width,32):return False
        return self.key('l' if x<15 else 's')
    def lines(self):
        snapshot=self.provider();c=Canvas(self.width,self.height);footer=max(0,self.height-4)
        def put(y,text,role='panel',x=0,width=None):
            if y>=footer:return
            c.put(x,y,text,width);c.role(x,y,min(len(str(text)),self.width-x) if width is None else width,role)
        def section(y,title):
            put(y,title+' '+'─'*max(0,self.width-len(title)-1),'muted')
        put(0,'Last heard' if self.mode=='last' else 'Selected station','heading')
        item=snapshot.selected if self.mode=='selected' else next(iter(snapshot.observations[-1:]),None)
        if item is None:put(2,'No selected station' if self.mode=='selected' else 'No retained station reception','muted')
        else:
            protocol=item.peer.protocol.upper();c.right_label(0,0,self.width,protocol);c.role(max(0,self.width-len(protocol)),0,len(protocol),'muted')
            name=item.name if item.name!=item.peer.address else ''
            put(2,item.peer.address+('  '+name if name else ''),'heading')
            put(3,', '.join(item.roles[:6]) if item.roles else 'Role unknown','muted')
            if item.position is None:put(5,'Station position unknown','muted')
            elif snapshot.reference is None:put(5,'Own position unknown · bearing unavailable','muted')
            else:
                km,bearing=direction(snapshot.reference,item.position)
                heading='same location' if bearing is None else f'{bearing:03.0f}° '+('N','NE','E','SE','S','SW','W','NW')[int((bearing+22.5)//45)%8]
                put(4,'DISTANCE','muted');put(5,f'{km:.1f} km','heading')
                if self.width>=36:
                    put(4,'TRUE BEARING','muted',x=18);put(5,heading,'heading',x=18)
                    if self.width>=44:
                        x=self.width-7;put(4,'N','muted',x=x+2);put(5,'W '+('·' if bearing is None else ('↑','↗','→','↘','↓','↙','←','↖')[int((bearing+22.5)//45)%8])+' E','heading',x=x);put(6,'S','muted',x=x+2)
                else:put(6,heading+' · true north','heading')
            section(7,'RECORDED TIMES')
            put(8,'RX       '+str(item.recorded_at or 'unknown'),'body')
            put(9,'Station  '+str((item.position.recorded_at if item.position else None) or 'unknown'),'muted')
            put(10,'Own fix  '+str((snapshot.reference.recorded_at if snapshot.reference else None) or 'unknown'),'muted')
            # Never show a hop chain without its complete evidence qualifier.
            if item.path:
                if 13<footer and item.path_kind and len(item.path_kind)<=self.width:
                    section(11,'PATH EVIDENCE');put(12,' → '.join(item.path[:8]),'body');put(13,item.path_kind,'muted')
                else:put(11,'Path evidence hidden','muted')
            else:put(11,'Path unknown','muted')
        c.put(0,footer,snapshot.status+' · '+snapshot.source);c.role(0,footer,self.width,'status')
        c.put(0,footer+1,snapshot.scope);c.role(0,footer+1,self.width,'muted')
        c.put(0,footer+2,'l Last heard   s Selected station');c.role(0,footer+2,self.width,'control')
        self._spans=tuple(c.styled_spans());return c.lines()
    def navigation_action_spans(self,key):
        return ((self.height-2,0 if key=='l' else 15,14 if key=='l' else min(17,max(0,self.width-15)),'input'),)
    def spans(self):return self._spans
