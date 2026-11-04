"""Native station selection shared by the directory, details and existing map worker."""
import importlib.util
import math
import datetime
import re
from pathlib import Path
import time
import sqlite3
import textwrap
from console_icons import aprs_display, profile_from_environment
from app_widgets import AdaptivePanels,PanelSpec,Canvas,SelectList,Columns,Column,TextInput
from offline_map import Plane,ScaledPlane,raster_size
from map_terrain import Renderer
from paint import ink


def map_spacing(value):
    number,unit=(value/1000,'km') if value>=1000 else (value,'m')
    text=format(number,'.2f' if unit=='km' or number<1 else '.1f').rstrip('0').rstrip('.')
    return text+' '+unit


class Context:
    def __init__(self):
        self.detail=None;self.target=None;self.revision=0
        self.map_catalog=None;self.map_revision=None;self.map_error=None;self.refresh_catalog=None;self.close_catalog=None;self.select_station=None
    def select(self,detail,target):
        if detail!=self.detail or target!=self.target:
            self.detail=detail;self.target=target;self.revision+=1

    def catalog(self,snapshot,error=None):
        self.map_catalog=snapshot;self.map_error=error
        self.map_revision=snapshot['revision'] if snapshot is not None else ('unavailable',error)


class Directory:
    def __init__(self,db,sources,context,*,self_calls=None):
        self.db=Path(db).expanduser();self.context=context;self.rows=();self.signature=None;self.error=None;self.next_check=0
        spec=importlib.util.spec_from_file_location('pocket_directory_projection',Path(sources)/'n810-directory-projection.py')
        self.model=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.model)
        self.map_cache=self.model.StationMapCache(self.db,self_calls=self_calls)
        self.self_calls=self.map_cache.self_calls;self.counts={}
        context.refresh_catalog=self.update;context.close_catalog=self.close;context.select_station=self.select
    def close(self):self.map_cache.close()
    def set_self_calls(self,values):
        self.map_cache.set_self_calls(values);self.self_calls=self.map_cache.self_calls
        self.signature=None;self.next_check=0;self.update(True)
    def update(self,force=False):
        now=time.monotonic()
        if not force and now<self.next_check:return False
        self.next_check=now+1
        try:
            snapshot=self.map_cache.snapshot();map_changed=snapshot is not self.context.map_catalog
            self.context.catalog(snapshot)
            files=(self.db,Path(str(self.db)+'-wal'))
            signature=tuple((p.stat().st_mtime_ns,p.stat().st_size) if p.exists() else None for p in files)
            if not force and signature==self.signature and not map_changed:return False
            rows=self.model.list_stations(self.db,self_calls=self.self_calls)
            self.counts=rows['counts']
            self.rows=tuple(rows['rows']);self.has_more=rows['has_more'];self.signature=signature;self.error=None
            call=(self.context.target or {}).get('call')
            if call:self.select(call)
            elif self.rows:self.select(self.rows[0]['call'])
            return True
        except (OSError,ValueError,TypeError,sqlite3.Error) as error:
            self.error=str(error);self.context.catalog(None,self.error);return False
    def select(self,call):
        try:
            detail=self.model.station_details(self.db,call,self_calls=self.self_calls)
            if detail:
                self.context.select(detail,self.model.navigation_target(detail));self.error=None;return True
            else:self.error='Selected station is no longer available'
        except (OSError,ValueError,TypeError,sqlite3.Error) as error:self.error=str(error)


class Stations:
    def help_pages(self):
        from app_help_content import pages
        return pages('Stations')
    def __init__(self,directory,open_map):
        self.directory=directory;self.context=directory.context;self.open_map=open_map
        self.width=74;self.height=24;self.query='';self.scroll=0;self.list=SelectList(());self.calls=();self.hits=[];self._spans=[];self._filter_rows=None;self._filter_query=None;self._filtered=();self._synced=None;self._context_revision=None;self._selected_call=None
        self.layout=AdaptivePanels((PanelSpec('list','Stations',16,25),PanelSpec('details','Station details',28,49)))
        self._detail_length=0
        self.list.column_layout=Columns((Column('Stations',10,'heading'),Column('Name',20,'body')))
        self.self_editor=None;self.self_edit_error='';self.save_self_calls=None
        from native_uls import ULSLookup
        self.license_lookup=ULSLookup();self.open_uls=None
    def navigation_modal_hint(self):return ('Stations','↑↓ browse · U license · Enter map · / filter · Tab pane')
    def bind_wakeup(self,callback):self.license_lookup.bind_wakeup(callback)
    def poll_interval(self):return self.license_lookup.poll_interval()
    def poll(self):return self.license_lookup.poll()
    def close(self):self.license_lookup.close()
    def edit_self_calls(self):
        self.self_editor=TextInput(', '.join(self.directory.self_calls),limit=350)
        self.self_edit_error=''
    @property
    def focus(self):return int(self.layout.focus=='details')
    @focus.setter
    def focus(self,value):self.layout.select('details' if value else 'list')
    def pane_rects(self):
        return {key:(x,y+2,w,h) for key,(x,y,w,h) in self.layout.layout(self.width,max(1,self.height-3)).items()}
    @property
    def pointer_captured(self):return self.layout.pointer_captured
    @property
    def resizing(self):return self.layout.resizing
    def cancel_pointer(self):self.layout.cancel_pointer()
    def bind_session(self,callback):self.layout.bind_session(callback)
    def session_state(self):return dict(panels=self.layout.session_state())
    def restore_session(self,state):
        if isinstance(state,dict):self.layout.restore_session(state.get('panels',{}))
    def matches(self):
        query=self.query.casefold()
        if self.directory.rows is not self._filter_rows or query!=self._filter_query:
            self._filter_rows=self.directory.rows;self._filter_query=query
            self._filtered=self.directory.rows if not query else tuple(row for row in self.directory.rows if query in (row['call']+' '+row.get('name','')).casefold())
        return self._filtered
    def sync(self):
        rows=self.matches();selected=(self.context.target or {}).get('call')
        if rows is not self._synced:
            self._synced=rows;calls=tuple(row['call'] for row in rows);values=tuple((row['call'],row.get('name') or '') for row in rows)
            self.calls=calls;self.list.column_values=values;self.list.replace(tuple(row['call']+(' · '+row['name'] if row.get('name') else '') for row in rows),calls)
            self.list.index=calls.index(selected) if selected in calls else min(self.list.index,max(0,len(calls)-1))
        revision=getattr(self.context,'revision',selected)
        if revision!=self._context_revision:
            self._context_revision=revision
            if selected in self.calls:self.list.index=self.calls.index(selected)
            if selected!=self._selected_call:self.list.reveal()
            self._selected_call=selected
        return rows
    def choose(self):
        self.sync()
        if not self.calls:return False
        call=self.calls[self.list.index]
        return True if (self.context.target or {}).get('call')==call else self.directory.select(call)
    def lookup_selected(self):
        if self.choose() and self.open_uls:self.open_uls(self.calls[self.list.index])
        return True
    def key(self,key):
        if self.self_editor is not None:
            if key=='\x1b':self.self_editor=None
            elif key in ('\r','\n'):
                try:
                    values=tuple(value for value in re.split(r'[,\s]+',self.self_editor.text.strip().upper()) if value)
                    self.directory.set_self_calls(values)
                    if self.save_self_calls is not None:self.save_self_calls(self.directory.self_calls)
                    self.self_editor=None;self.self_edit_error=''
                except ValueError as error:self.self_edit_error=str(error)
            else:self.self_editor.key(key)
            return True
        self.sync()
        if key in ('u','U') and not self.list.searching and not self.query and not self.list.query:return self.lookup_selected()
        if (self.layout.resizing or key=='\x12' and not self.list.searching) and self.layout.split_key(key,self.width):return True
        if not self.focus and self.list.search_key(key):
            self.choose();return True
        if key=='?' and (self.focus or not self.query):return False
        if key in ('\t','backtab'):self.focus=1-self.focus
        elif self.focus and key in ('up','down','j','k','pageup','pagedown','home','end'):
            if key=='home':self.scroll=0
            elif key=='end':self.scroll=self._detail_length
            else:self.scroll=max(0,self.scroll+(-1 if key in ('up','k','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1))
        elif self.list.key(key):self.choose();self.scroll=0
        elif key in ('\r','\n','v'):
            if self.choose():self.open_map()
        elif key=='f5':self.directory.update(True)
        elif key=='\x1b':self.query=''
        elif not self.focus and key in ('\x7f','\b'):self.query=self.query[:-1]
        elif not self.focus and len(key)==1 and key.isprintable():self.query=(self.query+key)[:32]
        else:return False
        return True
    def pointer(self,column,row,width,button=0,released=False):
        rects=self.pane_rects()
        if self.layout.split_pointer(column,row,width,button,released,top=2,bottom=self.height-1):return True
        if released or button&32:return False
        if button==0 and row==0 and width-23<=column<width-12:return self.lookup_selected()
        if button==0 and row==0 and column>=width-12:
            if self.choose():self.open_map()
            return True
        if button==0 and row==2 and self.layout.tabbed:
            self.layout.select('list' if column<10 else 'details');return True
        for key,(x,y,w,h) in rects.items():
            if not(x<=column<x+w and y<=row<y+h):continue
            if button&64:
                if key=='list':self.list.scroll(3 if button&1 else -3,max(1,h-1))
                else:self.scroll=max(0,self.scroll+(3 if button&1 else -3))
                return True
            if button!=0:return False
            self.layout.select(key)
            if key=='list' and row>y:
                if self.list.pointer_at(column-x,row-y-1,w,max(1,h-1)):self.choose();self.scroll=0
            return True
        return False
    def selected_entities(self):
        from entity_actions import EntityRef
        call=(self.context.target or {}).get('call')
        return (EntityRef('station',call),) if call else ()
    def entities_at(self,column,row):
        from entity_actions import EntityRef
        self.sync();call=None
        for key,(x,y,w,h) in self.pane_rects().items():
            if not(x<=column<x+w and y<=row<y+h):continue
            if key=='list' and row>y:
                index=self.list.offset+row-y-1
                if self.list.has_scrollbar(w) and column==x+w-1:return ()
                if 0<=index<len(self.calls):call=self.calls[index]
            elif key=='details':call=(self.context.target or {}).get('call')
        return (EntityRef('station',call),) if call else ()
    def split(self):return self.pane_rects().get('list',(0,0,0,0))[2]
    def lines(self):
        self.directory.update();rows=self.sync();c=Canvas(self.width,self.height);rects=self.pane_rects();split=self.split()
        c.put(0,0,'Stations');c.put(max(0,self.width-23),0,'[ ULS U ]  [ View map ]')
        c.put(0,1,('Self addresses: '+self.self_editor.draw(max(1,self.width-16))) if self.self_editor is not None else 'Filter: '+self.query)
        counts=self.directory.counts
        c.put(0,0,f"Stations · {len(rows)} shown",max(1,self.width-24))
        target=self.context.target or {}
        self._spans=[(0,0,self.width,'toolbar'),(1,0,split,'input')]
        if self.layout.tabbed:c.put(0,2,'[Stations]  Details' if not self.focus else 'Stations  [Details]')
        else:c.divider(split,2,max(1,self.height-3))
        for key,(x,y,w,h) in rects.items():c.pane(x,y,w,h,'Stations' if key=='list' else target.get('call') or 'Selected station',key==self.layout.focus,inset=key=='list')
        if 'list' in rects:
            x,y,w,h=rects['list'];self.list.draw(c,x,y+1,w,max(1,h-1))
            if self.list.visible_selection is not None:self._spans.append((y+1+self.list.visible_selection,x,w,'selected'))
        detail=self.context.detail
        if detail and 'details' in rects:
            call=(self.context.target or {}).get('call','Unknown')
            target=self.context.target or {};position=target.get('position')
            license=self.license_lookup
            provider=getattr(self,'license_database_provider',None)
            if callable(provider) and not license.pending:
                path=provider()
                if path!=license.path.text:
                    license.path=TextInput(path,limit=1024);license.call=TextInput('',limit=16)
            license.poll()
            if license.call.text!=call and not license.pending:license.select_callsign(call)
            body=list(detail.get('lines',()))
            identity=[]
            if license.call.text==call:
                if license.result and license.result.get('record'):
                    record=license.result['record']
                    identity=['FCC LICENSE',record.get('name') or '',', '.join(str(record.get(k) or '') for k in ('city','region')),
                              'Class: '+str(record.get('license_class') or 'Not supplied')+' · Status: '+str(record.get('status') or 'Not supplied'),
                              'Expires: '+str(record.get('expires') or 'Not supplied'),'Mailing locality; not current position.','']
                elif license.pending:identity=['FCC license: looking up…','']
                elif license.error:identity=['FCC lookup unavailable · U opens lookup','']
                elif license.result:identity=['No FCC license found · US licences only','']
            if body and body[0].strip()==call:body.pop(0)
            body=identity+body
            body=[line.replace('Last reported ','Position received ').replace('Heard ','Last packet ',1) if line.lstrip().startswith(('Last reported ','Heard ')) else line for line in body]
            body+=['','Heard-through entries are aggregate observations.'] if detail.get('heard_through') else []
            x,y,w,h=rects['details'];width=max(1,w-2);wrapped=[]
            for line in body:wrapped.extend(textwrap.wrap(line,width,replace_whitespace=False) or [''])
            self._detail_length=len(wrapped)
            self.scroll=min(self.scroll,max(0,len(wrapped)-max(1,h-2)))
            for row,line in enumerate(wrapped[self.scroll:self.scroll+max(1,h-2)],y+2):c.put(x+1,row,line,width)
        if detail and detail.get('is_self'):c.put(0,self.height-2,'Configured self address · received evidence; RF echo unverified')
        if self.directory.error:c.put(0,self.height-2,'Directory unavailable: '+self.directory.error)
        c.put(0,self.height-1,'←/→ resize split · Enter done · Esc cancel' if self.layout.resizing else 'Tab pane · ↑↓ browse · Enter/v map · U ULS · / filter')
        if self.self_editor is not None:
            c.put(0,self.height-2,self.self_edit_error or 'Exact addresses, separated by spaces or commas. Empty means none.')
            c.put(0,self.height-1,'Enter saves · Esc cancels · Address SSIDs are separate identities')
        c.role(0,1,self.width,'muted');c.role(0,self.height-1,self.width,'muted')
        self._spans=c.styled_spans(self._spans)
        return c.lines()
    def spans(self):return tuple(self._spans)


class StationMap:
    def help_pages(self):
        from app_help_content import pages
        return pages('Station Map')
    filter_options=(('all','All stations'),('selected','Selected station'),('relays','Relay evidence'),('mobile','Mobile symbols (advertised)'),('links','Gateway/link symbols (advertised)'),('voice','Voice advertised'),('services','Services advertised'),('symbols','Symbol reported'),('unknown','No role or symbol'))
    def __init__(self,context,sources,open_directory,maps=None):
        self.context=context;self.renderer=Renderer(sources,maps=maps);self.renderer.reuse_regions=True;self.open_directory=open_directory
        self.width=90;self.height=32;self.center=(47.25,-122.25);self.span=160.;self._image=None;self._layer=None;self._key=None
        self._pan_drag=None;self._pan_dragged=False;self._track_revision=0;self._track_seen=set();self._image_view=None;self._display_layer=None;self._display_key=None;self.visible_count=0;self.map_notice=None
        self.legend=False;self.filter_mode='all';self.filter_query=TextInput(limit=40);self.filters=SelectList(tuple(label for _,label in self.filter_options))
        self.filter_open=False;self.filter_focus=0;self._filter_token=None;self._filter_rows=();self._filter_calls=frozenset();self._filter_spans=();self._station_hits=()
        def load(name):
            spec=importlib.util.spec_from_file_location('native_'+name.replace('-','_'),Path(sources)/(name+'.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
        self.tracks=load('n810-station-tracks').Tracks();self._decode_position=load('n810-aprs-decode').decode
        self.classify_symbol=load('n810-directory-model').classify_symbol
        display_symbol=load('n810-aprs-symbols').display_symbol
        icon_profile=profile_from_environment()
        self.display_symbol=lambda table,code:aprs_display(display_symbol(table,code),icon_profile)
    def configure_map_library(self,root,opener):self.renderer.configure_library(root,opener)
    def open_pack(self,reference):
        from map_library_provider import ApprovedProviderRef
        if reference is not None and not isinstance(reference,ApprovedProviderRef):reference=ApprovedProviderRef.from_mapping(reference)
        if not self.renderer.select_provider(reference):return False
        self.tracks.pause();self.cancel_pointer()
        if hasattr(self,'full_overview'):
            from packed_map import ProviderOverview
            self.full_overview=False
            if not hasattr(self,'_builtin_overview'):self._builtin_overview=self._overview
            self._overview=self._builtin_overview if reference is None else ProviderOverview(self)
            if hasattr(self,'_locator_overview'):
                if not hasattr(self,'_builtin_locator_overview'):self._builtin_locator_overview=self._locator_overview
                self._locator_overview=self._builtin_locator_overview if reference is None else ProviderOverview(self)
        if reference is not None:self.center=tuple(reference.initial_view[:2]);self.span=reference.initial_view[2]
        return True
    def poll(self):
        if self.context.refresh_catalog:self.context.refresh_catalog()
    def close(self):
        if self.context.close_catalog:self.context.close_catalog()
    def filtered_stations(self):
        call=(self.context.target or {}).get('call');query=self.filter_query.text.casefold()
        token=(self.context.map_revision,self.filter_mode,query,call if self.filter_mode=='selected' else None)
        if token!=self._filter_token:
            self._filter_token=token;catalog=self.context.map_catalog;rows=catalog['rows'] if catalog else ()
            def matches(row):
                if query not in (row['call']+' '+row.get('name','')).casefold():return False
                categories=row['categories'];symbol=row['symbol']
                if self.filter_mode in ('mobile','links'):
                    if symbol is None:return False
                    classified=self.classify_symbol(symbol['table'],symbol['code'])
                    return classified['advertised_mobile_symbol' if self.filter_mode=='mobile' else 'advertised_gateway_link_symbol'] is True
                return self.filter_mode=='all' or self.filter_mode=='selected' and row['call']==call or self.filter_mode=='relays' and any(tag in categories for tag in ('relay_observed','digipeater_advertised')) or self.filter_mode=='voice' and 'voice_advertised' in categories or self.filter_mode=='services' and any(tag.startswith('service:') for tag in categories) or self.filter_mode=='symbols' and row['symbol'] is not None or self.filter_mode=='unknown' and not categories and row['symbol'] is None
            self._filter_rows=tuple(row for row in rows if matches(row));self._filter_calls=frozenset(row['call'] for row in self._filter_rows)
        return self._filter_rows
    def selection_visible(self):
        self.filtered_stations();call=(self.context.target or {}).get('call')
        return not self.filter_query.text and self.filter_mode in ('all','selected') or call in self._filter_calls
    def open_filters(self,query=False):
        self.filter_open=True;self.filter_focus=int(query);self.filters.index=next(i for i,(key,_) in enumerate(self.filter_options) if key==self.filter_mode);self.filters.reveal()
    def apply_filter(self):
        self.filter_mode=self.filter_options[self.filters.index][0];self.filter_open=False;self.map_notice=None
    def filter_key(self,key):
        if key=='\x1b':self.filter_open=False;return True
        if key in ('\t','backtab'):self.filter_focus=1-self.filter_focus;return True
        if key in ('\r','\n'):self.apply_filter();return True
        if self.filter_focus:return self.filter_query.key(key)
        if key=='/':self.filter_focus=1;return True
        if key=='g':self.filter_open=False;return True
        if key=='c':self.filter_mode='all';self.filter_query=TextInput(limit=40);self.filters.index=0;self.filters.reveal();return True
        return self.filters.key(key)
    def filter_lines(self):
        c=Canvas(self.width,self.height);c.pane(0,0,self.width,max(1,self.height-1),'Station map filters',True)
        c.put(max(0,self.width-10),0,'[ Esc ]',10)
        c.put(0,1,'Name: '+(self.filter_query.draw(max(1,self.width-6)) if self.filter_focus else self.filter_query.text or '(any callsign or name)'),self.width)
        c.role(0,1,self.width,'input' if self.filter_focus else 'muted')
        c.put(0,2,'Show');self.filters.draw(c,0,3,self.width,max(1,self.height-6))
        if self.filters.visible_selection is not None:c.role(0,3+self.filters.visible_selection,self.width,'selected')
        rows=self.filtered_stations();known=sum(row['position'] is not None for row in rows)
        c.put(0,self.height-3,f'Active: {dict(self.filter_options)[self.filter_mode]} · {len(rows)} matches · {known} located',self.width)
        c.put(0,self.height-2,'Advertised/observed evidence · unknown is not absence',self.width)
        c.put(0,self.height-1,'↑↓ choose  Enter apply  / name  Tab field  c clear  Esc map',self.width)
        self._filter_spans=tuple(c.styled_spans());return c.lines()
    def filter_pointer(self,column,row,width,button,released):
        if released or button&32:return False
        if button&64:
            if not 3<=row<self.height-3:return False
            self.filters.scroll(3 if button&1 else -3,max(1,self.height-6));return True
        if button!=0:return False
        if row==0 and column>=width-10:self.filter_open=False;return True
        if row==1:self.filter_focus=1;return True
        if 3<=row<self.height-3:
            self.filter_focus=0
            if self.filters.pointer_at(column,row-3,width,max(1,self.height-6)):self.apply_filter()
            return True
        return False
    def fit_stations(self):
        catalog=self.context.map_catalog
        positions=[(row['position']['lat'],row['position']['lon']) for row in self.filtered_stations() if row['position']]
        if not positions:
            self.map_notice='No known catalog positions';return False
        latitudes,longitudes=zip(*positions);lat=max(-85,min(85,(min(latitudes)+max(latitudes))/2));lon=(min(longitudes)+max(longitudes))/2
        width,height=raster_size(self.width,self.height-3)
        horizontal=(max(longitudes)-min(longitudes))*111.32*math.cos(math.radians(lat))
        vertical=(max(latitudes)-min(latitudes))*111.32*max(1,width-1)/max(1,height-1)/2
        wanted=max(getattr(self,'minimum_span',.25),max(horizontal,vertical)*1.15)
        self.tracks.pause();self.center=(lat,lon);self.span=min(2000.,wanted)
        self.map_notice='Some positions exceed map range' if wanted>2000 else None
        return True
    def update_tracks(self,packets):
        seen=set();changed=False
        for packet in packets[-200:]:
            if packet.get('direction')!='radio_to_host':continue
            raw=packet.get('raw');stamp=packet.get('time')
            if not isinstance(raw,str) or not isinstance(stamp,str):continue
            token=(stamp,raw);seen.add(token)
            if token in self._track_seen:continue
            match=re.fullmatch(r'(\S+)>(\S+) ctl=[0-9a-f]+ pid=f0 (.*)',raw)
            if not match:continue
            call,route,payload=match.groups()
            position=self._decode_position(payload,route.split(',')[0]).get('position')
            if not position:continue
            try:
                parsed=datetime.datetime.fromisoformat(stamp)
                observed=parsed.timestamp() if parsed.tzinfo is not None else None
            except ValueError:observed=None
            if self.tracks.add(call,*position,stamp=stamp,observed_at=observed):changed=True
        self._track_seen=seen
        if changed:self._track_revision+=1
        return changed
    def toggle_follow(self):
        call=(self.context.target or {}).get('call')
        if not call:return
        if self.tracks.call==call:
            if self.tracks.paused:self.tracks.resume()
            else:self.tracks.stop()
        else:self.tracks.follow(call)
    def focus_selection(self):
        self.tracks.pause()
        position=(self.context.target or {}).get('position')
        if position:self.center=tuple(position);self.span=min(self.span,80.)
    @staticmethod
    def distance_label(span):
        return f'{span*1000:.0f} m' if span<1 else f'{span:.4g} km'
    def scale_label(self):
        displayed=self._image_view[1] if self._image is not None and self._image_view else self.span
        label=self.distance_label(displayed)+' wide'
        if displayed!=self.span:label+=' · '+self.distance_label(self.span)+' requested'
        return label
    def map_controls(self):
        x=0;items=[]
        for label,key in (('[ - ]','-'),('[ + ]','+'),('[ Key l ]','l'),('[←]','left'),('[↑]','up'),('[↓]','down'),('[→]','right')):
            if x+len(label)>self.width:break
            items.append((x,len(label),label,key));x+=len(label)+1
        return tuple(items)
    def zoom_step(self,inward):
        anchor,step,previous=getattr(self,'_zoom_steps',(self.span,0,self.span))
        if previous!=self.span:anchor,step=self.span,0
        step+=1 if inward else -1
        span=max(getattr(self,'minimum_span',.25),min(2000.,anchor*.8**step))
        self._zoom_steps=(anchor,step,span) if .25<span<2000 else (span,0,span)
        self.span=span
    def pan_step(self,key):
        opposite={'left':'right','right':'left','up':'down','down':'up'}
        camera=(tuple(self.center),self.span);history=getattr(self,'_pan_steps',[])
        if history and history[-1][2]!=camera:history=[]
        if history and history[-1][0]==opposite[key]:
            _,before,_=history.pop();self.center,self.span=before
        else:
            lat,lon=self.center;delta=self.span*.15/111.32
            if key in ('up','down'):lat+=delta*(1 if key=='up' else -1)
            else:lon+=delta*(1 if key=='right' else -1)/max(.1,math.cos(math.radians(lat)))
            self.center=(max(-85,min(85,lat)),(lon+180)%360-180)
            history.append((key,camera,(tuple(self.center),self.span)));history=history[-32:]
        self._pan_steps=history
    def key(self,key):
        if self._pan_drag is not None:self.cancel_pointer()
        if self.filter_open:return self.filter_key(key)
        if key in ('g','/'):self.open_filters(key=='/');return True
        if key=='l':self.legend=not self.legend;return True
        if key in ('+','='):self.zoom_step(True)
        elif key=='-':self.zoom_step(False)
        elif key=='a':self.fit_stations()
        elif key=='f':self.map_notice=None;self.tracks.pause();self.focus_selection()
        elif key=='F':self.toggle_follow()
        elif key=='d':self.open_directory()
        elif key in ('left','right','up','down'):
            self.tracks.pause()
            self.pan_step(key)
        else:return False
        return True
    def pointer(self,column,row,width,button=0,released=False):
        if self.filter_open:return self.filter_pointer(column,row,width,button,released)
        if released:
            if self._pan_drag is None:return False
            press=self._pan_drag[:2]
            self._pan_to(column,row);self._pan_drag=None
            click=not self._pan_dragged
            if click and self.context.select_station:
                refs=self.entities_at(*press);calls=[ref.key for ref in refs if ref.kind=='station']
                current=(self.context.target or {}).get('call')
                if calls:self.context.select_station(calls[(calls.index(current)+1)%len(calls)] if current in calls else calls[0])
                if len(calls)>1:self.map_notice=f'{len(calls)} overlapping stations · click again to cycle'
            return True
        if button&32:
            if self._pan_drag is None:return False
            self._pan_to(column,row);return True
        if button&64:
            if not (0<=column<width and 2<=row<self.height-1):return False
            self._pan_drag=None
            return self.zoom_at_pointer(column,row,width,button&1)
        if button==0 and row==self.height-1:
            for x,length,_,key in self.map_controls():
                if x<=column<x+length:return self.key(key)
            return False
        if button==0 and row==0 and width-37<=column<width-24:self.open_filters();return True
        if button==0 and row==0 and column>=width-12:self.open_directory();return True
        if button==0 and row==0 and width-24<=column<width-12:self.toggle_follow();return True
        if button==0 and 0<=column<width and 2<=row<self.height-1:
            self._pan_dragged=False
            self._pan_drag=(column,row,self.center,self.span,max(1,width),max(1,self.height-3));return True
        return False
    def zoom_at_pointer(self,column,row,width,out=False):
        span=min(2000.,self.span/.8) if out else max(getattr(self,'minimum_span',.25),self.span*.8)
        if span==self.span:return True
        height=max(1,self.height-3);rw,rh=raster_size(width,height)
        center,old_span=self._image_view or (self.center,self.span)
        old_w,old_h=(self._image.width,self._image.height) if self._image is not None else (rw,rh)
        def cell(value,screen,logical):return max(0,min(logical-1,(value+.5)*logical/max(1,screen)-.5))
        x,y=cell(column,width,old_w),cell(row-2,height,old_h)
        projection=getattr(self._image,'projection',None)
        if callable(getattr(projection,'unproject',None)):lat,lon=projection.unproject(x,y)
        elif projection is not None:
            lat0,lon0=projection.center
            degrees=projection.span/max(1,projection.width-1)/111.32
            lat=lat0-(y-(projection.height-1)/2)*degrees*projection.cell_aspect
            lon=lon0+(x-(projection.width-1)/2)*degrees/max(.000001,math.cos(math.radians(lat0)))
        else:
            degrees=old_span/max(1,old_w-1)/111.32
            lat=center[0]-(y-(old_h-1)/2)*degrees*2
            lon=center[1]+(x-(old_w-1)/2)*degrees/max(.000001,math.cos(math.radians(center[0])))
        x,y=cell(column,width,rw),cell(row-2,height,rh)
        degrees=span/max(1,rw-1)/111.32
        lat=max(-85,min(85,lat+(y-(rh-1)/2)*degrees*2))
        lon-= (x-(rw-1)/2)*degrees/max(.000001,math.cos(math.radians(lat)))
        self.tracks.pause();self.center=(lat,(lon+180)%360-180);self.span=span
        return True

    @property
    def pointer_captured(self):return self._pan_drag is not None
    def cancel_pointer(self):
        if self._pan_drag is not None:self.center=self._pan_drag[2]
        self._pan_drag=None;self._pan_dragged=False
    def _pan_to(self,column,row):
        x,y,(lat,lon),span,width,height=self._pan_drag
        dx=max(-width*2,min(width*2,column-x));dy=max(-height*2,min(height*2,row-y))
        if not self._pan_dragged:
            if abs(dx)<=1 and abs(dy)<=1:return
            self._pan_dragged=True
        if dx or dy:self.tracks.pause()
        degrees=span/max(1,width-1)/111.32
        self.center=(max(-85,min(85,lat+dy*degrees*2)),(lon-dx*degrees/max(.1,math.cos(math.radians(lat)))+180)%360-180)
    def lines(self):
        if self.filter_open:return self.filter_lines()
        if self.tracks.call and (self.context.target or {}).get('call')!=self.tracks.call:self.tracks.pause()
        camera=self.tracks.camera_position()
        if camera is not None:self.center=camera
        w,h=max(1,self.width),max(1,self.height-3)
        image=self.renderer.frame(self.center,self.span,w,h)
        updating=image is None and self._image is not None
        if image is not None:
            self._image=image;self._image_view=(tuple(self.center),self.span)
        image=self._image;c=Canvas(self.width,self.height)
        target=self.context.target or {};call=target.get('call') or 'No station selected'
        catalog=self.context.map_catalog;selected=next((row for row in catalog['rows'] if row['call']==call),None) if catalog else None
        symbol=selected['symbol'] if selected else None
        heading=call+(' ['+symbol['table']+symbol['code']+'] '+self.display_symbol(symbol['table'],symbol['code'])['name'] if symbol else '')
        c.put(0,0,heading,max(0,self.width-39));c.put(max(0,self.width-37),0,'[ Filters g ]');c.put(max(0,self.width-24),0,'[ Follow F ]');c.put(max(0,self.width-12),0,'[ Stations ]')
        status=('Following '+self.tracks.call+(' · paused' if self.tracks.paused else '')) if self.tracks.call else 'station selection'
        loading=getattr(self.renderer,'loading_message',lambda:'Loading offline map…')()
        if updating:status=((self.renderer.pack_state.get('reason') or 'Map update unavailable') if self.renderer.error else loading)+' · '+status
        elif image is not None and image.source=='regional-pack':
            state=getattr(image,'pack_status',{})
            native=state.get('native_spacing_m');requested=state.get('requested_spacing_m')
            label=('Coarse' if state.get('coarse_fallback') else 'Prepared')+' '+state.get('pack','map')
            status=label+(f' {map_spacing(native)} grid / {map_spacing(requested)} cells' if native is not None and requested is not None else '')+' · '+state.get('dem_resolution','')
        detail_status=status+' · '+self.tracks.freshness(time.time(),call)+' · RX time '+str((self.tracks.points(call) or [{}])[-1].get('time') or target.get('position_time') or 'unknown date')
        c.put(0,1,self.scale_label()+' · '+detail_status)
        for x,_,label,_ in self.map_controls():c.put(x,self.height-1,label)
        controls=self.map_controls();end=controls[-1][0]+controls[-1][1]+1 if controls else 0
        c.put(end,self.height-1,'drag to pan · a fit · g filters',max(0,self.width-end))
        if image is None:
            c.put(0,3,self.renderer.error or loading);self._layer=None
        else:
            self._layer=self.station_layer(image)
        catalog=self.context.map_catalog
        if catalog is not None:
            rows=self.filtered_stations();known=sum(row['position'] is not None for row in rows);unknown=len(rows)-known
            label=dict(self.filter_options)[self.filter_mode]+(' /'+self.filter_query.text[:12] if self.filter_query.text else '')
            summary=f'{label}: {self.visible_count} shown · {known} located · {unknown} unknown'+(' · more not loaded' if catalog['has_more'] else '')
            if self.context.target and not self.selection_visible():summary='Selection hidden · '+summary
            if self.map_notice:
                detail=self.map_notice+(' · more not loaded' if catalog['has_more'] else '')+f' · {known} located/{unknown} unknown'
            else:detail=(status+' · '+summary) if updating else detail_status+' · '+summary
            c.put(0,1,(self.scale_label()+' · '+detail)[:self.width].ljust(self.width))
        elif self.context.map_error:c.put(0,1,('Catalog unavailable · '+self.context.map_error)[:self.width].ljust(self.width))
        display_key=(id(self._layer),w,h)
        if display_key!=self._display_key:
            self._display_key=display_key;self._display_layer=self._layer
            if self._layer and (image.width,image.height)!=(w,h):
                self._display_layer=(0,2,w,h,ScaledPlane(self._layer[4],image.width,image.height,w,h))
        return c.lines()
    def station_layer(self,image):
        """Project station symbols/tracks into any displayed detail or preview view."""
        target=self.context.target or {};call=target.get('call') or 'No station selected'
        catalog=self.context.map_catalog
        selected=next((row for row in catalog['rows'] if row['call']==call),None) if catalog else None
        projection=getattr(image,'projection',None)
        center,span=(projection.center,projection.span) if projection is not None else self._image_view
        from repeater_catalog import signature,annotate
        key=(getattr(self,'station_labels',False),getattr(self,'repeater_labels',False),tuple(getattr(self,'repeater_bands',())),getattr(self,'internet_revision',0),getattr(self,'show_repeaters',True),signature(),id(image),self.context.revision,self.context.map_revision,self.filter_mode,self.filter_query.text,self.legend,center,span,self._track_revision)
        if key!=self._key:
            overlay={};points=self.tracks.points(call) if self.selection_visible() else ()
            position=((points[-1]['lat'],points[-1]['lon']) if points else target.get('position')) if self.selection_visible() else None
            view=getattr(image,'projection',None) or self.renderer.module.Viewport(center,span,image.width,image.height)
            rows=self.filtered_stations()
            self.visible_count=0;labels=0;occupied=set();hits=[]
            budget=min(24,image.width*image.height//150)
            visible=[]
            for station in rows:
                item=station['position']
                if not item or station['call']==call:continue
                x,y=map(round,view.project(item['lon'],item['lat']))
                if 0<=x<image.width and 0<=y<image.height:visible.append((station,x,y))
            occupied={(x,y) for _,x,y in visible}
            if position:
                sx,sy=map(round,view.project(position[1],position[0]))
                occupied.update((x,y) for x in range(sx,min(image.width,sx+len(call)+3)) for y in range(max(0,sy-1),min(image.height,sy+2)))
            for station,x,y in visible:
                self.visible_count+=1;categories=station['categories']
                relay='relay_observed' in categories or 'digipeater_advertised' in categories
                voice='voice_advertised' in categories
                symbol=station['symbol'];classified=self.classify_symbol(symbol['table'],symbol['code']) if symbol else {}
                mobile=classified.get('advertised_mobile_symbol') is True;gateway=classified.get('advertised_gateway_link_symbol') is True
                glyph='◆' if relay else 'G' if gateway else '→' if mobile else '▲' if voice else '●'
                display=self.display_symbol(symbol['table'],symbol['code']) if symbol else None
                if display:glyph=display['glyph']
                color=(212,162,255) if relay else (255,182,120) if voice else (112,204,255)
                under=image.cells[y*image.width+x][1];bg=tuple((under>>shift)&255 for shift in (16,8,0))
                overlay[y*image.width+x]=(glyph,ink(*color,background=bg))
                hits.append((x,y,1,station['call']))
                if display and display['overlay'] and x+1<image.width and (x+1,y) not in occupied:
                    overlay[y*image.width+x+1]=(display['overlay'],ink(*color,background=bg));hits.append((x+1,y,1,station['call']))
                label=station['call']+(' '+symbol['table']+symbol['code'] if symbol else '');places={(xx,yy) for xx in range(x+1,min(image.width,x+len(label)+3)) for yy in range(max(0,y-1),min(image.height,y+2))}
                if getattr(self,'station_labels',False) and labels<budget and x+2+len(label)<=image.width and not occupied.intersection(places):
                    for n,char in enumerate(label):
                        index=y*image.width+x+2+n;under=image.cells[index][1];bg=tuple(round(((under>>shift)&255)*.55) for shift in (16,8,0))
                        overlay[index]=(char,ink(*color,background=bg))
                    labels+=1;occupied.update(places);hits.append((x+2,y,len(label),station['call']))
            for point in points[:-1]:
                x,y=map(round,view.project(point['lon'],point['lat']))
                if 0<=x<image.width and 0<=y<image.height:
                    under=image.cells[y*image.width+x][1];bg=tuple((under>>s)&255 for s in (16,8,0))
                    overlay[y*image.width+x]=(':',ink(170,208,196,background=bg))
            if position:
                x,y=map(round,view.project(position[1],position[0]))
                if 0<=x<image.width and 0<=y<image.height:
                    self.visible_count+=1
                    selected_symbol=selected['symbol'] if selected else None
                    display=self.display_symbol(selected_symbol['table'],selected_symbol['code']) if selected_symbol else None
                    label=(display['glyph']+(display['overlay'] or '') if display else '●')+' '+call+(' '+selected_symbol['table']+selected_symbol['code'] if selected_symbol else '')
                    hits.append((x,y,len(label),call))
                    for n,char in enumerate(label):
                        if 0<=x+n<image.width:
                            under=image.cells[y*image.width+x+n][1];bg=tuple((under>>s)&255 for s in (16,8,0))
                            overlay[y*image.width+x+n]=(char,ink(255,232,150,background=bg))
            if self.legend:
                definitions=[]
                for station in rows:
                    symbol=station['symbol']
                    if symbol:
                        display=self.display_symbol(symbol['table'],symbol['code']);entry=display['glyph']+(display['overlay'] or '')+' '+symbol['table']+symbol['code']+' '+display['name']
                        if entry not in definitions:definitions.append(entry)
                legend=('Water blue · land green/brown · peaks grey/white · Gold: selected · l hide', ' · '.join(definitions[:4]) or '● No advertised symbol · unknown is not absence')
                for row,text in enumerate(legend):
                    y=max(0,image.height-len(legend))+row
                    for x,char in enumerate(text[:image.width]):overlay[y*image.width+x]=(char,ink(230,232,240,background=(18,22,30)))
                hits=[hit for hit in hits if hit[1]<max(0,image.height-len(legend))]
            for internet_call,pos in getattr(self,'internet_positions',{}).items():
                if any(r['call']==internet_call and r.get('position') for r in rows):continue
                lat,lon=(pos.get('lat'),pos.get('lon')) if isinstance(pos,dict) else pos[:2]
                x,y=map(round,view.project(lon,lat))
                label='I '+internet_call if getattr(self,'station_labels',False) or internet_call==call else 'I'
                if 0<=x<image.width and 0<=y<image.height:
                    for i,char in enumerate(label[:image.width-x]):overlay[y*image.width+x+i]=(char,ink(120,235,190,background=(12,35,30)))
                    hits.append((x,y,min(len(label),image.width-x),internet_call))
            self._repeater_hits=annotate(image,view,overlay,occupied,getattr(self,'repeater_bands',__import__('repeater_catalog').BANDS),show_labels=getattr(self,'repeater_labels',False)) if getattr(self,'show_repeaters',True) else ()
            self._station_hits=tuple(hits);self._layer=(0,2,image.width,image.height,Plane(image.cells,overlay));self._key=key
        return self._layer
    def selected_entities(self):
        from entity_actions import EntityRef
        call=(self.context.target or {}).get('call')
        return (EntityRef('station',call),) if call else ()
    def entities_at(self,column,row):
        from entity_actions import EntityRef
        if self.filter_open or self._image is None or not (0<=column<self.width and 2<=row<self.height-1):return ()
        x=(column+.5)*self._image.width/max(1,self.width)-.5
        y=(row-2+.5)*self._image.height/max(1,self.height-3)-.5
        calls=[]
        for start,line,width,call in reversed(self._station_hits):
            if start-.5<=x<start+width-.5 and abs(line-y)<=.5 and call not in calls:calls.append(call)
        return tuple(EntityRef('station',call) for call in calls)+tuple(EntityRef('repeater',item['id'],item) for start,line,width,item in getattr(self,'_repeater_hits',()) if start-.5<=x<start+width-.5 and abs(line-y)<=.5)
    def layer(self):return None if self.filter_open else self._display_layer
    def spans(self):return self._filter_spans if self.filter_open else ((0,0,self.width,'toolbar'),(1,0,self.width,'muted'))


from map_gestures import map_candidate
StationMap=map_candidate(StationMap,policy=dict(slop=(1,1),radius=(2,1),max_contact_ns=250_000_000,interval_ns=350_000_000))

# Keep the accepted source-timed gesture bridge; adapt map-local navigation once.
from map_navigation import map_class
StationMap=map_class(StationMap)
