"""Adapt cached decoded RX evidence/catalog, independent of RadioFeed selection or pause."""
import hashlib,re
from last_heard_model import Peer,Position,Observation,Snapshot
RX=re.compile(r'^([A-Z0-9]{1,6}(?:-[0-9]{1,2})?)>(\S+) ctl=(?:03|13) pid=f0 ')
def position(value):
    if not isinstance(value,dict):return None
    try:return Position(value['lat'],value['lon'],value.get('stamp'))
    except (KeyError,TypeError,ValueError):return None

def adapt(receive,station_catalog=None,selected_detail=None,reference=None,network='local-aprs'):
    """Caller supplies cached Catalog.feed_view() evidence, not Feed form state.

    Snapshot order is retained source order, not sorting by packet timestamps.
    This adapter intentionally excludes unidentifiable/non-AX.25 UI records.
    """
    catalog={r['call']:r for r in (station_catalog or {}).get('rows',()) if isinstance(r,dict) and isinstance(r.get('call'),str)}
    def observation(call,row,route=()):
        item=catalog.get(call,{})
        return Observation(hashlib.sha256((str(row.get('time'))+'\0'+str(row.get('frame'))+'\0'+str(row.get('raw'))).encode()).hexdigest(),Peer('aprs',network,call),item.get('name') or call,row.get('time'),position(item.get('position')),tuple(item.get('categories') or ())[:8],tuple(hop[:-1] for hop in route if hop.endswith('*'))[:8],'Reported used addresses; physical route unverified',str(row.get('raw') or '')[:512])
    observations=[]
    for row in tuple(receive.get('evidence') or ())[-200:]:
        if not isinstance(row,dict) or row.get('direction')!='radio_to_host':continue
        match=RX.match(str(row.get('raw') or ''))
        if match:observations.append(observation(match[1],row,match[2].split(',')[1:]))
    selected=None
    if selected_detail and isinstance(selected_detail.get('call'),str):
        call=selected_detail['call'];selected=next((r for r in reversed(observations) if r.peer.address==call),None)
        if selected is None:
            selected=Observation('directory:'+call,Peer('aprs',network,call),call,None,position(selected_detail.get('position')),path_kind='No retained reception selected')
    return Snapshot(tuple(observations),selected,reference,receive.get('source') or 'Receive source unavailable',receive.get('connection') or 'Unknown','Retained RX snapshot; replay/reconnect is not new RF evidence')
