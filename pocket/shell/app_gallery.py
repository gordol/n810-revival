"""Reviewable app shells with immutable fixtures; no adapters or device actions."""
from dataclasses import dataclass
from core import Window
from controls import SplitPane
from session import RETIRED


@dataclass(frozen=True,slots=True)
class Item:
    name:str
    summary:str
    details:tuple
    evidence:tuple


@dataclass(frozen=True,slots=True)
class App:
    name:str
    desktop:int
    purpose:str
    items:tuple
    map:bool=False


def item(name,summary,*details):
    return Item(name,summary,details,('Source: local review fixture','Freshness: unknown / not live','Provider: not connected'))


APPS=(
    App('APRS',1,'Stations / map / received packet',(
        item('DEMO-1','Portable station','Position: illustrative only','Symbol: portable','Path: sample direct reception'),
        item('DEMO-2','Weather station','Temperature: sample 8 C','Wind: sample SW 3 m/s','Position: illustrative only'),
        item('DEMO-3','Relay candidate','Relay role: unconfirmed','No inference from symbol alone')),True),
    App('Conversations',1,'Threads / messages / contact evidence',(
        item('DEMO-1','Trail check-in','DEMO-1: At the trail junction.','Local draft: Meeting point?','Draft only; sending unavailable'),
        item('DEMO-2','Weather question','DEMO-2: Rain near the pass.','Delivery: no receipt evidence'))),
    App('Directory',2,'Services / advertised details / provenance',(
        item('Trail bulletin','Information service','Category: bulletin','Availability: unknown','Advertised position != receive point'),
        item('Weather source','Environmental reports','Category: weather','Address: fixture only','Discovery adapter not connected'),
        item('Regional relay','Infrastructure candidate','Capability: unconfirmed','No automatic connection'))),
    App('Nets',2,'Agenda / net details / reminders',(
        item('Evening check-in','Sample agenda entry','Schedule: example only','Time zone: must come from source','Reminder: off'),
        item('Trail coordination','Sample local net','Frequency: not supplied','No tuning or transmit controls','Reminder: off'))),
    App('Walk Test',2,'Sessions / reception points / map',(
        item('Sample ridge walk','3 illustrative reception points','Own receive position: fixture','Remote station position: distinct','Coverage estimate: not measured'),
        item('Sample valley walk','2 illustrative reception points','Session import: not connected','Missing GPS must stay unknown')),True),
    App('Radio',2,'Read-only status / telemetry / evidence',(
        item('Connection','Disconnected','Transport owner: external adapter','No competing Bluetooth connection','No tune / PTT / transmit actions'),
        item('Telemetry','No live sample','Battery: unknown','Signal: unknown','Sample age: unknown'),
        item('Memory preview','Read-only placeholder','Memory snapshot: not supplied','Live radio state is separate'))),
    App('Connectivity',2,'Links / observations / current evidence',(
        item('Packet feed','Not connected','Socket adapter: not connected','Last receive time: unknown','Observation != confirmed reachability'),
        item('Position','No position source','GPS fix: unknown','Own position not inferred from APRS'),
        item('Radio transport','Externally owned','Read-only adapter required','No transport opened by this shell'))),
)
NAMES=tuple(a.name for a in APPS)


def windows(width,height):
    result=[]
    for app in APPS:
        siblings=[a.name for a in APPS if a.desktop==app.desktop]
        index=siblings.index(app.name)
        preferred={'Conversations':(54,28),'Directory':(58,26),'Nets':(56,25),'Radio':(48,19),'Connectivity':(48,18)}
        if app.name in ('APRS','Walk Test'):
            sidebar=54 if app.name=='APRS' else 50
            w=width-sidebar-3 if width>=110 else width-2
            h=height-2;x=y=1
        else:
            pw,ph=preferred[app.name];w=min(pw,width-2);h=min(ph,height-2)
            x=1 if app.name=='Directory' else 61 if app.name=='Nets' and width>=120 else max(1,width-w-1)
            y=1 if app.name!='Connectivity' else min(21,max(1,height-h-1))
            x=min(max(0,width-w),x)
        result.append(Window(app.name,x,y,w,h,desktop=app.desktop,opened=True,visible=app.name!='Walk Test'))
    for name in ('Packet Inspector','Chat History','Layout Edit','Terrain 3D'):
        w,h=(max(12,min(width-2,182)),max(8,min(height-2,74))) if name=='Terrain 3D' else (min(width,54),min(height,18))
        result.append(Window(name,max(0,width-w-2),min(3,max(0,height-h)),w,h,opened=False,visible=False))
    return result


def open_workspace(host):
    for spec in windows(host.width,host.height):
        target=host.window(spec.name)
        for key in ('x','y','w','h','desktop','visible','opened','rolled','pinned'):
            setattr(target,key,getattr(spec,key))
    for form in getattr(host,'app_forms',{}).values():
        if hasattr(form,'changed'):form.changed()
    views=getattr(host,'app_forms',{})
    if 'APRS' in views:views['APRS'].docks.reset()
    host.desktop=0;host.focus=None;host.desktop_focus.clear();host.invalidate((0,0,host.width,host.height))


def forms(host=None):
    from app_views import forms as app_forms
    return app_forms(APPS,host)
