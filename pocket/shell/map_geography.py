"""Offline through-roads and collision-limited geographic labels for map views."""
import gzip,json,math,hashlib
from array import array
from functools import lru_cache
from pathlib import Path
from data_paths import data_root
PATH=data_root()/'map-geography.json.gz'
INDEX=PATH.parent/'geography/index.json'
def signature():
 p=INDEX if INDEX.is_file() else PATH
 if not p.is_file():return ()
 s=p.stat();return str(p),s.st_mtime_ns,s.st_size
@lru_cache(maxsize=2)
def load(identity):
 if not identity:return dict(roads=[],labels=[])
 p=Path(identity[0]);raw=p.read_bytes()
 return json.loads(gzip.decompress(raw) if p.suffix=='.gz' else raw)
@lru_cache(maxsize=32)
def tile(path,digest):
 raw=Path(path).read_bytes()
 if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Geography tile integrity failure')
 return json.loads(gzip.decompress(raw))
def data_for_view(view,display_span=None):
 data=load(signature())
 if 'tiles' not in data:return data
 if (view.span if display_span is None else display_span)>80:return dict(roads=data.get('overview_roads',[]),streams=[],labels=data['labels'])
 west,south,east,north=view.bbox;step=data['step'];a,b,c,d=data['coverage'];roads={};streams={}
 if east<a or west>c or north<b or south>d:return dict(roads=[],streams=[],labels=data['labels'])
 for iy in range(math.floor(max(south,b)/step),math.floor(min(north,d)/step)+1):
  for ix in range(math.floor(max(west,a)/step),math.floor(min(east,c)/step)+1):
   row=data['tiles'].get(f'{ix},{iy}')
   if row is None:continue
   pack=tile(str(INDEX.parent/row['file']),row['sha256'])
   for n,r in enumerate(pack['roads']):roads[r.get('id',('road',r.get('name'),tuple(r['bbox'])))]=r
   for n,r in enumerate(pack['streams']):streams[r.get('id',('stream',n))]=r
 return dict(roads=tuple(roads.values()),streams=tuple(streams.values()),labels=data['labels'])
def covers(view):
 data=load(signature());bounds=data.get('coverage')
 if not bounds or 'tiles' not in data:return False
 a,b,c,d=bounds;w,s,e,n=view.bbox
 return a<=w<=e<=c and b<=s<=n<=d

def selected_geography(engine,view,roads=True,display_span=None,detail_pixels=1,forest_roads=None,forest_only=False):
 """Select geographic features once for terminal and pixel consumers."""
 span=view.span if display_span is None else display_span
 data=data_for_view(view,span);west,south,east,north=view.bbox
 def intersects(item):
  a,b,c,d=item.get('bbox',(-180,-90,180,90))
  return not (c<west or a>east or d<south or b>north)
 streams=tuple(item for item in data.get('streams',())
               if intersects(item) and (view.ground_m_per_halfcell<=250 or item.get('kind')=='river'))
 chosen=[]
 show_forest=getattr(engine,'forest_roads',False) if forest_roads is None else forest_roads
 if roads:
  for item in data.get('roads',()):
   role=item.get('kind')
   if (forest_only and role!='forest') or (role=='forest' and not show_forest):continue
   # The terminal has one stroke per cell; the native scene has eight pixels.
   # Cull minor roads before a wide cell map becomes a field of road glyphs.
   limit={'residential':20,'unclassified':20,'living_street':12,'service':8,
          'tertiary':60,'secondary':120,'primary':240,'trunk':400}.get(role)
   if limit is not None and view.ground_m_per_halfcell/max(1,detail_pixels)>limit:continue
   if limit is None and span>item.get('max_span',100):continue
   if intersects(item):chosen.append(item)
 return streams,tuple(chosen),data.get('labels',())

def vector_segments(engine,view,roads=True,detail_pixels=1,forest_roads=None,forest_only=False):
 """Return geographic road and stream geometry selected for this view."""
 if covers(view):
  streams,chosen,_=selected_geography(engine,view,roads,detail_pixels=detail_pixels,
                                     forest_roads=forest_roads,forest_only=forest_only)
  groups=((chosen,(219,205,155)),) if forest_only else ((streams,(55,177,196)),(chosen,(219,205,155)))
  for items,color in groups:
   points=array('d')
   for item in items:
    for first,last in zip(item['points'],item['points'][1:]):points.extend((*first,*last))
   yield color,points
  return
 if forest_only or view.ground_m_per_halfcell>6000:return
 atlas=engine.atlas
 west,south,east,north=(round(v*100000) for v in view.bbox)
 for role,layer in [*enumerate(atlas.roads),*(([(2,atlas.streams)]) if atlas.streams else [])]:
  if role!=2 and not roads:continue
  if role==0 and view.ground_m_per_halfcell>=150 or role==2 and view.ground_m_per_halfcell>=250:continue
  extent=engine.layer_bounds.get(id(layer))
  if not extent:continue
  a,b,c,d=max(west,extent[0]),max(south,extent[1]),min(east,extent[2]),min(north,extent[3])
  if a>c or b>d:continue
  ids=set();tile=layer['tile']
  for y in range(b//tile,d//tile+1):
   for x in range(a//tile,c//tile+1):ids.update(layer['index'].get((x,y),()))
  points=array('d');coords=layer['coords']
  for i in sorted(ids):points.extend(value/100000 for value in coords[i*4:i*4+4])
  yield ((55,177,196) if role==2 else (219,205,155)),points

def _semantic_labels(engine,view,frame,roads=True,display_span=None,forest_roads=None):
 # A narrow edge patch inherits the whole display's road/label detail level.
 span=view.span if display_span is None else display_span
 streams,chosen,place_labels=selected_geography(engine,view,roads,span,forest_roads=forest_roads)
 labels=[];w,h=view.width,view.height
 west,south,east,north=view.bbox
 def visible(lon,lat):return west<=lon<=east and south<=lat<=north
 for stream in streams:
  if frame is None and (not stream.get('name') or span>=8):continue
  shown=[]
  for a,b in zip(stream['points'],stream['points'][1:]):
   x,y=map(round,view.project(*a));xx,yy=map(round,view.project(*b));line=engine.geometry.clip(x,y,xx,yy,w,h)
   if line is None:continue
   x,y,xx,yy=map(round,line);dx,dy=abs(xx-x),abs(yy-y);steps=max(dx,dy,1)
   glyph='─' if dx>dy*2 else '│' if dy>dx*2 else '/' if (xx-x)*(yy-y)<0 else '\\'
   for i in range(steps+1):
    px,py=round(x+(xx-x)*i/steps),round(y+(yy-y)*i/steps);j=py*w+px
    if frame is not None:frame[j]=(glyph,(55,177,196),frame[j][2])
    shown.append((px,py))
  if shown and stream.get('name') and span<8:
   x,y=shown[len(shown)//2];labels.append((2,stream['name'],x,y,(100,210,235)))
 if roads:
  for road in chosen:
   label_limit={'highway':150,'motorway':100,'trunk':70,'primary':15,'secondary':10,'tertiary':5,'forest':8,'residential':1.2,'living_street':.8,'service':.6,'unclassified':2}.get(road.get('kind'),3)
   if frame is None and (not road.get('name') or span>label_limit):continue
   pts=road['points'];shown=[]
   for a,b in zip(pts,pts[1:]):
    x,y=map(round,view.project(*a));xx,yy=map(round,view.project(*b))
    line=engine.geometry.clip(x,y,xx,yy,w,h)
    if line is None:continue
    x,y,xx,yy=map(round,line);dx,dy=abs(xx-x),abs(yy-y);err=dx-dy;sx=1 if x<xx else -1;sy=1 if y<yy else -1
    glyph='─' if dx>dy*2 else '│' if dy>dx*2 else '/' if (xx-x)*(yy-y)<0 else '\\'
    while True:
     i=y*w+x
     if frame is not None:frame[i]=(glyph,(219,205,155),frame[i][2])
     shown.append((x,y))
     if x==xx and y==yy:break
     e=2*err
     if e>-dy:err-=dy;x+=sx
     if e<dx:err+=dx;y+=sy
   if shown and road.get('name') and span<=label_limit:
    name=road['name']
    for word,short in (('Southwest','SW'),('Northwest','NW'),('Southeast','SE'),('Northeast','NE'),('Boulevard','Blvd'),('Avenue','Ave'),('Drive','Dr'),('Street','St'),('Road','Rd')):name=name.replace(word,short)
    x,y=shown[len(shown)//2];labels.append((2 if road.get('kind')=='highway' else 3,name,x,y,(235,220,175)))
 from map_hydrography import labels as hydro_labels
 for p in [*engine.labels,*hydro_labels(),*place_labels]:
  if not visible(p['lon'],p['lat']):continue
  kind=p.get('kind','town');limit=p.get('max_span',200 if kind=='city' else 70 if kind in ('town','village') else 25)
  if span>limit:continue
  x,y=map(round,view.project(p['lon'],p['lat']))
  water=kind in ('water','lake','bay');labels.append((1 if water else 0,p.get('name',p.get('label','')),x,y,(100,210,235) if water else (245,241,216)))
 occupied=set();names=set();budget=max(3,min(16,w*h//300));marks={}
 for _,name,x,y,color in sorted(labels,key=lambda p:(p[0],(p[2]-w/2)**2+(p[3]-h/2)**2,p[1])):
  if not name or name.casefold() in names or len(names)>=budget:continue
  text=name[:max(1,w-2)];x=max(0,min(w-len(text),x-len(text)//2));y=max(0,min(h-1,y-1))
  area={(xx,yy) for xx in range(max(0,x-2),min(w,x+len(text)+2)) for yy in range(max(0,y-1),min(h,y+2))}
  if occupied.intersection(area):continue
  for n,ch in enumerate(text):marks[y*w+x+n]=(ch,color,(20,35,30))
  occupied.update(area);names.add(name.casefold())
 return marks

def decorate(engine,view,frame,roads=True,display_span=None):
 frame=list(frame)
 for index,cell in _semantic_labels(engine,view,frame,roads,display_span).items():frame[index]=cell
 return tuple(frame)

def label_annotations(engine,view,roads=True,display_span=None,forest_roads=None):
 """Expose place and road-name labels without decoding painted map cells."""
 from paint import ink
 return {index:(char,ink(*foreground,background=background))
         for index,(char,foreground,background) in _semantic_labels(engine,view,None,roads,display_span,forest_roads).items()}

def maidenhead(lat,lon,precision=6):
 lon=max(0,min(359.999999,lon+180));lat=max(0,min(179.999999,lat+90))
 a=int(lon/20);b=int(lat/10);lon-=a*20;lat-=b*10
 text=chr(65+a)+chr(65+b)+str(int(lon/2))+str(int(lat));lon=lon%2;lat=lat%1
 if precision>=6:text+=chr(97+min(23,int(lon*12)))+chr(97+min(23,int(lat*24)))
 if precision>=8:text+=str(int(lon*120)%10)+str(int(lat*240)%10)
 return text

def grid_features(view):
 """Geographic grid geometry and text annotations for pixel presentation."""
 from paint import ink
 west,south,east,north=view.bbox;w,h=view.width,view.height
 precision=8 if view.span<2 else 6 if view.span<120 else 4
 dx,dy={4:(2,1),6:(1/12,1/24),8:(1/120,1/240)}[precision]
 points=array('d');labels={};style=ink(183,209,219,background=(22,39,42))
 for ix in range(math.floor((west+180)/dx),math.ceil((east+180)/dx)+1):
  lon=ix*dx-180
  if not west<=lon<=east:continue
  points.extend((lon,south,lon,north))
  for iy in range(math.floor((south+90)/dy),math.ceil((north+90)/dy)+1):
   lat=iy*dy-90
   if not south<=lat<=north:continue
   text=maidenhead(lat+dy/2,lon+dx/2,precision)
   x,y=map(round,view.project(lon,lat));y=min(h-1,y+1)
   if x+len(text)+1>=w:continue
   for i,char in enumerate(text):labels[y*w+x+i+1]=(char,style)
 for iy in range(math.floor((south+90)/dy),math.ceil((north+90)/dy)+1):
  lat=iy*dy-90
  if south<=lat<=north:points.extend((west,lat,east,lat))
 return ((117,143,153),points),labels

def grid_enabled(mode,span):return mode=='on' or mode=='auto' and span<8

def grid(view):
 """Return sparse optional Maidenhead lines; stations and path render above it."""
 from paint import ink
 w,h=view.width,view.height;west,south,east,north=view.bbox
 precision=8 if view.span<2 else 6 if view.span<120 else 4
 dx,dy={4:(2,1),6:(1/12,1/24),8:(1/120,1/240)}[precision]
 out={};style=ink(117,143,153,background=(22,39,42));label=ink(183,209,219,background=(22,39,42))
 for ix in range(math.floor((west+180)/dx),math.ceil((east+180)/dx)):
  lon=ix*dx-180;x=round(view.project(lon,view.center[0])[0])
  if not 0<=x<w:continue
  for y in range(0,h,2):out[y*w+x]=('┆',style)
  for iy in range(math.floor((south+90)/dy),math.ceil((north+90)/dy)):
   lat=iy*dy-90;y=round(view.project(lon,lat)[1])
   if not 0<=y<h:continue
   for xx in range(w):
    if xx%2==0:out[y*w+xx]=('┄',style)
   text=maidenhead(lat+dy/2,lon+dx/2,precision)
   for n,ch in enumerate(text):
    if x+1+n<w:out[min(h-1,y+1)*w+x+1+n]=(ch,label)
 return out
