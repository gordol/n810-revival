"""Bounded read-only projections of the existing Directory SQLite model."""
from contextlib import closing
import functools
import importlib.util
import json
import math
from pathlib import Path
import sqlite3


@functools.lru_cache(maxsize=1)
def directory():
    spec=importlib.util.spec_from_file_location('directory_projection_source',Path(__file__).with_name('n810-directory-model.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def connect(db):
    connection=sqlite3.connect(Path(db).expanduser().resolve().as_uri()+'?mode=ro',uri=True,timeout=.2)
    connection.row_factory=sqlite3.Row
    connection.execute('PRAGMA query_only=ON');connection.execute('BEGIN')
    return connection


def bounded(value,default,maximum):
    value=default if value is None else value
    if type(value)!=int or not 0<=value<=maximum:raise ValueError('Invalid projection bound')
    return value


def list_stations(db,filters=None,*,self_calls=None,own_call='N0ANT'):
    """db is a path. Filters: limit, offset, buddy_only, via."""
    identities=directory().self_call_snapshot(self_calls,own_call)
    filters=dict(filters or {})
    if set(filters)-{'limit','offset','buddy_only','via'}:raise ValueError('Unknown station filter')
    limit=bounded(filters.get('limit'),200,500);offset=bounded(filters.get('offset'),0,1000000)
    for key in ('buddy_only',):
        if key in filters and type(filters[key])!=bool:raise ValueError('Expected boolean filter')
    via=filters.get('via')
    if via is not None and not isinstance(via,str):raise ValueError('Expected relay callsign')
    source='stations s';where=[];args=[]
    if via:
        source='via s';where.append('s.relay=?');args.append(via.strip().upper())
    if filters.get('buddy_only'):where.append('coalesce(p.buddy,0)=1')
    sql="SELECT s.call,s.first,s.last,s.packets,coalesce(p.buddy,0) buddy,coalesce(p.name,'') name FROM "+source+" LEFT JOIN people p ON p.call=CASE WHEN instr(s.call,'-')>0 THEN substr(s.call,1,instr(s.call,'-')-1) ELSE s.call END"
    if where:sql+=' WHERE '+' AND '.join(where)
    sql+=" ORDER BY (substr(s.last,1,7)='legacy '),s.last DESC,s.call LIMIT ? OFFSET ?"
    with closing(connect(db)) as connection:
        records=connection.execute(sql,[*args,limit+1,offset]).fetchall()
        counts=directory().station_counts(connection,self_calls=identities)
        rows=[dict(row,is_self=row['call'] in identities,base_call=row['call'].split('-')[0],buddy=bool(row['buddy'])) for row in records[:limit]]
    return dict(rows=rows,limit=limit,offset=offset,has_more=len(records)>limit,counts=counts,self_calls=identities)


def station_details(db,call,*,relay_limit=50,width=72,self_calls=None,own_call='N0ANT'):
    """Return None for an unknown station; evidence and relays are aggregate."""
    identities=directory().self_call_snapshot(self_calls,own_call)
    if not isinstance(call,str) or not call.strip():raise ValueError('Expected station callsign')
    call=call.strip().upper();base=call.split('-')[0]
    relay_limit=bounded(relay_limit,50,200);width=bounded(width,72,240)
    if width<20:raise ValueError('Detail width must be at least 20')
    with closing(connect(db)) as connection:
        row=connection.execute('SELECT * FROM stations WHERE call=?',(call,)).fetchone()
        if row is None:return None
        person=connection.execute('SELECT buddy,name,notes FROM people WHERE call=?',(base,)).fetchone()
        buddy,name,notes=tuple(person) if person else (0,'','')
        evidence=directory().station_evidence(connection,call)
        sources={r['kind']:'legacy_text' for r in connection.execute('SELECT kind FROM legacy_evidence WHERE call=?',(call,))}
        sources.update({r['kind']:'capture' for r in connection.execute('SELECT kind FROM evidence WHERE call=?',(call,))})
        relays=connection.execute('SELECT relay,first,last,packets FROM via WHERE call=? ORDER BY packets DESC,relay LIMIT ?',(call,relay_limit+1)).fetchall()
        result=dict(row,is_self=call in identities,base_call=base,buddy=bool(buddy),name=name,notes=notes,
                    evidence=[dict(kind=k,stamp=t,detail=d,source=sources.get(k,'aggregate' if k in ('relay_activity','forwarded') else 'legacy_text')) for k,t,d in evidence],
                    heard_through=[dict(r) for r in relays[:relay_limit]],relays_truncated=len(relays)>relay_limit,
                    position=None,symbol=None,capture_ref=None,route=None)
        for item in result['evidence']:
            if item['kind']=='position':
                result['position']=_map_position(item)
            elif item['kind']=='symbol':result['symbol']=_map_symbol(item)
        hops=[(r['relay'],r['packets'],r['last']) for r in relays[:relay_limit]]
        try:result['lines']=directory().station_details(call,name,bool(buddy),row['last'],row['packets'],evidence,hops,notes,width)
        except (ValueError,TypeError,KeyError):result['lines']=[call,'Malformed advertised detail; inspect original evidence.']
        return result


def navigation_target(detail):
    """Station-focus payload; caller adds a navigation action token if needed."""
    if not detail or not isinstance(detail.get('call'),str):raise ValueError('Station detail required')
    target=dict(call=detail['call'],source='directory')
    position=detail.get('position')
    if position:
        target.update(position=[position['lat'],position['lon']],position_time=position['stamp'])
    return target


def _map_position(item):
    try:
        lat,lon=json.loads(item['detail'])
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (lat,lon)) or not (-90<=lat<=90 and -180<=lon<=180):return None
        return dict(lat=lat,lon=lon,stamp=item['stamp'],source=item['source'])
    except (ValueError,TypeError):return None


def _map_symbol(item):
    try:
        value=json.loads(item['detail'])
        if not isinstance(value,dict):return None
        symbol=directory().symbol_value(value.get('table'),value.get('code'))
        return dict(symbol,stamp=item['stamp'],source=item['source']) if symbol else None
    except (ValueError,TypeError):return None


def _station_batch(connection,limit,offset,identities):
    records=connection.execute("SELECT s.*,coalesce(p.buddy,0) buddy,coalesce(p.name,'') name FROM stations s LEFT JOIN people p ON p.call=CASE WHEN instr(s.call,'-')>0 THEN substr(s.call,1,instr(s.call,'-')-1) ELSE s.call END ORDER BY (substr(s.last,1,7)='legacy '),s.last DESC,s.call LIMIT ? OFFSET ?",(limit+1,offset)).fetchall()
    rows=[dict(r,is_self=r['call'] in identities,base_call=r['call'].split('-')[0],buddy=bool(r['buddy']),position=None,symbol=None,categories=[],category_evidence=[]) for r in records[:limit]]
    by_call={row['call']:row for row in rows}
    if rows:
        placeholders=','.join('?' for _ in rows);calls=list(by_call)
        facts={call:{} for call in calls}
        tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table,source in [('legacy_evidence','legacy_text'),('evidence','capture')]:
            if table not in tables:continue
            for r in connection.execute('SELECT call,kind,stamp,detail FROM '+table+' WHERE call IN ('+placeholders+')',calls):
                facts[r['call']][r['kind']]=dict(kind=r['kind'],stamp=r['stamp'],detail=r['detail'],source=source)
        roles={'APRS digipeater / routing advertised','APRS digipeater / advertised symbol'}
        for call,items in facts.items():
            row=by_call[call]
            if 'position' in items:row['position']=_map_position(items['position'])
            if 'symbol' in items:row['symbol']=_map_symbol(items['symbol'])
            for kind,item in sorted(items.items()):
                tag='digipeater_advertised' if kind=='role' and item['detail'] in roles else 'voice_advertised' if kind=='voice' else kind if kind.startswith('service:') else None
                if tag:
                    row['categories'].append(tag);row['category_evidence'].append(dict(item,category=tag))
        for r in connection.execute('SELECT relay,count(DISTINCT call) station_count,max(last) last FROM via WHERE relay IN ('+placeholders+') GROUP BY relay',calls):
            row=by_call[r['relay']];row['categories'].append('relay_observed')
            row['category_evidence'].append(dict(category='relay_observed',kind='relay_activity',stamp=r['last'],source='aggregate',detail=str(r['station_count'])))
    return dict(rows=rows,limit=limit,offset=offset,has_more=len(records)>limit,counts=directory().station_counts(connection,self_calls=identities),self_calls=identities)


def _batch_revision(result):
    import hashlib
    revision=hashlib.sha256(json.dumps(result,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
    return dict(result,revision=revision)


def map_stations(db,*,limit=500,offset=0,self_calls=None,own_call='N0ANT'):
    """One bounded, consistent read snapshot; unknown position/symbol stays null."""
    identities=directory().self_call_snapshot(self_calls,own_call)
    limit=bounded(limit,500,500);offset=bounded(offset,0,1000000)
    with closing(connect(db)) as connection:return _batch_revision(_station_batch(connection,limit,offset,identities))


class StationMapCache:
    """Requery on SQLite or explicit identity changes; revision reflects content."""
    def __init__(self,db,*,limit=500,offset=0,self_calls=None,own_call='N0ANT'):
        self.self_calls=directory().self_call_snapshot(self_calls,own_call)
        self.path=Path(db).expanduser().resolve();self.limit=bounded(limit,500,500);self.offset=bounded(offset,0,1000000)
        self.connection=None;self.file_id=None;self.version=None;self.value=None
    def close(self):
        if self.connection:self.connection.close()
        self.connection=None;self.file_id=None;self.version=None;self.value=None
    def set_self_calls(self,values):
        identities=directory().self_call_snapshot(values)
        if identities!=self.self_calls:
            self.self_calls=identities;self.version=None
    def snapshot(self):
        try:
            info=self.path.stat();file_id=(info.st_dev,info.st_ino)
            if self.connection is None or file_id!=self.file_id:
                self.close();self.connection=sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True,timeout=.2)
                self.connection.row_factory=sqlite3.Row;self.connection.execute('PRAGMA query_only=ON');self.file_id=file_id
            version=self.connection.execute('PRAGMA data_version').fetchone()[0]
            if self.value is not None and version==self.version:return self.value
            self.connection.execute('BEGIN')
            try:result=_batch_revision(_station_batch(self.connection,self.limit,self.offset,self.self_calls))
            finally:self.connection.rollback()
            if self.value is None or result['revision']!=self.value['revision']:self.value=result
            self.version=version;return self.value
        except (OSError,sqlite3.Error):
            self.close();raise
