"""Read-only observation presentation; transport and protocol policy stay in adapters."""
from collections import namedtuple
import math
class Peer(namedtuple('Peer','protocol network address',defaults=())):
    __slots__=()
    protocol:str
    network:str
    address:str
class Position(namedtuple('Position','lat lon recorded_at',defaults=(None,))):
    __slots__=()
    lat:float
    lon:float
    recorded_at:str | None
    def __post_init__(self):
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (self.lat,self.lon)) or not -90<=self.lat<=90 or not -180<=self.lon<=180:raise ValueError('Invalid position')

    def __new__(cls,lat,lon,recorded_at=None):
        self=super().__new__(cls,lat,lon,recorded_at)
        self.__post_init__()
        return self
class Observation(namedtuple('Observation','id peer name recorded_at position roles path path_kind summary',defaults=(None,(),(),'unavailable','',))):
    __slots__=()
    id:str
    peer:Peer
    name:str
    recorded_at:str | None
    position:Position | None
    roles:tuple
    path:tuple
    path_kind:str
    summary:str
class Snapshot(namedtuple('Snapshot','observations selected reference source status scope',defaults=((),None,None,'Source unavailable','Unavailable','Retained receptions; not proof of live RF arrival',))):
    __slots__=()
    observations:tuple
    selected:Observation | None
    reference:Position | None
    source:str
    status:str
    scope:str

def direction(origin,target):
    """Great-circle distance and true-north initial bearing, or no bearing if coincident."""
    a,b=map(math.radians,(origin.lat,target.lat));delta=math.radians((target.lon-origin.lon+180)%360-180)
    h=math.sin((b-a)/2)**2+math.cos(a)*math.cos(b)*math.sin(delta/2)**2
    distance=6371.0088*2*math.asin(math.sqrt(max(0,min(1,h))))
    if distance<1e-9:return distance,None
    bearing=math.degrees(math.atan2(math.sin(delta)*math.cos(b),math.cos(a)*math.sin(b)-math.sin(a)*math.cos(b)*math.cos(delta)))%360
    return distance,bearing
