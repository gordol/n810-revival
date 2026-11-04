"""Declarative pane ownership and a small explicit layout editor."""
from collections import namedtuple


class Pane(namedtuple('Pane','title source window',defaults=())):
    __slots__=()
    title:str
    source:str
    window:str


PANES=(Pane('Packet inspector','APRS','Packet Inspector'),Pane('Chat transcript','Conversations','Chat History'))


class Docks:
    def __init__(self,host,views):
        self.host,self.views=host,views
        self.locations={p.window:p.source for p in PANES}
    def foreign(self,target):
        return next((p for p in PANES if self.locations[p.window]==target and p.source!=target),None)
    def place(self,pane,target):
        if target!='Floating' and self.foreign(target) not in (None,pane):
            other=self.foreign(target);self.locations[other.window]=other.source
        self.locations[pane.window]=target
        if target==pane.source and pane.source=='APRS':self.views['APRS'].inspector=True
        if self.host:
            w=self.host.window(pane.window);self.host.invalidate(w.rect)
            w.visible=w.opened=target=='Floating'
            if target=='Floating':w.desktop=self.host.desktop;self.host.activate(w.name)
            else:self.host.activate(target)
        for view in self.views.values():
            if hasattr(view,'changed'):view.changed()
    def rows(self,pane):
        owner=self.views[pane.source]
        if pane.source=='APRS':return owner.inspector_lines()
        return tuple(sender+': '+text for sender,text in owner.messages())
    def reset(self):
        for pane in PANES:self.place(pane,pane.source)
        self.views['APRS'].inspector=False
        self.views['APRS'].changed()


def editor(docks,names):
    from controls import Choice,Button
    from settings import SettingsWindow
    selected=[0];target=['Floating']
    def choose(value):selected[0]=next(i for i,p in enumerate(PANES) if p.title==value)
    def place():docks.place(PANES[selected[0]],target[0])
    rows=[Choice('Pane',lambda:PANES[selected[0]].title,choose,tuple(p.title for p in PANES)).row(),
          Choice('Move to',lambda:target[0],lambda value:target.__setitem__(0,value),('Floating',)+tuple(names)).row(),
          Button('Move pane',place).row(),Button('Reset panes',docks.reset).row(),
          ('Current home',lambda:docks.locations[PANES[selected[0]].window],lambda d:None),
          ('Layout memory',lambda:'off while reviewing',lambda d:None)]
    return SettingsWindow([('Layout edit',rows)],width=52)
