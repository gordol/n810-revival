"""Connection controls using the shared application widgets."""
from app_widgets import Canvas,TextInput
from service_catalog import OWNER_SERVICES
from app_commands import button as command_button, label as command_label


class ConnectionsView:
    keybinding_scope = 'connections'
    def __init__(self, host, *, app_context):
        self.service = app_context.services['connections']
        self.host=host
        self.registry=getattr(app_context,'registry',None)
        self.action_error=''
        self.width, self.height = 76, 20
        self.address = self.service.suggested_address
        self._session_callback = None
        self.selected_service = 'receive'
        self.addresses = {}
        self.editing = False
        self._hits = []
        self._spans = ()
        self.peer_setup = None

    @property
    def navigation_form(self):
        return None if self.peer_setup is not None else self

    def bind_session(self, callback):
        self._session_callback = callback

    def session_state(self):
        state = dict(address=self.address if self.selected_service == 'receive' else self.addresses.get('receive', ''))
        if getattr(self.service, 'reticulum', None) is not None:
            state['reticulum_address'] = self.address if self.selected_service == 'reticulum' else self.addresses.get('reticulum', '')
        if getattr(self.service,'meshcore',None) is not None:
            state['meshcore_address']=self.address if self.selected_service=='meshcore' else self.addresses.get('meshcore','')
        return state

    def restore_session(self, state):
        value = state.get('address') if isinstance(state, dict) else None
        if not self.service.suggested_address and isinstance(value, str) and len(value) <= 240 and all(c.isprintable() for c in value):
            self.address = value

        value = state.get('reticulum_address') if isinstance(state, dict) else None
        if isinstance(value, str) and len(value) <= 240 and all(c.isprintable() for c in value):
            self.addresses['reticulum'] = value
        value=state.get('meshcore_address') if isinstance(state,dict) else None
        if isinstance(value,str) and len(value)<=240 and all(c.isprintable() for c in value):self.addresses['meshcore']=value

    @property
    def selection(self):
        return self.service if self.selected_service == 'receive' else getattr(self.service,self.selected_service)

    def bind_wakeup(self, callback):
        self.service._view_wake = callback

    def readiness_sources(self):
        control = self.service.control
        sources = ((control.readable, control.ready),) if control is not None else ()
        reticulum = getattr(self.service, 'reticulum', None)
        if reticulum is not None: sources += reticulum.readiness_sources(reticulum.drain)
        meshcore=getattr(self.service,'meshcore',None)
        if meshcore is not None:sources+=meshcore.readiness_sources(meshcore.drain)
        return sources

    navigation_tab_row=0
    @property
    def service_choices(self):return ('receive',)+tuple(s.id for s in OWNER_SERVICES if getattr(self.service,s.id,None) is not None)
    @property
    def tabs(self):return tuple({'receive':'Device','reticulum':'Reticulum','meshcore':'MeshCore'}[name] for name in self.service_choices)
    @property
    def tab(self):return self.service_choices.index(self.selected_service)
    @tab.setter
    def tab(self,value):self.select_service(self.service_choices[value])

    def connection_actions(self):
        if self.selected_service=='receive':
            actions=(('This device','l'),('Connect SSH','c'),('Connect peer','p'),('Socket folder','s'),('Disconnect','d'))
        else:
            actions=[('Local owner','l'),('Owner socket','s'),('Disconnect','d')]
            if self.selected_service=='reticulum':
                actions += [('Direct peer setup','p'),('Verified peer','c'),('RNode connections','h')]
        return [(command_button(self.keybinding_scope,key,title),key) for title,key in actions]

    def navigation_targets(self):
        from native_navigation import Target
        actions=[('i','System'),('f','Radio Feed'),('r','Reticulum'),('m','Messages')] if self.selected_service=='receive' else [('r','Reticulum')] if self.selected_service=='reticulum' else [('m','Messages')]
        actions += [(key,label.strip('[]')) for label,key in self.connection_actions()]+[('e','Address')]
        return [Target('tabs','Tabs','tabs')]+[Target('action:'+key,label,'action',key) for key,label in actions]

    def select_service(self,name):
        if name!='receive' and getattr(self.service,name,None) is None:return False
        self.addresses[self.selected_service]=self.address
        self.selected_service=name
        self.address=self.addresses.get(name,'')
        self.action_error=''
        return True

    def open_app(self,title):
        try:
            if self.registry is not None and title in self.registry.by_title:
                self.registry.open(self.registry.by_title[title])
            elif self.host is not None:self.host.activate(title)
            else:return False
            self.action_error=''
            return True
        except (KeyError,ValueError,StopIteration) as error:
            self.action_error=title+' is not available in this shell'
            return False

    def finish_peer_setup(self,folder=None):
        self.peer_setup=None
        if folder is not None:
            self.address=folder
            self.addresses['reticulum']=folder
            if callable(self._session_callback):self._session_callback()

    def navigation_end_input(self):
        if not self.editing:return False
        self.address=self._address_input.text
        self.editing=False
        if self.address!=self._address_before and callable(self._session_callback):self._session_callback()
        return True

    def key(self, key):
        if self.peer_setup is not None:return self.peer_setup.key(key)
        if self.editing:
            if key in ('\x1b','escape'):
                self.address=self._address_before;self.editing=False
            elif key in ('\r','\n','enter'):
                self.navigation_end_input()
            else:
                self._address_input.key(key);self.address=self._address_input.text
            return True
        if key == 'p' and self.selected_service == 'reticulum':
            from native_peer_setup import PeerSetup
            self.peer_setup=PeerSetup(self.selection,self.finish_peer_setup)
            return True
        if key == 'h' and self.selected_service == 'reticulum':
            return self.open_app('RNode connections')
        if key in ('i','f','r','m'):
            return self.open_app({'i':'System','f':'Radio Feed','r':'Reticulum','m':'Messages'}[key])
        if key in ('v','o','b'):
            return self.select_service({'v':'receive','o':'reticulum','b':'meshcore'}[key])
        if key in ('\t','backtab'):
            from native_navigation import native_key
            return native_key(self,key)
        if key == 't':
            choices=('receive',)+tuple(s.id for s in OWNER_SERVICES if getattr(self.service,s.id,None) is not None)
            return self.select_service(choices[(choices.index(self.selected_service)+1)%len(choices)])
        elif key == 'e':
            self._address_before=self.address
            self._address_input=TextInput(self.address,limit=240)
            self.editing=True
        elif key == 'l': self.selection.connect('local', self.address) if self.selected_service != 'receive' else self.selection.connect('local')
        elif key == 's': self.selection.connect('socket', self.address)
        elif key == 'p' and self.selected_service == 'receive': self.selection.connect('peer',self.address)
        elif key == 'c' and self.selected_service == 'receive': self.selection.connect('ssh', self.address)
        elif key == 'c' and self.selected_service == 'reticulum': self.selection.connect('peer', self.address)
        elif key == 'd': self.selection.disconnect()
        else: return False
        return True

    def pointer(self, column, row, width=None, button=0, released=False):
        if self.peer_setup is not None:return self.peer_setup.pointer(column,row,width,button,released)
        if button != 0 or released: return False
        for x, y, width, key in self._hits:
            if y == row and x <= column < x + width:
                return self.key(key)
        return False

    def lines(self):
        if self.peer_setup is not None:
            result=self.peer_setup.lines(self.width,self.height);self._spans=self.peer_setup._spans;return result
        canvas=Canvas(self.width,self.height);self._hits=[]
        def button(x,y,label,key,limit=None):
            visible=min(len(label),max(0,self.width-x),self.width if limit is None else limit)
            canvas.put(x,y,label,visible);canvas.role(x,y,visible,'control')
            if visible:self._hits.append((x,y,visible,key))
        x=0
        for name,label,key in (('receive','Device','v'),('reticulum','Reticulum','o'),('meshcore','MeshCore','b')):
            if name!='receive' and getattr(self.service,name,None) is None:continue
            text='['+('*' if self.selected_service==name else '')+label+']'
            button(x,0,text,key);x+=len(text)+1
        state=self.selection
        source=getattr(getattr(state,'source',None),'receive',getattr(state,'source',None))
        publication=state.snapshot() if self.selected_service!='receive' else getattr(source,'state',{})
        device_source=getattr(state,'source',None)
        if self.selected_service=='receive' and hasattr(device_source,'catalogue_provider'):
            publication=device_source.catalogue_provider.snapshot()
        local_device=self.selected_service=='receive' and getattr(device_source,'local_device',False)
        if local_device:publication=dict(owner_online=not device_source.closed)
        phase='Attached' if publication.get('online') or publication.get('owner_online') else 'Waiting'
        canvas.put(0,1,'Connecting…' if state.busy else phase+' · '+state.label if getattr(state,'source',getattr(state,'provider',None)) is not None else state.label)
        error=self.action_error or state.error or publication.get('error') or ''
        if state.error and self.selected_service=='receive' and (getattr(state,'_intent',None) or (None,))[0]=='ssh':
            error=('SSH timed out' if 'timed out' in state.error.lower() or 'banner exchange' in state.error.lower() or 'timeout' in state.error.lower() else 'SSH connection failed')+(' · retrying' if getattr(state,'_retry_failed',False) else ' · '+command_label(self.keybinding_scope,'c')+' retry')+' · ? details'
        canvas.put(0,2,' '.join(error.split()))
        if error:canvas.role(0,2,self.width,'warning')
        if self.selected_service=='receive':
            catalogue=getattr(device_source,'catalogue',{})
            services={item['id']:item for item in catalogue.get('services',[])}
            for row,name,title,key in ((3,'system','System','i'),(4,'receive','Feed','f'),(5,'reticulum','Reticulum','r'),(6,'meshcore','MeshCore','m')):
                owner=self.service.label;item=services.get(name,{})
                status=item.get('state') or ('ready' if item.get('available') else 'unavailable')
                if name in ('reticulum','meshcore'):
                    selected=getattr(self.service,name,None)
                    if selected is not None:
                        owner=getattr(selected,'label','No owner selected')
                        if selected.snapshot().get('owner_online'):status='connected'
                        elif getattr(selected,'busy',False):status='connecting'
                elif name=='system':
                    local=getattr(device_source,'system',{})
                    if publication.get('owner_online') or isinstance(local,dict) and local.get('system',{}).get('source'):status='connected'
                elif getattr(source,'state',{}).get('online'):status='connected'
                label=command_button(self.keybinding_scope,key,title+': '+status)
                button(0,row,label,key)
                canvas.put(len(label)+1,row,owner)

        else:
            title=next(s.app for s in OWNER_SERVICES if s.id==self.selected_service)
            key='r' if self.selected_service=='reticulum' else 'm'
            button(0,3,command_button(self.keybinding_scope,key,'Open '+title),key)
            canvas.put(0,4,'Owner: '+state.label)
            canvas.put(0,5,'Select the service owner below.')
            canvas.put(0,6,'Radio activation is in its app.')

        # Two columns keep all actions reachable on the Nokia's compact panes.
        for index,(label,key) in enumerate(self.connection_actions()):
            x=(index%2)*(self.width//2)
            button(x,7+index//2,label,key,limit=self.width//2-1 if index%2==0 else self.width-x)
        button(0,11,('> ' if self.editing else command_button(self.keybinding_scope,'e','Address')+' ')+self.address,'e')
        if self.editing:self._address_input.paint(canvas,0,11,self.width)
        hint='SSH: user@host · Peer: verified identity' if self.selected_service=='receive' else 'Local: configuration folder · Socket: owner.sock'
        canvas.put(0,13,hint)
        self._spans=tuple(canvas.spans)
        return canvas.lines()

    def spans(self): return self._spans

    def help_pages(self):
        error=self.action_error or self.selection.error
        diagnostics=(('Connection error',tuple(error.splitlines())),) if error else ()
        label=lambda event:command_label(self.keybinding_scope,event)
        from keybindings import current
        bindings=current()
        key=lambda action:bindings.label('navigation',action)
        return diagnostics+(('Connections', (
                f"{key('focus.next')} / {key('focus.previous')}: move focus. {key('select.left')} / {key('select.right')} on the tab strip: switch tabs.",
                f"{label('i')}: open System. {label('f')}: open Radio Feed. {label('r')}: open Reticulum. {label('m')}: open Messages.",
                'Each service row shows its selected owner; opening it does not connect or transmit.',
                f"{label('l')}: use services on this device.",
                f"{label('e')}: enter an SSH host or a folder containing aprs.sock and replay.sock.",
                f"{label('c')}: attach device services through SSH: feed, System, Reticulum and MeshCore when configured. {label('s')}: attach receive sockets.",
                f"{label('p')}: attach a verified Reticulum peer using its full identity in Address.",
                'The peer must grant Device read in Reticulum → Data; other owners require their own grants.',
                f"{label('d')}: detach or cancel a pending attachment.",
                'Local services attach after startup. Remote connections remain explicit.',
                'SSH uses your configured host keys. Disconnect detaches this shell;',
                'the reusable SSH tunnel and independent service owners may remain running.')),)



def descriptor():
    return dict(id='connections', title='Connections', preferred_size=(76, 21),
                minimum_size=(40, 16), factory=ConnectionsView,
                uses=({'id': 'connections'},), category='System')
