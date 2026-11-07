#!/usr/bin/env python3
"""Small receive-only APRS dashboard. Receiver remains a separate process."""
import argparse
import collections
import contextlib
import curses
import datetime
import json
import math
import os
import re
import selectors
import socket
import subprocess
import sys
import time
import textwrap
import importlib.util
import hashlib

_tracks_spec=importlib.util.spec_from_file_location('station_tracks',os.path.join(os.path.dirname(__file__),'n810-station-tracks.py'))
station_tracks=importlib.util.module_from_spec(_tracks_spec);_tracks_spec.loader.exec_module(station_tracks)

_runtime_spec=importlib.util.spec_from_file_location('viewer_runtime',os.path.join(os.path.dirname(__file__),'n810-runtime.py'))
runtime=importlib.util.module_from_spec(_runtime_spec);_runtime_spec.loader.exec_module(runtime)

_map_spec = importlib.util.spec_from_file_location("n810_map", os.path.join(os.path.dirname(__file__), "n810-map.py"))
_map = importlib.util.module_from_spec(_map_spec)
_map_spec.loader.exec_module(_map)
_visibility_spec=importlib.util.spec_from_file_location('viewer_visible',os.path.join(os.path.dirname(__file__),'n810-ui-visible.py'))
visibility=importlib.util.module_from_spec(_visibility_spec);_visibility_spec.loader.exec_module(visibility)

_map_style_spec=importlib.util.spec_from_file_location('viewer_map_style',os.path.join(os.path.dirname(__file__),'n810-map-style.py'))
map_style=importlib.util.module_from_spec(_map_style_spec);_map_style_spec.loader.exec_module(map_style)

_ui_spec=importlib.util.spec_from_file_location('ui_state',os.path.join(os.path.dirname(__file__),'n810-ui-state.py'))
ui_state=importlib.util.module_from_spec(_ui_spec);_ui_spec.loader.exec_module(ui_state)

LINE = re.compile(r'^(\d\d:\d\d:\d\d) (\S+)>(\S+) ctl=([0-9a-f]+) pid=f0 (.*)$')
POSITION = re.compile(r'(\d{2})(\d{2}\.\d{2})([NS])(.)(\d{3})(\d{2}\.\d{2})([EW])')


_decode_spec=importlib.util.spec_from_file_location('aprs_decode',os.path.join(os.path.dirname(__file__),'n810-aprs-decode.py'))
aprs_decode=importlib.util.module_from_spec(_decode_spec);_decode_spec.loader.exec_module(aprs_decode)


def position(payload,destination=''):
    return aprs_decode.decode(payload,destination).get('position')


def packet_position(packet):
    return packet.get('decoded',{}).get('position') or position(packet['payload'],packet['route'].split(',')[0])


class State:
    def __init__(self):
        self.packets = collections.deque(maxlen=200)
        self.stations = {}
        self.tracks=station_tracks.Tracks()
        self.focus = 'list'
        self.terrain = False
        self.selected=0
        self.call_filter=None
        self.filter_history=[]
        self.selection_expired=False
        self.follow_latest=True
        self.transport_read_time=None
        self.total = 0
        self.status = 'Connecting to UV-PRO...'

    def add(self, line, historical=False):
        m = LINE.match(line)
        if not m:
            if line.strip():
                self.status = line.strip()[:180]
            return None
        stamp, call, route, control, payload = m.groups()
        row = dict(time=stamp, call=call, route=route, payload=payload,
                   received=datetime.datetime.now().astimezone().isoformat(), historical=historical, raw=line)
        row['decoded']=aprs_decode.decode(payload,route.split(',')[0])
        row['facts']=aprs_decode.facts(row['decoded'])
        if (getattr(self,'map_engine_name','legacy')=='next' and not self.follow_latest
                and len(self.packets)==self.packets.maxlen and self.selected==len(self.packets)-1
                and (not self.call_filter or self.packets[self.selected]['call']==self.call_filter)):
            self.selection_expired=True
        if getattr(self, 'selected', 0)>0 or (self.packets and not self.follow_latest):
            self.selected=min(getattr(self,'selected',0)+1,199)
        self.packets.appendleft(row)
        self.total += 1
        loc = packet_position(row)
        if loc:
            self.stations[call] = dict(row, lat=loc[0], lon=loc[1])
            # Decoded feed has no full capture date/replay marker; age stays unknown.
            self.tracks.add(call,*loc,stamp=stamp)
        self.status = 'Receiving APRS'
        return row


def put(win, y, x, text, width, attr=0):
    h, w = win.getmaxyx()
    if 0 <= y < h and 0 <= x < w and width > 0:
        try:
            win.addnstr(y, x, str(text), min(width, w-x-1), attr)
        except curses.error:
            pass


def ink(n):
    return map_style.ink(n)


def summary(payload,decoded=None):
    loc=decoded.get('position') if decoded is not None else position(payload)
    if loc:
        east=(loc[1]+122.52)*111.32*math.cos(math.radians(47.17))
        north=(loc[0]-47.17)*111.32
        direction=['N','NE','E','SE','S','SW','W','NW'][round(math.degrees(math.atan2(east,north))/45)%8]
        return 'Pos %dkm %s' % (round(math.hypot(east,north)),direction)
    if payload.startswith(':'):return 'Message  '+payload[1:]
    if payload.startswith('}'):return 'Relayed packet'
    if payload.startswith('>'):return 'Status   '+payload[1:]
    if payload.startswith(('`',"'")):return 'Mic-E    '+payload[1:]
    return payload


def friendly_status(text):
    if text.split('|',1)[0].strip()=='REPLAY':return text
    if text=='Receiving APRS' and os.environ.get('N810_DEV_MODE')=='REPLAY':
        return 'REPLAY  |  receiving recorded APRS  |  TX disabled'
    if 'Listening' in text or text=='Receiving APRS' or text.startswith('Radio settings unchanged'):
        return 'RADIO CONNECTED  |  listening for APRS'
    if text.startswith('UV-PRO connected'):return 'RADIO CONNECTED'
    if 'disconnected' in text.lower() or 'unavailable' in text.lower():return 'OFFLINE  |  waiting to reconnect'
    if 'Connecting' in text:return 'CONNECTING  |  radio / feed'
    return text


def packet_rows(state):
    call=state.call_filter if getattr(state,'map_engine_name','legacy')=='next' else None
    return [(i,row) for i,row in enumerate(state.packets) if not call or row['call']==call]


def selected_row(state):
    if getattr(state,'map_engine_name','legacy')=='next' and state.selection_expired:return None
    rows=packet_rows(state)
    if not rows:return None
    indices=[i for i,_ in rows]
    if getattr(state,'selected',0) not in indices:state.selected=indices[0]
    return state.packets[state.selected]


def move_selection(state,delta):
    rows=packet_rows(state)
    if not rows:return
    state.map_target=None
    state.selection_expired=False
    selected_row(state)
    indices=[i for i,_ in rows];index=indices.index(state.selected)
    state.selected=indices[max(0,min(len(indices)-1,index+delta))]
    if getattr(state,'map_engine_name','legacy')=='next':state.follow_latest=False


def packet_identity(packet,record=None):
    if packet is None:return dict(capture_id=None,local_record_key=None)
    capture=packet.get('capture_id')
    if record and record.get('time') and record.get('frame'):
        capture=hashlib.sha256((record['time']+record['frame']).encode()).hexdigest()
    return dict(capture_id=capture,local_record_key='decoded:'+hashlib.sha256(packet['raw'].encode()).hexdigest())


def workspace_view(state):
    panels=trial_panels(state)
    packet=selected_row(state)
    target=external_target(state)
    if target and packet and packet['call']!=target['call']:packet=None
    identity=packet_identity(packet)
    names={'packets':'list','inspector':'inspector','map':'map'}
    return dict(selected_capture_id=identity['capture_id'],local_record_key=identity['local_record_key'],
                selected_station=target['call'] if target else packet['call'] if packet else None,
                external_target=dict(station=target['call'],source=target.get('source','directory'),position_known='position' in target) if target else None,
                filter_scope='app',filter=dict(station=state.call_filter,query='',type=None,direction=None,history='all'),
                windows=dict(map=True,list='packets' in panels.visible,inspector='inspector' in panels.visible),
                focus=names[panels.focus],freshness=dict(captured=packet.get('capture_time') if packet else None,
                    fetched=state.transport_read_time,stale=None),
                capabilities=dict(receive=True,inspect=True,transmit=False,tune=False,program=False))


def filter_station(state,call,remember=True):
    if remember:state.filter_history.append(state.call_filter);state.filter_history=state.filter_history[-16:]
    state.call_filter=call
    state.map_target=None
    state.selection_expired=False
    state.follow_latest=False
    state.auto_fit=False
    selected_row(state)


def external_target(state):
    target=getattr(state,'map_target',None)
    if not target:return None
    if getattr(state,'map_engine_name','legacy')!='next':return target
    if 'position' not in target and target['call'] in state.stations:
        station=state.stations[target['call']]
        target=dict(target,position=[station['lat'],station['lon']],source='retained history',
                    position_time='date unknown / '+station.get('time','unknown'))
    return target


def activate_external_target(state,request,remember=True):
    if remember and getattr(state,'tracks',None):state.tracks.pause()
    call=request['call']
    if not isinstance(call,str) or not re.fullmatch(r'[A-Z0-9-]{1,16}',call):raise ValueError('Invalid station target')
    target={key:request[key] for key in ('call','id','source','position_time') if key in request}
    if request.get('position') is not None:
        lat,lon=map(float,request['position'])
        if not (math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180):
            raise ValueError('Invalid station position')
        target['position']=[lat,lon]
    previous=selected_row(state);old=getattr(state,'map_target',None)
    if remember:
        context=old.get('return_context') if old else None
        target['return_context']=context or dict(station=state.call_filter,
            raw=previous['raw'] if previous else None,expired=state.selection_expired)
    elif isinstance(request.get('return_context'),dict):target['return_context']=request['return_context']
    auto_fit=state.auto_fit
    filter_station(state,call,remember=False)
    matches=[i for i,row in enumerate(state.packets) if row['call']==call]
    if previous and previous['call']==call:
        state.selected=next(i for i in matches if state.packets[i] is previous)
    elif matches:state.selected=matches[0]
    state.map_target=target
    state.auto_fit=False if remember else auto_fit
    state.selection_expired=False
    trial_panels(state).focus_map();state.focus='detail';state.debug=False


def cancel_external_target(state):
    target=getattr(state,'map_target',None)
    if not target:return
    context=target.get('return_context')
    state.map_target=None
    if not isinstance(context,dict):return
    filter_station(state,context.get('station'),remember=False)
    raw=context.get('raw')
    if raw:
        matches=[i for i,row in enumerate(state.packets) if row['raw']==raw]
        if matches:state.selected=matches[0]
        else:state.selection_expired=True
    if context.get('expired'):state.selection_expired=True


def mapped_packet(state):
    """A retained packet may supply a route only for the displayed station."""
    packet=selected_row(state)
    target=getattr(state,'map_target',None)
    if target and (getattr(state,'map_engine_name','legacy')!='next'
                   or packet is None or packet['call']!=target['call']):return None
    return packet


def fitted_span(state,width,height,span):
    if not state.auto_fit:return span
    points=[(47.17,-122.52)]+[(p['lat'],p['lon']) for p in state.stations.values() if not state.call_filter or p['call']==state.call_filter]
    target=external_target(state)
    if getattr(state,'map_engine_name','legacy')=='next' and target and 'position' in target:points.append(target['position'])
    # Keep nearby named mountains in the regional overview, not just RF stations.
    for label in place_labels(state):
        if label.get('kind')=='peak' and abs(label['lat']-47.17)<2 and abs(label['lon']+122.52)<3:
            points.append((label['lat'],label['lon']))
    if len(points)==1:
        state.center=[47.38,-122.52]
        return 160.0
    south=min(p[0] for p in points);north=max(p[0] for p in points)
    west=min(p[1] for p in points);east=max(p[1] for p in points)
    state.center=[(south+north)/2,(west+east)/2]
    east_km=(east-west)*111.32*math.cos(math.radians(state.center[0]))
    north_km=(north-south)*111.32
    needed=max(60,east_km*1.5,north_km*1.5*max(1,width-1)/max(1,2*(height-1)))
    for size in (80,120,160,240,320,480,640,960,1600,2400,4800,9600,24000,48000):
        if size>=needed:return float(size)
    return 48000.0


def toggle_station_follow(state):
    tracks=state.tracks
    target=getattr(state,'map_target',None)
    packet=selected_row(state)
    call=target['call'] if target else packet['call'] if packet else None
    if tracks.call and tracks.paused and (not target or call==tracks.call):tracks.resume()
    elif tracks.call==call:tracks.stop()
    elif call:tracks.follow(call)
    if tracks.call:
        state.auto_fit=False
        state.map_target=None


def apply_station_follow(state):
    position=state.tracks.camera_position()
    if position is not None:
        state.center=list(position);state.auto_fit=False


def follow_caption(state):
    tracks=state.tracks
    if not tracks.call:return ''
    mode='camera paused' if tracks.paused else 'following'
    return tracks.call+' / '+mode+' / '+tracks.freshness(time.time())+' / reported-position trail'


def selection_caption(state):
    if getattr(state,'tracks',None) and state.tracks.call:return follow_caption(state)
    if getattr(state,'map_target',None):
        target=external_target(state)
        if getattr(state,'map_engine_name','legacy')=='next':
            return target['call']+': external '+('last known position' if 'position' in target else 'location unknown')+' / '+target.get('source','directory')+' / '+target.get('position_time','time unknown')+(' / retained packet route; last known relay positions' if mapped_packet(state) else '')
        return target['call']+(': last known position / '+target.get('position_time','') if 'position' in target else ': location unknown')
    packet=selected_row(state)
    if state.selection_expired:return 'Selection left retained history; select another record'
    if packet is None:return 'No packets match filter' if state.call_filter else 'No packet selected'
    if packet_position(packet):
        return packet['call'] + ': packet position / @ selected'
    if packet['call'] in state.stations:
        return packet['call'] + ': last known position / @ selected'
    relays=[hop.rstrip('*') for hop in packet['route'].split(',')[1:]
            if hop.endswith('*') and hop.rstrip('*') in state.stations]
    return packet['call'] + ': location unknown' + (' / relays: '+', '.join(relays) if relays else ' / no located used relays')


def include_selection(state, span, width, height):
    """Expand a manual view to contain its old bounds plus selected position."""
    if state.auto_fit:return span
    if getattr(state,'map_engine_name','legacy')!='next' and not state.packets:return span
    packet=mapped_packet(state)
    target=external_target(state)
    if packet is None and (not target or getattr(state,'map_engine_name','legacy')!='next'):return span
    loc=packet_position(packet) if packet else None
    station=state.stations.get(packet['call']) if packet else None
    if loc is None and station:loc=(station['lat'],station['lon'])
    if target:loc=target.get('position')
    points=[loc] if loc is not None else []
    if getattr(state,'map_engine_name','legacy')=='next' and packet:
        for hop in packet['route'].split(',')[1:]:
            relay=state.stations.get(hop.rstrip('*')) if hop.endswith('*') else None
            if relay:points.append((relay['lat'],relay['lon']))
    if not points:return span
    cos=max(.05,math.cos(math.radians(state.center[0])))
    half_lon=span/(2*111.32*cos)
    half_lat=span*max(1,height-1)/(max(1,width-1)*111.32)
    south,north=state.center[0]-half_lat,state.center[0]+half_lat
    west,east=state.center[1]-half_lon,state.center[1]+half_lon
    if all(south<=lat<=north and west<=lon<=east for lat,lon in points):return span
    south=min(south,*(lat for lat,lon in points));north=max(north,*(lat for lat,lon in points))
    west=min(west,*(lon for lat,lon in points));east=max(east,*(lon for lat,lon in points))
    state.center=[(south+north)/2,(west+east)/2]
    horizontal=(east-west)*111.32*math.cos(math.radians(state.center[0]))
    vertical=(north-south)*111.32*max(1,width-1)/(2*max(1,height-1))
    return max(span,horizontal,vertical)*1.05


def init_map(state,directory,engine='legacy',theme='current'):
    state.map_engine_name=engine
    state.map_engine=None
    state.tui_theme=None
    if engine=='legacy':
        state.atlas=_map.Atlas(directory,os.path.expanduser('~/.cache/n810-aprs/map-bases'))
        return
    spec=importlib.util.spec_from_file_location('viewer_map_next',os.path.join(os.path.dirname(__file__),'n810-map-next.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    state.map_next=module
    if theme in ('restrained','color'):state.tui_theme=module.load('viewer_tui_theme','n810-aprs-theme.py')
    style='rgb' if module.rgb_enabled() else 'ansi'
    options=dict(palette=state.tui_theme) if state.tui_theme is not None else {}
    state.map_engine=module.Engine(directory,style=style,attribute=map_style.cell_attr,**options)
    state.atlas=state.map_engine


def erase_view(win,state):
    state.canvas_signature=None
    state.pending_map=None
    win.erase()
    engine=getattr(state,'map_engine',None)
    if engine is not None:engine.invalidate()


def begin_frame(win,state,map_rect=None):
    """Keep the trial map surface intact while clearing surrounding UI cells."""
    state.pending_map=None
    engine=getattr(state,'map_engine',None)
    h,w=win.getmaxyx()
    signature=(h,w,map_rect)
    if engine is None or map_rect is None or getattr(state,'canvas_signature',None)!=signature:
        erase_view(win,state)
        state.canvas_signature=signature if engine is not None and map_rect is not None else None
        return
    x0,y0,width,height=map_rect
    for y in range(h):
        if y0<=y<y0+height:
            put(win,y,0,' '*x0,x0)
            start=x0+width
            put(win,y,start,' '*max(0,w-start),w-start)
        else:
            put(win,y,0,' '*w,w)


# Match the existing N810 console foreground colors; terrain is engine-owned.
MAP_FOREGROUND=tuple(tuple(bytes.fromhex(color)) for color in (
    '0b1015','273d32','142f27','3b4635','193f59','4b5553','6d787b','adb6b5',
    '4a555a','c28778','93cfa5','c4bf8c','5e9bc0','b1a0c2','98c8c7','dde4df'))


def label_backplate(state):
    return getattr(getattr(state,'tui_theme',None),'BACKPLATE',(14,21,18))


def rgb_overlays(state,cells,backplate=None):
    converted=state.map_next.ansi_overlays(cells,colors=MAP_FOREGROUND,backplate=backplate)
    theme=getattr(state,'tui_theme',None)
    if theme is not None:
        for key,(char,attr) in cells.items():
            if attr==selected_attr(state):converted[key]=(char,theme.SELECTION_TEXT,theme.SELECTION_FILL)
    return converted


def finish_frame(win,state):
    win.refresh()
    pending=getattr(state,'pending_map',None)
    if pending is not None:
        overlays,x0,y0=pending
        state.pending_map=None
        state.map_engine.draw(overlays,x0=x0,y0=y0)


def map_panel(win,state,span,x0,y0,width,height):
    if width<8 or height<3:return
    engine=getattr(state,'map_engine',None)
    if engine is not None:
        viewport=state.map_next.Viewport(state.center,span,width,height)
        engine.prepare(viewport,terrain=state.terrain,roads=state.roads)
        overlays=map_overlays(state,span,width,height,viewport)
        if engine.style=='rgb':
            overlays=rgb_overlays(state,overlays,backplate=label_backplate(state))
            state.pending_map=(overlays,x0,y0)
        else:
            engine.draw(overlays,x0=x0,y0=y0,win=win)
        if state.atlas.errors:put(win,y0+height-1,x0,'Map pack error (? for details)',width,ink(3))
        return
    base_key=(tuple(state.center),span,width,height,state.roads)
    if getattr(state,'base_key',None) != base_key:
        state.base_cells=state.atlas.background(state.center,span,width,height,state.roads)
        state.base_key=base_key
    cells,names=state.base_cells
    for (x,y),(char,kind) in cells.items():
        attr=map_style.cell_attr(kind,getattr(state,'terrain',True))
        put(win,y0+y,x0+x,char,1,attr)
    for (x,y),(char,attr) in map_overlays(state,span,width,height).items():
        put(win,y0+y,x0+x,char,1,attr)
    if not names:put(win,y0,x0,'No offline map coverage',width,ink(3))
    if state.atlas.errors:put(win,y0+height-1,x0,'Map pack error (? for details)',width,ink(3))


def selected_attr(state):
    if getattr(state,'map_engine_name','legacy')=='next':
        return ink(72)|curses.A_REVERSE
    return ink(7)|curses.A_BOLD


def map_dimensions(state,width,height):
    if getattr(state,'map_engine_name','legacy')=='next':return width-1,height
    return width-max(29,int(width*.40))-4,max(1,height-14)


def place_labels(state,viewport=None):
    atlas=getattr(state,'atlas',None)
    if atlas is None:return ()
    if getattr(state,'map_engine_name','legacy')=='next':
        return atlas.places(viewport)
    return tuple(label for pack in atlas.packs for label in pack['labels'])


def map_overlays(state,span,width,height,viewport=None):
    """Build local foreground cells independently of geography and screen output."""
    cells={}
    def emit(y,x,text,count,attr=0):
        if not 0<=y<height:return
        for offset,char in enumerate(str(text)[:max(0,count)]):
            xx=x+offset
            if 0<=xx<width:cells[xx,y]=(char,attr)
    tracks=getattr(state,'tracks',None)
    if tracks and tracks.call:
        for point in tracks.points():
            x,y=viewport.project(point['lon'],point['lat']) if viewport is not None else state.atlas.project(point['lon'],point['lat'],state.center,span,width,height)
            emit(round(y),round(x),':',1,ink(3)|curses.A_BOLD)
    occupied=set()
    selected_packet=mapped_packet(state)
    relay_calls={hop.rstrip('*') for hop in selected_packet['route'].split(',')[1:] if hop.endswith('*')} if selected_packet else set()
    chosen=selected_packet['call'] if selected_packet else None
    if getattr(state,'map_target',None):chosen=state.map_target['call']
    known=dict(state.stations)
    target=external_target(state)
    if getattr(state,'map_engine_name','legacy')=='next' and target and 'position' in target:
        lat,lon=target['position'];known[target['call']]=dict(call=target['call'],lat=lat,lon=lon)
    visible_stations=[p for p in known.values() if not state.call_filter or p['call']==state.call_filter or p['call'] in relay_calls or (tracks and p['call']==tracks.call)]
    stations=sorted(visible_stations,key=lambda p:(p['call']!=chosen,p['call'] not in relay_calls,p['call'].split('-')[0]!=getattr(state,'my_call','N0DEM').split('-')[0]))
    def pixel(lon,lat):
        x,y=viewport.project(lon,lat) if viewport is not None else state.atlas.project(lon,lat,state.center,span,width,height)
        return round(x),round(y)
    selected = None
    if selected_packet:
        selected = selected_packet
        previous = known.get(selected['call'])
        for hop in selected['route'].split(',')[1:]:
            if not hop.endswith('*'):
                previous = None
                continue
            current = state.stations.get(hop.rstrip('*'))
            if previous and current:
                ax,ay=pixel(previous['lon'],previous['lat']);bx,by=pixel(current['lon'],current['lat'])
                steps=max(abs(bx-ax),abs(by-ay),1)
                # Sample at screen resolution even for off-screen distant stations.
                if steps <= 10000:
                    for n in range(1,steps):
                        x=round(ax+(bx-ax)*n/steps);y=round(ay+(by-ay)*n/steps)
                        if 0<=x<width and 0<=y<height:emit(y,x,'·',1,ink(3)|curses.A_BOLD)
            previous=current
    # Reserve every marker before placing text; later labels cannot erase them.
    markers={pixel(p['lon'],p['lat']) for p in stations}
    markers={(x,y) for x,y in markers if 0<=x<width and 0<=y<height}
    occupied.update(markers)
    def label(lon,lat,text,attr,marker=None):
        x,y=pixel(lon,lat)
        if not (0<=x<width and 0<=y<height):return
        candidates=[(x+2,y),(x-len(text)-1,y),(x+1,y-1),(x+1,y+1),(x-len(text)//2,y-2),(x-len(text)//2,y+2)]
        for start,yy in candidates:
            if not (0<=yy<height):continue
            start=min(max(0,start),max(0,width-len(text)))
            area={(xx,yy) for xx in range(start,min(width,start+len(text)))}
            if not (occupied & area):
                emit(yy,start,text,width-start,attr)
                occupied.update((xx,yy) for xx in range(max(0,start-1),min(width,start+len(text)+1)))
                return
    ref=pixel(-122.52,47.17)
    # A coarse reference is unnecessary when it crowds a received station.
    show_ref=0<=ref[0]<width and 0<=ref[1]<height and not any(abs(ref[0]-x)<=2 and abs(ref[1]-y)<=1 for x,y in markers)
    if show_ref:
        occupied.add(ref)
        emit(ref[1],ref[0],'+',1,ink(1))
        label(-122.52,47.17,'Lakewood ref',ink(1))
    labeled=[];ordinary=0
    limit=6 if span>=240 else 12 if span>=120 else 1000
    for p in stations:
        mine=p['call'].split('-')[0]==getattr(state,'my_call','N0DEM').split('-')[0]
        important=p['call']==chosen or mine or p['call'] in relay_calls or (tracks and p['call']==tracks.call)
        x,y=pixel(p['lon'],p['lat'])
        if not (0<=x<width and 0<=y<height):continue
        if not important and (ordinary>=limit or (span>=120 and any(abs(x-xx)<10 and abs(y-yy)<3 for xx,yy in labeled))):continue
        label(p['lon'],p['lat'],p['call'],selected_attr(state) if p['call']==chosen else (ink(3) if p['call'] in relay_calls else ink(4))|curses.A_BOLD)
        labeled.append((x,y))
        if not important:ordinary+=1
    # Draw markers last, with the user's station winning a shared screen cell.
    for p in reversed(stations):
        x,y=pixel(p['lon'],p['lat'])
        if 0<=x<width and 0<=y<height:emit(y,x,'@' if p['call']==chosen else '*',1,selected_attr(state) if p['call']==chosen else (ink(3) if p['call'] in relay_calls else ink(4))|curses.A_BOLD)
    places=place_labels(state,viewport)
    count=0
    for p in sorted(places,key=lambda p:((getattr(state,'map_engine_name','legacy')=='next' and 'rainier' not in p['name'].lower()),p.get('kind')!='peak',-p.get('population',0),p['name'])):
        if p['name']=='Lakewood':continue
        x,y=viewport.project(p['lon'],p['lat']) if viewport is not None else state.atlas.project(p['lon'],p['lat'],state.center,span,width,height)
        if not (0<=x<width and 0<=y<height):continue
        if count>=4:break
        count+=1
        label(p['lon'],p['lat'],p['name'].replace('Mount ','Mt '),ink(1))
    return cells


_raw_cache = {}

def raw_record(packet, socket_path, snapshot_socket=None):
    """Read a frozen RX snapshot; never open a live/TX radio endpoint."""
    records = []
    endpoint=snapshot_socket or os.path.join(os.path.dirname(socket_path), 'n810-aprs-replay.sock')
    cached = _raw_cache.get(endpoint)
    if cached and time.monotonic()-cached[0] < 2:
        records = cached[1]
    try:
        if cached and time.monotonic()-cached[0] < 2:
            raise InterruptedError()
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(.35)
            client.connect(endpoint)
            with client.makefile('rb') as stream:
                header = json.loads(stream.readline(4096))
                if header.get('type') != 'snapshot' or header.get('version') != 1:
                    raise ValueError('Unsupported snapshot')
                for _ in range(min(int(header['records']), 200)):
                    records.append(json.loads(stream.readline(150000)))
    except InterruptedError:
        pass
    except (OSError, ValueError, KeyError):
        if snapshot_socket:return None
        try:
            with open(os.path.expanduser('~/.local/state/n810-aprs/raw-frames.json')) as stream:
                records = json.load(stream).get('records', [])
        except (OSError, ValueError, AttributeError):
            return None
    _raw_cache[endpoint] = (cached[0] if cached and records is cached[1] else time.monotonic(), records)
    try:
        spec = importlib.util.spec_from_file_location('packet_monitor', os.path.join(os.path.dirname(__file__), 'n810-packet-monitor.py'))
        monitor = importlib.util.module_from_spec(spec); spec.loader.exec_module(monitor)
        for record in reversed(records):
            if record.get('direction') != 'radio_to_host':
                continue
            frame = bytes.fromhex(record['frame'])
            stamp = datetime.datetime.fromisoformat(record['time']).strftime('%H:%M:%S')
            if stamp + ' ' + (monitor.describe(frame) or '') == packet['raw']:
                return record
    except (OSError, ValueError, KeyError, ImportError):
        pass
    return None


def inspector_lines(packet, record, width):
    route = packet['route'].split(',')
    lines = [packet['call'] + '  >  ' + route[0],
             'Time    ' + packet.get('time', '--:--:--'),
             'Path    ' + (' → '.join(route[1:]) or 'Direct / no digipeaters'),
             '', 'DECODED']
    facts=packet.get('facts')
    if facts is None:facts=aprs_decode.facts(aprs_decode.decode(packet.get('payload',''),route[0]))
    for fact in facts:
        lines += textwrap.wrap(fact,max(16,width))
    lines += ['', 'PAYLOAD']
    lines += textwrap.wrap(packet.get('payload', packet['raw']), max(16, width), replace_whitespace=False, drop_whitespace=False)
    lines += ['', 'CAPTURE']
    if record is None:
        return lines + ['Decoded text only · original bytes unavailable',
                        'Older address flags cannot be reconstructed.', '', 'FEED TEXT'] + textwrap.wrap(packet['raw'], max(16,width))
    data = bytes.fromhex(record['frame'])
    lines += [record['time'],
              '%d bytes · radio → host · RF origin unverified' % len(data),
              '', 'BYTES  /  HEX + ASCII',
              'Offset  KISS command at 0000 · AX.25 at 0001', '']
    for offset in range(0, len(data), 8):
        chunk = data[offset:offset+8]
        lines.append('%04x    %-23s  %s' % (offset, chunk.hex(' '), ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)))
    return lines


def trial_panels(state):
    if not hasattr(state,'panel_model'):
        spec=importlib.util.spec_from_file_location('viewer_panels',os.path.join(os.path.dirname(__file__),'n810-map-panels.py'))
        state.panel_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(state.panel_module)
        state.panel_model=state.panel_module.PanelState()
    return state.panel_model


def trial_panel_key(state,key):
    if getattr(state,'map_engine_name','legacy')!='next':return False
    panels=trial_panels(state)
    if key in (ord('p'),ord('x')):panels.toggle('packets' if key==ord('p') else 'inspector')
    elif key==ord('v'):panels.map_only()
    elif key==ord('c'):
        packet=selected_row(state)
        if packet:filter_station(state,packet['call'])
    elif key==ord('a'):filter_station(state,None)
    elif key in (curses.KEY_BACKSPACE,127,8):
        if getattr(state,'map_target',None):cancel_external_target(state)
        elif state.filter_history:filter_station(state,state.filter_history.pop(),remember=False)
    elif key==ord('z'):panels.focus_map()
    elif key==9:panels.focus_next()
    elif key in (10,13,curses.KEY_ENTER):
        if not panels.visible:panels.toggle('packets')
        elif panels.focus=='map':panels.focus_next()
        else:panels.focus_map()
    elif key in (curses.KEY_LEFT,curses.KEY_RIGHT) and panels.focus!='map':
        target='packets' if key==curses.KEY_LEFT else 'inspector'
        if target in panels.visible:panels.focus=target
        else:panels.focus_map()
    else:return False
    state.focus='detail' if panels.focus=='map' else 'list'
    state.debug=False
    if panels.focus!='map':state.follow_latest=False
    return True


def floating_panel_rows(state,width,height,panel=None):
    rows=[]
    def line(y,text,attr=0):
        if 0<=y<height:rows.append((y,str(text)[:max(0,width)],attr))
    packets=packet_rows(state)
    packet=selected_row(state)
    selected=packet
    panels=trial_panels(state)
    panel=panel or (panels.focus if panels.focus!='map' else next((name for name in panels.names if name in panels.visible),None))
    if panel=='packets':
        line(0,'PACKETS  /  '+('FOCUSED' if panels.focus==panel else 'Tab to focus'),ink(72))
        line(1,'TIME      CALL       POSITION / TYPE',ink(1))
        visible=max(1,height-4)
        cursor=next((i for i,(index,row) in enumerate(packets) if index==state.selected),0)
        start=max(0,cursor-visible+1)
        if state.selection_expired:line(2,'Selection left retained history',ink(1))
        if not packets:line(3,'No matching packets',ink(1))
        for y,(i,packet) in enumerate(packets[start:start+visible],3):
            text='%s %-10.10s %s'%(packet['time'],packet['call'],summary(packet['payload'],packet.get('decoded')))
            line(y,text.ljust(width),selected_attr(state) if packet is selected else ink(72))
    elif panel=='inspector':
        line(0,'INSPECTOR  /  '+('FOCUSED' if panels.focus==panel else 'Tab to focus'),ink(72))
        if packet is None:
            target=external_target(state)
            if target:
                line(2,target['call']+' / external target',ink(72))
                line(3,'No retained packet selected',ink(1))
            else:line(2,'Selection left retained history' if state.selection_expired else 'No matching packet selected',ink(1))
        else:
            if state.debug_key!=packet['raw']:
                state.debug_record=raw_record(packet,state.socket_path,getattr(state,'snapshot_socket',None))
                state.debug_key=packet['raw'];state.debug_scroll=0
            identity=packet_identity(packet,state.debug_record)
            if identity['capture_id'] and state.debug_record:
                packet['capture_id']=identity['capture_id'];packet['capture_time']=state.debug_record['time']
            line(1,'Capture '+identity['capture_id'][:12] if identity['capture_id'] else 'Legacy text / original capture unavailable',ink(1))
            lines=inspector_lines(packet,state.debug_record,max(8,width))
            for y,text in enumerate(lines[state.debug_scroll:state.debug_scroll+max(1,height-4)],2):
                line(y,text,ink(72))
    hint='[] scroll | Enter map' if panel=='inspector' else 'Up/Down select | Enter map'
    line(height-1,hint,ink(1))
    return rows


def draw_next(win,state,span):
    h,w=win.getmaxyx();width=w-1;height=h
    if width<30 or height<12:
        begin_frame(win,state)
        put(win,0,0,'Use at least 32 columns x 12 rows.',w,ink(1))
        return
    begin_frame(win,state,(0,0,width,height))
    span=fitted_span(state,width,height,span)
    engine=state.map_engine;viewport=state.map_next.Viewport(state.center,span,width,height)
    engine.prepare(viewport,terrain=state.terrain,roads=state.roads)
    marks=map_overlays(state,span,width,height,viewport)
    overlays=rgb_overlays(state,marks,backplate=label_backplate(state)) if engine.style=='rgb' else marks
    panels=trial_panels(state)
    rects=state.panel_module.layout(width,height,panels.visible)
    def compose_panel(rect,rows,opacity=None,padding=1):
        theme=getattr(state,'tui_theme',None)
        if opacity is None:opacity=getattr(theme,'PANEL_OPACITY',.65)
        px,py,panel_width,panel_height=rect
        if engine.style=='rgb':shade=engine.panel(rect,tint=getattr(theme,'PANEL_TINT',(14,21,18)),opacity=opacity)
        else:shade={(x,y):(' ',ink(1)) for y in range(py,py+panel_height) for x in range(px,px+panel_width)}
        overlays.update(shade)
        text_cells={}
        for y,text,attr in rows:
            for offset,char in enumerate(text[:max(0,panel_width-2*padding)]):
                key=(px+padding+offset,py+padding+y)
                if key in shade:text_cells[key]=(char,attr)
        if engine.style=='rgb':
            for key,cell in rgb_overlays(state,text_cells).items():
                overlays[key]=cell if len(cell)>2 else cell+(shade[key][2],)
        else:overlays.update(text_cells)
    for panel in panels.names:
        if panel in rects:
            rect=rects[panel]
            compose_panel(rect,floating_panel_rows(state,rect[2]-2,rect[3]-2,panel))
    status=friendly_status(state.status).split('|',1)[0].strip()
    read_time=datetime.datetime.fromisoformat(state.transport_read_time).strftime('%H:%M:%S') if state.transport_read_time else '--'
    top=[(0,'RADIO CONSOLE / APRS / %.0f km / focus: %s'%(span,panels.focus.upper()),ink(72)),
         (1,'%s | READ ONLY | filter:%s | %d/%d retained | read:%s'%(status,state.call_filter or 'ALL',len(packet_rows(state)),len(state.packets),read_time),ink(72))]
    hints='Up/Down select' if panels.focus!='map' else 'Arrows pan'
    bottom=[(0,selection_caption(state),ink(1)),
            (1,hints+' | p/x windows Tab focus | c call a all | F follow/resume/stop | +/- zoom f fit | ? help',ink(72))]
    compose_panel(rects['top'],top,opacity=.72,padding=0)
    theme=getattr(state,'tui_theme',None)
    if engine.style=='rgb' and theme is not None and 'CONNECTED' in status:
        for x in range(min(width,len(status))):
            char,_,bg=overlays[x,1];overlays[x,1]=(char,theme.LIVE,bg)
    compose_panel(rects['bottom'],bottom,opacity=.72,padding=0)
    if engine.style=='rgb':state.pending_map=(overlays,0,0)
    else:engine.draw(overlays,x0=0,y0=0,win=win)


def draw_next_help(win,state):
    begin_frame(win,state)
    lines=['RADIO CONSOLE / APRS / CONTROLS','',
           'p   Show/hide packet panel', 'x   Show/hide inspector for selected packet',
           'v   Map alone; p and x toggle independently', 'c   Filter workspace to selected station; a clears; Backspace undoes', 'z   Focus the selected packet on the map', 'Enter   Toggle map/panel focus; Tab cycles map and visible panels',
           'F   Follow selected callsign; resume paused camera; again stops', 'Manual pan pauses follow; trail contains received positions only', 'Map focused: arrows pan', 'Panel focused: Up/Down select; Left/Right focus the other visible panel',
           'j / k   Older / newer packet', '[ / ]   Scroll inspector',
           '+ / -   Zoom in / out', 'f / 0   Fit stations and landmarks',
           't   Terrain on/off', 'r   Roads on/off',
           'b   Heard directory', 'm   Messages', 'g   Nets',
           '?   Close help', 'q   Close viewer; feed keeps running','',
           'Panels tint the single map beneath them; no second geography render.',
           'LEGACY remains the default renderer. This is the opt-in NEXT trial.']
    h,w=win.getmaxyx()
    for y,text in enumerate(lines[:h-1]):put(win,y,1,text,w-2,ink(72) if y==0 else ink(1))


def draw(win,state,span):
    if getattr(state,'map_engine_name','legacy')=='next':
        return draw_next_help(win,state) if state.help else draw_next(win,state,span)
    h,w=win.getmaxyx()
    split=max(29,int(w*.40));bottom=h-7;x0=split+2
    map_rect=(x0,6,w-x0-2,max(1,bottom-7)) if h>=16 and w>=64 and not getattr(state,'debug',False) and not state.help else None
    begin_frame(win,state,map_rect)
    put(win,0,0,' APRS / FIELD CONSOLE '+(' / NEXT MAP TRIAL' if getattr(state,'map_engine_name','legacy')=='next' else ''),w,ink(1)|curses.A_REVERSE|curses.A_BOLD)
    put(win,1,1,friendly_status(state.status),w-2,(ink(4) if 'CONNECTED' in friendly_status(state.status) else ink(3))|curses.A_BOLD)
    last=state.packets[0]['time'] if state.packets else '--:--:--'
    put(win,2,1,'%d packets  /  %d stations  /  last packet %s' % (state.total,len(state.stations),last)+('  |  TERRAIN ON' if state.terrain else '  |  TERRAIN OFF')+' (t)',w-2)
    if h<16 or w<64:
        put(win,5,1,'Use at least 64 columns x 16 rows.',w-2);return
    split=max(29,int(w*.40));bottom=h-7
    put(win,4,1,('> PACKETS' if state.focus == 'list' else '  PACKETS'),split-2,ink(1)|curses.A_BOLD)
    put(win,5,1,'TIME     CALL       TYPE / POSITION',split-2,ink(1))
    for y in range(4,bottom):put(win,y,split,'│',1,ink(1))
    rows=list(state.packets);visible=max(1,bottom-6)
    state.selected=min(state.selected,max(0,len(rows)-1));start=max(0,state.selected-visible+1)
    for y,(i,p) in enumerate(list(enumerate(rows))[start:start+visible],6):
        attr=selected_attr(state) if i==state.selected else 0
        put(win,y,1,'%s %-10.10s %s'%(p['time'],p['call'],summary(p['payload'],p.get('decoded'))),split-2,attr)
    x0=split+2;mw=w-x0-2
    span=fitted_span(state,mw,max(1,bottom-7),span)
    if not getattr(state, 'debug', False):put(win,4,x0,('> ' if state.focus == 'detail' else '  ')+('AUTO MAP' if state.auto_fit else 'LOCAL MAP')+(' / %.0f km / N ^' if getattr(state,'map_engine_name','legacy')=='next' else ' / %.0f km / N ↑')%span+(' / TERRAIN' if state.terrain else ' / LAND/WATER')+(' / ROADS' if state.roads else ''),mw,ink(1)|curses.A_BOLD)
    if getattr(state, 'debug', False) and rows:
        put(win,4,x0,('> INSPECTOR' if state.focus == 'detail' else '  INSPECTOR'),mw,ink(1)|curses.A_BOLD)
        packet = rows[state.selected]
        if state.debug_key != packet['raw']:
            state.debug_record = raw_record(packet, state.socket_path, getattr(state,'snapshot_socket',None))
            state.debug_key = packet['raw']
            state.debug_scroll = 0
        lines = inspector_lines(packet, state.debug_record, mw-1)
        for y, line in enumerate(lines[state.debug_scroll:state.debug_scroll+max(1,bottom-7)], 6):
            put(win,y,x0,line,mw,ink(4)|curses.A_BOLD if line in ('DECODED','PAYLOAD','CAPTURE','BYTES  /  HEX + ASCII','FEED TEXT') or y == 6 else 0)
        put(win,bottom-1,x0,'← list  ↑↓ packets  Enter back  [ ] scroll',mw,ink(1))
    else:
        map_panel(win,state,span,x0,6,mw,max(1,bottom-7))
        put(win,bottom-1,x0,selection_caption(state),mw,ink(1))
    put(win,bottom,0,'─'*(w-1),w,ink(1))
    if getattr(state, 'debug', False):
        pass
    elif rows:
        p=rows[state.selected]
        put(win,bottom+1,1,'%s  %s > %s'%(p['time'],p['call'],p['route']),w-2,ink(4)|curses.A_BOLD)
        text=p['payload']
        for n in range(2):put(win,bottom+2+n,1,text[n*(w-3):(n+1)*(w-3)],w-2)
    else:put(win,bottom+1,1,'Waiting for packets. Offline geography is ready to browse.',w-2)
    put(win,h-2,1,'' if getattr(state,'debug',False) else 'Map: OSM / Natural Earth / USGS / NOAA | ? help',w-2,ink(1))
    hints='Up/Down packets  Right map  Enter back  v full map  x inspect  t terrain  r roads  f fit' if getattr(state,'map_engine_name','legacy')=='next' else '↑↓ packets  → panel  Enter back/view  x inspect  F follow/resume/stop  t terrain  r roads  f fit  ? help'
    put(win,h-1,1,hints,w-2,ink(1))
    if state.help:
        erase_view(win,state)
        lines=['APRS / FIELD CONSOLE','', 'Path * marks a used digipeater; other entries are requested routing.', 'Radio-to-host captures may include local transmit echoes.', '', 'j / k         Select older / newer packet',
               'r             Toggle major roads (visible at 60 km or closer)', 't             Toggle elevation / flat land-water', 'x             Toggle packet inspector (hex + ASCII)', '[ / ]         Scroll packet inspector', 'Up / Down     Select packets in list or inspector', 'Left / Right  Focus list / inspector', 'Tab           Switch list / right panel focus', 'Map focused   Arrows pan; center/Enter returns to list', 'List focused  Center/Enter switches map / inspector','+ / -         Zoom in / out',
               'f / 0         Fit stations, reference and nearby landmarks','?             Close this help','g             Open Nets / local schedule agenda','m             Open the Messages tmux window', 'b             Open the offline heard directory', 'q             Quit viewer (feed keeps running)',
               '', '* station    + fixed Lakewood reference (not GPS)',
               'Elevation: six muted bands from dark green to pale gray.', 'Blue water. Elevation colors do not show vegetation or snow cover.',
               'Uncompressed and Mic-E positions are mapped; ambiguous Mic-E is approximate.', 'Packet distances/directions are from the fixed Lakewood reference.', '', 'OFFLINE MAP PACKS']
        if getattr(state,'map_engine_name','legacy')=='next':
            lines.insert(2,'p packets / x inspector / v map alone / Enter panel-map focus')
        lines += [p['name'] for p in state.atlas.packs] or ['No map packs installed']
        lines += state.atlas.errors
        lines += ['', '(c) OpenStreetMap contributors. Map data under ODbL.', 'https://www.openstreetmap.org/copyright',
                  'Packs load from: '+state.map_dir]
        for y,line in enumerate(lines[:h-1]):put(win,y,1,line,w-2,ink(1) if y==0 else 0)


def draw_map(win,state,span):
    h,w=win.getmaxyx()
    begin_frame(win,state,(1,3,w-3,max(1,h-6)))
    span=fitted_span(state,w-3,max(1,h-6),span)
    put(win,0,0,('APRS MAP / %.0f km / N ^' if getattr(state,'map_engine_name','legacy')=='next' else 'APRS MAP / %.0f km / N ↑')%span,w,ink(1)|curses.A_BOLD)
    put(win,1,0,friendly_status(state.status),w)
    map_panel(win,state,span,1,3,w-3,max(1,h-6))
    put(win,h-2,0,'(c) OpenStreetMap contributors / ODbL',w,ink(1))
    hints='Arrows pan  +/- zoom  f fit  v/Enter packets  j/k select  t terrain  r roads  q quit' if getattr(state,'map_engine_name','legacy')=='next' else 'Arrows pan  +/- zoom  0 reset  q quit'
    put(win,h-1,0,hints,w,ink(1))


def run(win, args):
    curses.curs_set(0)
    win.timeout(100)
    win.keypad(True)
    map_style.init_screen(win)
    state = State()
    state.map_dir = args.maps
    put(win,0,0,'APRS / Loading offline geography...',win.getmaxyx()[1])
    win.refresh()
    init_map(state,args.maps,args.map_engine,getattr(args,'tui_theme','current'))
    state.center = [47.38,-122.52]
    state.selected = 0
    state.debug = False
    state.focus = 'list'
    state.debug_key = None
    state.debug_record = None
    state.debug_scroll = 0
    state.map_target = None
    request_check = 0
    request_id = None
    state.socket_path = args.socket or "/dev/shm/n810-aprs.sock"
    state.snapshot_socket=getattr(args,'snapshot_socket',None)
    state.roads = False
    state.help = False
    state.auto_fit = True
    if not args.history:
        try:
            with open(os.path.expanduser('~/.local/state/n810-aprs/last-packets.json')) as f:
                saved_packets=json.load(f).get('packets',[])
            for line in saved_packets[-200:]:
                if isinstance(line,str):state.add(line,historical=True)
        except (OSError,ValueError,AttributeError):pass
    if args.history and os.path.exists(args.history):
        with open(args.history) as f:
            for line in collections.deque(f, maxlen=200):
                try:
                    row = json.loads(line)
                    state.add(row['raw'], historical=True)
                except (ValueError, KeyError):
                    pass
    state.status = "Connecting | history in RAM | disk logging OFF" if not args.log else "Connecting | explicit disk logging ON"
    view_state_key='map-next' if args.map_engine=='next' else 'map'
    saved=ui_state.load(view_state_key)
    span = max(10,min(48000,float(saved.get('span',160))))
    if isinstance(saved.get('center'),list) and len(saved['center'])==2:
        state.center=[max(-80,min(80,float(saved['center'][0]))),max(-180,min(180,float(saved['center'][1])))]
    for field in ('terrain','roads','auto_fit','debug'):
        if isinstance(saved.get(field),bool):setattr(state,field,saved[field])
    state.focus=saved.get('focus','list') if saved.get('focus') in ('list','detail') else 'list'
    state.debug_scroll=max(0,int(saved.get('debug_scroll',0)))
    request_id=saved.get('request_id')
    restore_raw=saved.get('selected_raw')
    state.map_target=saved.get('map_target')
    if args.map_engine=='next':
        panels=trial_panels(state)
        panels.visible=set(saved.get('panels',[]))&set(panels.names) if isinstance(saved.get('panels',[]),list) else set()
        panels.focus=saved.get('panel_focus','map') if saved.get('panel_focus') in panels.visible else 'map'
        call=saved.get('call_filter')
        state.call_filter=call if isinstance(call,str) and re.fullmatch(r'[A-Z0-9-]{1,16}',call) else None
        state.focus='detail' if panels.focus=='map' else 'list'
        state.selection_expired=saved.get('selection_expired') is True
        state.follow_latest=not (restore_raw or state.call_filter or 'inspector' in panels.visible or state.selection_expired)
        if state.map_target:activate_external_target(state,state.map_target,remember=False)
    def save_view():
        rows=list(state.packets)
        selected=(selected_row(state) or {}) if args.map_engine=='next' else (rows[min(state.selected,len(rows)-1)] if rows else {})
        workspace={}
        if args.map_engine=='next':
            panels=trial_panels(state)
            workspace=dict(panels=sorted(panels.visible),panel_focus=panels.focus,call_filter=state.call_filter,selection_expired=state.selection_expired)
        ui_state.save(view_state_key,dict(**workspace,center=state.center,span=span,terrain=state.terrain,
            roads=state.roads,auto_fit=state.auto_fit,debug=state.debug,focus=state.focus,
            debug_scroll=state.debug_scroll,selected_raw=selected.get('raw'),
            request_id=request_id,map_target=state.map_target))
    child = None
    connection = None
    selector = selectors.DefaultSelector()
    if not args.socket:
        child = subprocess.Popen([sys.executable, '-u', args.receiver], stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        selector.register(child.stdout, selectors.EVENT_READ)
        os.set_blocking(child.stdout.fileno(), False)
    retry_at = 0.0
    replay = collections.Counter()
    pending = b''
    dirty = True
    last_size = None
    try:
        with (open(args.log, 'a', buffering=1) if args.log else contextlib.nullcontext(None)) as log:
            while True:
                if time.monotonic() >= request_check:
                    request_check=time.monotonic()+.5
                    try:
                        request=runtime.read_json('n810-map-request.json')
                        if request.get('id') != request_id:
                            request_id=request['id'];call=request['call']
                            if args.map_engine=='next':activate_external_target(state,request)
                            else:
                                matches=[i for i,p in enumerate(state.packets) if p['call']==call]
                                state.map_target=None
                                if matches:state.selected=matches[0];state.selection_expired=False
                                else:
                                    state.map_target=request
                                    if 'position' in request:
                                        lat,lon=request['position']
                                        state.stations[call]=dict(call=call,lat=lat,lon=lon)
                                state.map_target=request
                                state.debug=False;state.focus='list'
                            h,w=win.getmaxyx()
                            span=include_selection(state,span,*map_dimensions(state,w,h))
                            dirty=True
                    except (OSError,ValueError,KeyError,TypeError):pass
                if args.socket and connection is None and time.monotonic() >= retry_at:
                    candidate = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    candidate.settimeout(0.2)
                    try:
                        candidate.connect(args.socket)
                    except OSError:
                        candidate.close()
                        state.status = 'Feed unavailable - waiting to reconnect'
                        retry_at = time.monotonic() + 2
                    else:
                        connection = candidate
                        connection.setblocking(False)
                        selector.register(connection, selectors.EVENT_READ)
                        pending = b''
                        replay = collections.Counter(p['raw'] for p in state.packets)
                        state.status = 'Connected to RAM feed - waiting for status'
                    dirty = True
                for key, _ in selector.select(0):
                    try:
                        chunk = os.read(key.fileobj.fileno(), 8192)
                    except BlockingIOError:
                        continue
                    except OSError:
                        chunk = b''
                    if not chunk:
                        selector.unregister(key.fileobj)
                        if args.socket:
                            key.fileobj.close()
                            connection = None
                            pending = b''
                            retry_at = time.monotonic() + 2
                            state.status = 'Feed disconnected - waiting to reconnect'
                        else:
                            state.status = 'Receiver stopped - q quits'
                        dirty = True
                        continue
                    dirty = True
                    state.transport_read_time=datetime.datetime.now().astimezone().isoformat()
                    pending += chunk
                    while b'\n' in pending:
                        line, pending = pending.split(b'\n', 1)
                        line = line.decode('utf-8', 'replace')
                        # The feed replays its packet ring before its current status.
                        # Consume matching old records only during that replay.
                        if not LINE.match(line):
                            replay.clear()
                        elif replay[line]:
                            replay[line] -= 1
                            continue
                        row = state.add(line)
                        if row and log is not None:
                            row['raw'] = line
                            log.write(json.dumps(row)+'\n')
                if restore_raw:
                    matches=[i for i,p in enumerate(state.packets) if p['raw']==restore_raw]
                    if matches:state.selected=matches[0];restore_raw=None;dirty=True
                if not visibility.visible():
                    dirty=True
                    state.canvas_signature=None
                queued_key=None
                if state.map_engine_name=='next':
                    win.timeout(0)
                    try:queued_key=win.getch()
                    finally:win.timeout(100)
                if visibility.visible() and queued_key in (None,-1) and (dirty or win.getmaxyx() != last_size):
                    apply_station_follow(state)
                    (draw_map if args.map_only else draw)(win, state, span)
                    finish_frame(win,state)
                    dirty = False
                    last_size = win.getmaxyx()
                key=queued_key if queued_key not in (None,-1) else win.getch()
                if key==ord('g'):
                    spec=importlib.util.spec_from_file_location('ui_window',os.path.join(os.path.dirname(__file__),'n810-ui-window.py'))
                    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
                    try:helper.open_window('Nets')
                    except (OSError,RuntimeError) as exc:state.status=str(exc)
                    continue
                if key in (ord('q'), 27):
                    break
                if key==ord('F'):
                    toggle_station_follow(state);dirty=True;continue
                if trial_panel_key(state,key):
                    dirty=True
                    continue
                if key in (ord('+'), ord('=')):
                    state.auto_fit = False
                    span = max(10, span/1.5)
                    dirty = True
                elif key == ord('r'):
                    state.roads = not state.roads
                    dirty = True
                elif key == ord('t'):
                    state.terrain = not state.terrain
                    dirty = True
                elif key == ord('x'):
                    state.debug = not state.debug
                    state.debug_key = None
                    dirty = True
                elif key in (ord('['), ord(']')):
                    state.debug_scroll = max(0, min(8500, state.debug_scroll + (5 if key == ord(']') else -5)))
                    dirty = True
                elif key in (ord('m'),ord('b')):
                    try:
                        spec=importlib.util.spec_from_file_location('ui_window',os.path.join(os.path.dirname(__file__),'n810-ui-window.py'))
                        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                        save_view()
                        if key == ord('b'):
                            call=state.map_target['call'] if state.map_target else (list(state.packets)[state.selected]['call'] if state.packets else None)
                            if call:
                                runtime.write_json('n810-directory-request.json',dict(call=call,id=time.time_ns()))
                        module.open_window('Directory' if key == ord('b') else 'Messages')
                    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
                        state.status='Could not open window: '+str(exc)
                    dirty = True
                elif key == ord('?'):
                    state.help = not state.help
                    dirty = True
                elif key in (ord('j'),ord('k')):
                    if args.map_engine!='next':state.map_target=None
                    move_selection(state,1 if key==ord('j') else -1)
                    h,w=win.getmaxyx();span=include_selection(state,span,*map_dimensions(state,w,h))
                    dirty = True
                elif key in (ord('0'),ord('f')):
                    state.tracks.pause()
                    state.auto_fit = True
                    state.center = [47.38,-122.52]
                    span = 160.0
                    dirty = True
                elif key in (10, 13, curses.KEY_ENTER):
                    if state.focus == 'detail':
                        state.focus = 'list'
                    else:
                        state.debug = not state.debug
                        state.debug_key = None
                    dirty = True
                elif key == 9:
                    state.focus = 'detail' if state.focus == 'list' else 'list'
                    dirty = True
                elif key in (curses.KEY_LEFT,curses.KEY_RIGHT,curses.KEY_UP,curses.KEY_DOWN) and (state.debug or state.focus == 'list') and (state.map_engine_name!='next' or trial_panels(state).focus!='map'):
                    if key in (curses.KEY_UP, curses.KEY_DOWN):
                        if args.map_engine!='next':state.map_target=None
                        move_selection(state,1 if key==curses.KEY_DOWN else -1)
                        h,w=win.getmaxyx();span=include_selection(state,span,*map_dimensions(state,w,h))
                    elif key == curses.KEY_LEFT:
                        state.focus = 'list'
                    else:
                        state.focus = 'detail'
                    dirty = True
                elif key in (curses.KEY_LEFT,curses.KEY_RIGHT,curses.KEY_UP,curses.KEY_DOWN):
                    state.auto_fit = False
                    state.tracks.pause()
                    if key in (curses.KEY_LEFT,curses.KEY_RIGHT):
                        state.center[1] += (-1 if key==curses.KEY_LEFT else 1)*span*.18/(111.32*math.cos(math.radians(state.center[0])))
                        state.center[1] = max(-180,min(180,state.center[1]))
                    else:
                        state.center[0] += (1 if key==curses.KEY_UP else -1)*span*.12/111.32
                        state.center[0] = max(-80,min(80,state.center[0]))
                    dirty = True
                elif key == ord('-'):
                    state.auto_fit = False

                    span = min(2000, span*1.5)
                    dirty = True
    finally:
        try:save_view()
        except OSError:pass
        selector.close()
        if connection is not None:
            connection.close()
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--socket', help='Subscribe to an existing RAM feed, without owning the receiver')
    p.add_argument('--snapshot-socket', help='Explicit read-only raw snapshot endpoint for the inspector')
    p.add_argument('--maps', default=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'maps'), help='Directory of offline *.json.gz map packs')
    p.add_argument('--map-engine',choices=('legacy','next'),default='legacy',help='Opt in to the experimental map engine; legacy remains the default')
    p.add_argument('--tui-theme',choices=('current','restrained','color'),default='current',help='Opt-in APRS map colors for the next renderer')
    p.add_argument('--map-only', action='store_true', help='Compact map for a side pane')
    p.add_argument('--receiver', default='/home/nokia/uvpro-aprs-listen.py')
    p.add_argument('--history', help='Read an existing JSONL capture into RAM')
    p.add_argument('--log', help='Explicitly enable append-only JSONL disk recording')
    args = p.parse_args()
    curses.wrapper(run, args)
