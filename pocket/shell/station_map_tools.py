"""Station Map owns terrain tools; navigation, renderer and camera stay shared."""
from entity_actions import EntityRef


class StationMapTools:
    def __init__(self,base,qth_path=None):
        self._disabled_qth=None;self.terrain_enabled=True;self.layers_visible=False;self._panel_layer=None;self.dialog=None;self.dialog_spans=();self.internet=None;self.internet_own='';self.internet_calls='';self.internet_editor=None;self.qth_path=qth_path;self._saved_pin_layer=None
        self.sidebar_tab='layers';self.detail_repeater=None;self.detail_point=None;self._detail_press=None;self._detail_call=None;self.sidebar_scroll=0;self._sidebar_max_scroll=0
        self.base=base;self.tool=None;self.terrain_active=False;self._wakeup=None;self._session_callback=None;self._saved_terrain={};self._terrain_button_row=0
    def __getattr__(self,name):return getattr(self.base,name)
    def bind_wakeup(self,callback):
        self._wakeup=callback;self.base.renderer.completion_wakeup=callback
        if self.tool:self.tool.bind_wakeup(callback)
    def ensure_tool(self):
        if self.tool is None:
            from native_terrain_profile import TerrainProfile
            self.tool=TerrainProfile(map_base=self.base,qth_path=self.qth_path)
            if self._wakeup:self.tool.bind_wakeup(self._wakeup)
            if self._saved_terrain:self.tool.restore_session(self._saved_terrain)
            if self._session_callback:self.tool.bind_session(self._session_callback)
            self.tool.resolve_station=self.resolve_station
            self.tool.enabled_provider=lambda:self.terrain_enabled
        return self.tool
    def preferences_changed(self,preferences):
        self.terrain_enabled=bool(preferences.get('terrain-enabled',True))
        if not self.terrain_enabled:
            self.terrain_active=False
            if self.tool:self._disabled_qth=self.tool.map.qth
            elif self.qth_path:
                from terrain_qth import QTH
                try:
                    saved=QTH(self.qth_path).read()
                    if saved:self._disabled_qth=(saved['latitude'],saved['longitude'])
                except (OSError,ValueError):pass
            if self.tool:
                self._saved_terrain=self.tool.session_state();self.tool.close();self.tool=None
            self._panel_layer=None;self._saved_pin_layer=None
    def terrain_unavailable(self):
        self.base.map_notice='Terrain and LOS disabled · Settings → App: Station Map'
        return False
    def resolve_station(self,call):
        select=self.base.context.select_station
        if select and select(call):
            position=(self.base.context.target or {}).get('position')
            if position:return position
        if self.internet:
            position=self.internet.snapshot().get(call)
            if position:return (position['lat'],position['lon']) if isinstance(position,dict) else tuple(position[:2])
        return None
    def profile_from_qth(self,call,position=None):
        if not self.terrain_enabled:return self.terrain_unavailable()
        tool=self.ensure_tool();self.terrain_active=True
        self.layers_visible=False;self.base.side_overview=False;self.dialog=None
        tool.screen='profile';tool.error='';tool.target_label=call
        position=position or self.resolve_station(call)
        if not position:
            tool.error='No observed position for '+call;tool.status='Profile unavailable';return False
        return tool.profile_to_location(call,position)
    def bind_session(self,callback):
        self._session_callback=callback;self.base.bind_session(callback)
        if self.tool:self.tool.bind_session(callback)
    def session_state(self):
        return dict(station_labels=getattr(self.base,'station_labels',False),repeater_labels=getattr(self.base,'repeater_labels',False),sidebar_tab=self.sidebar_tab,repeater_bands=list(getattr(self.base,'repeater_bands',__import__('repeater_catalog').BANDS)),layers_visible=self.layers_visible,show_repeaters=getattr(self.base,'show_repeaters',True),internet_own=self.internet_own,internet_calls=self.internet_calls,terrain_active=self.terrain_active,navigation=self.base.session_state(),terrain=self.tool.session_state() if self.tool else self._saved_terrain)
    def restore_session(self,state):
        if not isinstance(state,dict):return
        from repeater_catalog import BANDS
        self.base.repeater_bands=tuple(b for b in state.get('repeater_bands',BANDS) if b in BANDS)
        for key in ('station_labels','repeater_labels'):setattr(self.base,key,bool(state.get(key,False)))
        self.sidebar_tab='details' if state.get('sidebar_tab')=='details' else 'layers'
        self.layers_visible=bool(state.get('layers_visible',False))
        self.base.show_repeaters=bool(state.get('show_repeaters',True))
        for key in ('internet_own','internet_calls'):
            value=state.get(key,'')
            if isinstance(value,str):setattr(self,key,value[:350])
        self.base.restore_session(state.get('navigation',state))
        self.base.side_overview=self.layers_visible
        saved=state.get('terrain')
        if isinstance(saved,dict):
            self._saved_terrain=saved
            fields=saved.get('fields',[])
            self.terrain_active=bool(state.get('terrain_active',saved.get('mode')=='area' and fields and fields[0]))
        if not self.terrain_enabled:self.terrain_active=False
        if self.tool and self._saved_terrain:self.tool.restore_session(self._saved_terrain)
    def enter_terrain(self,mode=None,position=None,end=False):
        if not self.terrain_enabled:return self.terrain_unavailable()
        tool=self.ensure_tool();self.terrain_active=True;tool.screen='map'
        mode=mode or tool.map.mode;tool.map.mode=mode
        if position is not None:tool.set_endpoint(position,end=end)
        if mode=='area' and tool.qth and position is not None and tuple(position)==tuple(tool.map.qth):
            from app_widgets import TextInput
            tool.fields[3]=TextInput(f"{tool.qth['height_m']:g}",limit=8)
        tool.map.end=not end if mode=='path' else False
        tool.map.notice='Fixed LOS origin · right-click to choose another' if mode=='area' else 'Choose endpoints · P profile · Esc return to stations'
        if mode=='area' and position is not None:tool.show_los()
        return True
    def coverage_from_location(self,label,position,frequency,height_m=None):
        if not self.terrain_enabled:return self.terrain_unavailable()
        from app_widgets import TextInput
        tool=self.ensure_tool();tool.map.origin_label=label[:48]
        tool.fields[2]=TextInput(str(frequency),limit=12);tool.map.band_label=str(frequency)+' MHz'
        # Directory listings do not establish antenna height above ground.
        tool.fields[3]=TextInput(str(10 if height_m is None else height_m),limit=8)
        tool.fields[4]=TextInput('2',limit=8)
        self.enter_terrain('area',position)
        tool.status='Approximate directory site · antenna '+('10 m assumed; H to edit' if height_m is None else str(height_m)+' m AGL')
        tool.map.notice=tool.status
        return True
    def show_repeater(self,item):
        self.sidebar_scroll=0
        self.detail_point=None;self.detail_repeater=item;self._detail_call=(self.base.context.target or {}).get('call')
        self.sidebar_tab='details';self.layers_visible=True;self.base.side_overview=True
        if self._session_callback:self._session_callback()
        return True
    def detail_rows(self):
        item=self.detail_repeater
        if item:
            return [(text,None,None) for text in (
                item['call']+' · '+__import__('repeater_catalog').band(item['rx_mhz']),
                item.get('site',''),
                'RX '+str(item['rx_mhz'])+' MHz',
                'TX '+str(item['tx_mhz'])+' MHz',
                'TX tone '+str(item.get('tx_ctcss') or 'Off'),
                'RX tone '+str(item.get('rx_ctcss') or 'Off'),
                'DCS '+str(item.get('dcs') or 'Off'),
                ', '.join(item.get('modes',[])),
                item.get('area',''),
                'WWARA '+item.get('edition',''),
                'Approx. directory location',
                'Right-click for tune / LOS') if text]
        if self.detail_point:
            point=self.detail_point;lat,lon=point['position']
            return [(text,None,None) for text in (point.get('label','QTH'),f'{lat:.4f}, {lon:.4f}','Saved station location','Right-click for actions')]
        target=self.base.context.target or {};call=target.get('call')
        if not call:return [('Select a station or repeater',None,None),('on the map for details.',None,None)]
        catalog=self.base.context.map_catalog or {}
        item=next((row for row in catalog.get('rows',()) if row['call']==call),{})
        rows=[call,item.get('name','')]
        position=target.get('position')
        if position:rows += [f'{position[0]:.4f}, {position[1]:.4f}']
        symbol=item.get('symbol')
        if symbol:
            rows += [self.base.display_symbol(symbol['table'],symbol['code'])['name']]
        rows += ['Selected station stays labeled','Right-click for actions']
        return [(text,None,None) for text in rows if text]
    def internet_toggle(self):
        from aprs_fill import Fill
        if self.internet and self.internet.thread:
            self.internet.close();return True
        if not self.internet:self.internet=Fill(self._wakeup)
        calls=self.internet_calls.replace(',',' ').split()
        selected=(self.base.context.target or {}).get('call')
        if selected and selected not in calls:calls.append(selected)
        try:self.internet.start(self.internet_own.upper(),calls)
        except ValueError as error:self.internet.publish(str(error))
        return True
    def open_layers(self):
        self.layers_visible=not getattr(self.base,'side_overview',False)
        self.base.side_overview=self.layers_visible
        if self._session_callback:self._session_callback()
        return True
    def modal(self):return self.dialog is not None or self.terrain_active
    def navigation_modal_hint(self):return self.tool.navigation_modal_hint() if self.tool else ('Station Map','T terrain')
    @property
    def width(self):return self.base.width
    @width.setter
    def width(self,value):self.base.width=value
    @property
    def height(self):return self.base.height
    @height.setter
    def height(self,value):self.base.height=value
    @property
    def center(self):return self.base.center
    @center.setter
    def center(self,value):self.base.center=value
    @property
    def span(self):return self.base.span
    @span.setter
    def span(self,value):self.base.span=value
    def key(self,key):
        if self.internet_editor is not None:
            field,editor=self.internet_editor
            if key in ('\r','\n'):
                setattr(self,'internet_'+field,editor.text.upper());self.internet_editor=None
                if field=='own' and callable(getattr(self,'save_own_call',None)):self.save_own_call(self.internet_own)
                if self._session_callback:self._session_callback()
            elif key in ('escape','\x1b'):self.internet_editor=None
            else:editor.key(key)
            return True
        if self.dialog:
            if self.dialog[0]=='Tune UV-Pro' and key.lower()=='b':self.tuner.start({'restore':True})
            elif self.dialog[0]=='Map layers' and key.lower() in ('c','a'):
                from app_widgets import TextInput
                field='own' if key.lower()=='a' else 'calls'
                self.internet_editor=(field,TextInput(getattr(self,'internet_'+field),limit=350))
            elif self.dialog[0]=='Map layers' and key.lower()=='i':self.internet_toggle()
            elif self.dialog[0]=='Map layers' and key.lower()=='r':
                self.base.show_repeaters=not getattr(self.base,'show_repeaters',True);self.base._key=None
                if self._session_callback:self._session_callback()
            elif self.dialog[0]=='Map layers' and key.lower()=='f':
                self.dialog=None;return self.base.key('g')
            elif key in ('escape','\x1b','\r','\n'):self.dialog=None
            return True
        map_screen=not self.terrain_active or self.ensure_tool().screen=='map'
        if key.lower()=='s' and map_screen:
            self.base.key('s');self.layers_visible=bool(self.base.side_overview);return True
        if map_screen and (self.layers_visible or getattr(self.base,'side_overview',False)):
            lower=key.lower()
            if key in ('escape','\x1b'):
                self.layers_visible=False;self.base.side_overview=False;return True
            if key in ('up','down','pageup','pagedown','home','end'):
                step={'up':-1,'down':1,'pageup':-5,'pagedown':5}.get(key,0)
                self.sidebar_scroll=0 if key=='home' else self._sidebar_max_scroll if key=='end' else max(0,min(self._sidebar_max_scroll,self.sidebar_scroll+step))
                return True
            if lower in ('l','d'):
                self.sidebar_scroll=0
                self.sidebar_tab='layers' if lower=='l' else 'details'
                if self._session_callback:self._session_callback()
                return True
            if lower in ('n','p'):
                attr='station_labels' if lower=='n' else 'repeater_labels'
                setattr(self.base,attr,not getattr(self.base,attr,False))
                if self._session_callback:self._session_callback()
                return True
            if lower=='r':
                self.base.show_repeaters=not getattr(self.base,'show_repeaters',True)
                if self._session_callback:self._session_callback()
                return True
            if lower in ('a','c'):
                from app_widgets import TextInput
                field='own' if lower=='a' else 'calls'
                self.internet_editor=(field,TextInput(getattr(self,'internet_'+field),limit=350));return True
            if lower=='i':return self.internet_toggle()
            if lower=='t' and callable(getattr(self,'open_app_settings',None)):return self.open_app_settings()
            if lower in ('u','z'):return self.base.key(lower)
            if lower=='f':return self.base.key('g')
        if map_screen and (self.layers_visible or getattr(self.base,'side_overview',False)) and key in '123456':
            from repeater_catalog import BANDS
            enabled=set(getattr(self.base,'repeater_bands',BANDS));band=BANDS[int(key)-1]
            enabled.symmetric_difference_update((band,));self.base.repeater_bands=tuple(b for b in BANDS if b in enabled)
            if self._session_callback:self._session_callback()
            return True
        if self.terrain_active:
            self.ensure_tool()
            if key in ('escape','\x1b') and self.tool.screen=='map' and not self.base.full_overview and self.base.target_box.view is None:
                self.terrain_active=False;self.base.cancel_pointer();return True
            return self.tool.key(key)
        if key in ('g','G') and self.terrain_enabled:
            self.enter_terrain();self.tool.open_call();return True
        if key in ('q','Q'):self.ensure_tool().go_qth();return True
        if key=='t' and self.terrain_enabled:return self.enter_terrain()
        return self.base.key(key)
    def pointer_event(self,event,width):
        _,button,x,y,released=event
        if self.dialog:
            if button==0 and released:
                if self.dialog[0]=='Tune UV-Pro' and y==5:return self.key('b')
                if self.dialog[0]=='Map layers' and y in (2,3,4,5,6):return self.key({2:'r',3:'f',4:'a',5:'c',6:'i'}[y])
                # A menu's trailing release must not dismiss a newly opened view.
                if y==self.height-1:self.dialog=None
            return True
        if getattr(self.base,'side_overview',False) and not getattr(self.base,'full_overview',False) and x>=width-min(32,width//3) and 2<=y<self.height-1:
            if self.base.locator_hit(x,y):return self.base.pointer_event(event,width)
            if button&64 and not released:return self.key('down' if button&1 else 'up')
            if button==0 and not released:
                action=getattr(self,'_sidebar_hits',{}).get(y)
                if action=='scroll':return self.key('pagedown' if self.sidebar_scroll<self._sidebar_max_scroll else 'home')
                if action=='tabs':return self.key('l' if x<width-min(32,width//3)+12 else 'd')
                if action:return self.key(action)
            return True
        if y==self._terrain_button_row and x>=max(0,width-13) and button==0 and not released:return self.enter_terrain()
        if button==0 and not released:
            self._detail_press=(x,y,tuple(self.base.center),self.base.span,self.base.target_box.revision)
        if button&32 and self._detail_press and max(abs(x-self._detail_press[0]),abs(y-self._detail_press[1]))>1:self._detail_press=None
        result=self.tool.pointer_event(event,width) if self.terrain_active else self.base.pointer_event(event,width)
        if released and button==0:
            press=self._detail_press;self._detail_press=None
            if press and (x,y,tuple(self.base.center),self.base.span,self.base.target_box.revision)==press and not self.terrain_active:
                refs=self.entities_at(x,y)
                station=next((ref for ref in refs if ref.kind=='station'),None)
                repeater=next((ref for ref in refs if ref.kind=='repeater'),None)
                point=next((ref for ref in refs if ref.kind=='map-point' and ref.payload.get('saved_qth')),None)
                if station or repeater or point:
                    self.sidebar_scroll=0
                    self.detail_point=point.payload if point else None
                    self.detail_repeater=repeater.payload if not station else None
                    self.sidebar_tab='details';self.layers_visible=True;self.base.side_overview=True
                    if self._session_callback:self._session_callback()
        return result
    def pointer(self,x,y,width,button=0,released=False):
        from pointer_events import PointerEvent
        return self.pointer_event(PointerEvent(('mouse',button,x,y,released)),width)
    def lines(self):
        call=(self.base.context.target or {}).get('call')
        if call!=self._detail_call:
            self._detail_call=call;self.detail_repeater=None;self.detail_point=None
        provider=getattr(self,'self_calls_provider',None)
        if callable(provider):
            calls=provider() or ()
            self.internet_own=calls[0] if calls else ''
        if self.tool:self.tool.map.qth_label='QTH'+(' '+self.internet_own if self.internet_own else '')
        if self.dialog:
            from app_widgets import Canvas
            c=Canvas(self.width,self.height)
            title,rows=self.dialog
            if title=='Map layers':rows=[
                '[ R ] Repeaters: '+('shown' if getattr(self.base,'show_repeaters',True) else 'hidden'),
                '[ F ] Station filters',
                '[ A ] Own APRS call: '+(self.internet_own or 'not set'),
                '[ C ] Contact calls: '+(self.internet_calls or 'selected station'),
                '[ I ] '+(self.internet.status if self.internet else 'Internet fill off'),
                'Only listed calls + own call. No regional/all-packet feed.',
                'Positions: memory only, 30 minute expiry.',
                'Message/ACK evidence only: 24 hour expiry.',
                'Internet data never counts as RF heard.',
                'Esc / Enter / click to close']
            if self.internet_editor:rows=['Edit '+self.internet_editor[0]+':',self.internet_editor[1].text+'|','Enter saves · Esc cancels']
            if title=='Tune UV-Pro':rows=rows+[self.tuner.status,'[ B Finish listening · restore previous settings ]','Esc / Enter closes this view only']
            c.put(1,0,title)
            for y,line in enumerate(rows,2):
                if y<self.height:c.put(1,y,line)
            c.put(1,self.height-1,'[ Close · Esc ]')
            self.dialog_spans=((0,0,self.width,'toolbar'),(self.height-1,1,15,'control'))
            return c.lines()
        if self.terrain_active:
            self.ensure_tool()
            self.tool.width=self.width;self.tool.height=self.height
            return self.decorate_layers(list(self.tool.lines()),self.tool.layer())
        lines=list(self.base.lines());self._saved_pin_layer=self.base.layer()
        tool=self.ensure_tool() if self.qth_path and self.terrain_enabled else self.tool
        qth=tool.map.qth if tool and tool.qth else None
        if qth is None:qth=self._disabled_qth
        if qth and self._saved_pin_layer:
            from offline_map import Plane
            from paint import ink
            image=self.base._shown_image or self.base._image
            if image and image.projection:
                lat,lon=qth;x,y=image.projection.project(lon,lat)
                x0,y0,w,h,plane=self._saved_pin_layer
                x=round((x+.5)*w/image.width-.5);y=round((y+.5)*h/image.height-.5)
                if 0<=x<w and 0<=y<h:
                    overlay={y*w+x+i:(char,ink(255,255,255,background=(120,30,75))) for i,char in enumerate('QTH'+(' '+self.internet_own if self.internet_own else '')) if x+i<w}
                    self._saved_pin_layer=(x0,y0,w,h,Plane(plane,overlay))
        label='[ Terrain T ]' if self.terrain_enabled else ''
        self._terrain_button_row=1 if self.base.preview or self.base.full_overview or self.base.target_box.view is not None else 0
        row=self._terrain_button_row
        if label:lines[row]=lines[row][:max(0,self.width-len(label))]+label
        return self.decorate_layers(lines,self._saved_pin_layer or self.base.layer())
    def decorate_layers(self,lines,layer):
        from repeater_catalog import BANDS,COLORS
        from offline_map import Plane
        from paint import ink
        self._panel_layer=layer
        self._sidebar_hits={}
        if not getattr(self.base,'side_overview',False) or getattr(self.base,'full_overview',False) or not layer:return tuple(lines)
        x0,y0,w,h,plane=layer;overlay={};pane=min(32,self.width//3);left=max(0,w-pane)
        rect=getattr(self.base,'_locator_rect',None)
        start=(rect[1]+rect[3]+1) if rect else 3
        locator_layer=self.base.layer()
        if locator_layer and locator_layer[:4]==layer[:4]:
            for row in range(2,start):
                yy=row-y0
                if 0<=yy<h:
                    for xx in range(left,w):overlay[yy*w+xx]=locator_layer[4][yy*w+xx]
        enabled=getattr(self.base,"repeater_bands",BANDS)
        rows=[('[N] Station labels: '+('on' if getattr(self.base,'station_labels',False) else 'off'),'n',None),
              ('[P] Repeater labels: '+('on' if getattr(self.base,'repeater_labels',False) else 'off'),'p',None),
              ('[R] Repeaters: '+('shown' if getattr(self.base,'show_repeaters',True) else 'hidden'),'r',None)]
        rows += [(f'[{i+1}] [{"x" if band in enabled else " "}] {band}',str(i+1),COLORS[i]) for i,band in enumerate(BANDS)]
        rows += [('[T] Terrain / LOS: '+('on' if self.terrain_enabled else 'off'),'t',None),
                 ('[U] Maidenhead: '+getattr(self.base,'maidenhead_grid','auto'),'u',None),
                 ('[Z] Forest roads: '+('on' if getattr(getattr(self.base,'renderer',None),'forest_roads',False) else 'off'),'z',None),
                 ('[F] Station filters','f',None),
                 ('[A] Own call: '+(self.internet_own or 'not set'),'a',None),
                 ('[C] Contacts: '+(self.internet_calls or 'selected station'),'c',None),
                 ('[I] '+(self.internet.status if self.internet else 'Internet fill off'),'i',None)]
        if self.sidebar_tab=='details':
            from textwrap import wrap
            rows=[(line,None,None) for text,_,_ in self.detail_rows() for line in (wrap(text,max(1,pane-2)) or [''])]
        if self.internet_editor:
            field,editor=self.internet_editor
            rows=[('Edit '+field,None,None),(editor.text+'|',None,None),('Enter saves · Esc cancels',None,None)]
        # Compose after terrain/grid overlays; retain only the locator image above.
        blank=ink(220,220,220,background=(14,23,28))
        for row in range(start,self.height-1):
            yy=row-y0
            if 0<=yy<h:
                for xx in range(left,w):overlay[yy*w+xx]=('│' if xx==left else ' ',blank)
        capacity=max(0,self.height-start-3)
        self._sidebar_max_scroll=max(0,len(rows)-capacity)
        self.sidebar_scroll=min(self.sidebar_scroll,self._sidebar_max_scroll)
        shown=rows[self.sidebar_scroll:self.sidebar_scroll+capacity]
        heading=('[L] Layers  [D] Details','tabs',None)
        footer=(('↑↓ / wheel · '+str(self.sidebar_scroll+1)+'–'+str(min(len(rows),self.sidebar_scroll+capacity))+'/'+str(len(rows))) if self._sidebar_max_scroll else 'Drag locator to pan','scroll',None)
        visible=[(start,heading)]+list(enumerate(shown,start+1))+[(self.height-2,footer)]
        for row,(text,action,rgb) in visible:
            yy=row-y0
            if not 0<=yy<h:continue
            if row==start:
                self._sidebar_hits[row]='tabs'
            elif action:self._sidebar_hits[row]=action
            color=ink(*(rgb or (220,220,220)),background=(14,23,28))
            for xx,char in enumerate(text[:pane-2].ljust(pane-2),left+1):
                if xx<w:overlay[yy*w+xx]=(char,color)
        self._panel_layer=(x0,y0,w,h,Plane(plane,overlay))
        return tuple(lines)
    def layer(self):return None if self.dialog else self._panel_layer or (self.tool.layer() if self.terrain_active else self._saved_pin_layer or self.base.layer())
    def spans(self):return self.dialog_spans if self.dialog else self.tool.spans() if self.terrain_active else self.base.spans()
    def poll(self):
        if self.internet:
            self.base.internet_positions=self.internet.snapshot();self.base.internet_revision=self.internet.revision
        return self.tool.poll() if self.tool else self.base.poll()
    def poll_interval(self):return self.tool.poll_interval() if self.tool else self.base.poll_interval()
    def entities_at(self,x,y):
        if getattr(self.base,'side_overview',False) and not getattr(self.base,'full_overview',False) and x>=self.width-min(32,self.width//3):return ()
        refs=self.base.entities_at(x,y)
        if 2<=y<self.height-1 and not self.base.locator_hit(x,y):
            tool=self.ensure_tool();position=tool.map.position_at(x,y)
            if position and tool.map.qth:
                image=tool.map.image;layer=self.layer()
                if image and image.projection and layer:
                    px,py=image.projection.project(tool.map.qth[1],tool.map.qth[0])
                    qx=round((px+.5)*layer[2]/image.width-.5)+layer[0]
                    qy=round((py+.5)*layer[3]/image.height-.5)+layer[1]
                    label='QTH'+(' '+self.internet_own if self.internet_own else '')
                    if self.terrain_active and tool.map.mode=='path' and tool.map.points[0]==tool.map.qth:label='A '+label
                    if qy==y and qx<=x<min(self.width,qx+len(label)):
                        # The topmost saved-location label owns its complete hit area.
                        # Do not expose station labels hidden beneath it.
                        position=tool.map.qth
                        return (EntityRef('map-point',f'{position[0]:.7f},{position[1]:.7f}',payload={'position':position,'label':'QTH'+(' '+self.internet_own if self.internet_own else ''),'saved_qth':True}),)
            if position:refs=tuple(refs)+(EntityRef('map-point',f'{position[0]:.7f},{position[1]:.7f}',payload={'position':position}),)
        return refs
    def selected_entities(self):
        position=self.base.center
        return tuple(self.base.selected_entities())+(EntityRef('map-point',f'{position[0]:.7f},{position[1]:.7f}',payload={'position':position}),)
    def close(self):
        if self.internet:self.internet.close()
        if self.tool:self.tool.close()
        self.base.close()
