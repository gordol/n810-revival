"""One lazy app catalog for desktop windows, menu entries and lifetime owners."""
from collections import namedtuple
import importlib.util
import os
from runtime_codec import pack,unpack,atomic_write
import math
from types import MappingProxyType,ModuleType
from pathlib import Path
import re
import stat
import sys

BUILTINS=(('apps/doom-app/registration.py','descriptor'),
          ('apps/surface-renderer/registration.py','descriptor'),
          ('apps/surface-renderer/registration.py','outdoor_descriptor'),
          ('apps/landscape-lab/wildlife_registration.py','descriptor'),
          ('apps/nokia-touch-lab-v1/registration.py','descriptor'))


_ID=re.compile(r'[a-z][a-z0-9-]{0,63}\Z')

def saved_reticulum_selection(state_directory):
    """Read the explicit owner choice; configuration never activates a radio."""
    path=Path(state_directory)/'reticulum-owner.msgpack'
    legacy=not path.exists() and not path.is_symlink()
    if legacy:path=path.with_suffix('.json')
    try:fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    except FileNotFoundError:return None
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o022:
            raise ValueError('Reticulum endpoint configuration must be a private user-owned regular file')
        raw=stream.read(2049)
    if len(raw)>2048:raise ValueError('Reticulum endpoint configuration exceeds 2048 bytes')
    if legacy:
        from legacy_state import decode
        value=decode(raw)
    else:value=unpack(raw,2048)
    value=validate_reticulum_selection(value)
    if legacy:
        try:atomic_write(path.with_suffix('.msgpack'),value)
        except OSError:pass  # A read-only legacy configuration can still be imported.
    return value

def validate_reticulum_selection(value):
    if not isinstance(value,dict):raise ValueError('Invalid Reticulum owner selection')
    def absolute(key):
        item=value.get(key)
        if not isinstance(item,str) or not item or not Path(item).is_absolute() or not item.isprintable():
            raise ValueError('Reticulum '+key+' must be an absolute printable path')
    if set(value)=={'socket'}:value={'mode':'external',**value}
    if value.get('mode')=='external' and set(value)=={'mode','socket'}:
        absolute('socket');return dict(value)
    if value.get('mode')=='local' and 'carriers' in value:
        required={'mode','state','interpreter','station','carriers'}
        if not required<=set(value) or set(value)-required-{'relay'}:raise ValueError('Invalid carrier owner configuration')
        for key in ('state','interpreter'):absolute(key)
        if not isinstance(value['station'],str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}',value['station']):raise ValueError('Invalid station identity')
        if not isinstance(value['carriers'],list) or not 1<=len(value['carriers'])<=8:raise ValueError('Select one to eight carriers')
        if type(value.get('relay',False)) is not bool:raise ValueError('Relay must be boolean')
        return dict(value)
    required={'mode','state','interpreter','station','radio_id','connection','port','minimum_txpower','maximum_txpower'}
    if value.get('mode')!='local' or not required<=set(value) or set(value)-required-{'seed_profile','prepare_nokia_spp','startup_timeout'}:
        raise ValueError('Invalid Reticulum local owner configuration')
    for key in ('state','interpreter'):absolute(key)
    if 'seed_profile' in value:absolute('seed_profile')
    for key in ('station','radio_id'):
        item=value[key]
        if not isinstance(item,str) or not 1<=len(item)<=128 or not item.isprintable():
            raise ValueError('Invalid Reticulum '+key)
    if value['connection']=='hub':
        if not isinstance(value['port'],str) or not re.fullmatch(r'hub://[0-9a-f]{24}/3',value['port']):
            raise ValueError('Reticulum requires a configured hub LoRa service')
    elif value['connection']=='ble':
        if not isinstance(value['port'],str) or not re.fullmatch(r'ble://[A-Za-z0-9 _.:-]{1,80}',value['port']) or not value['port'][6:].strip():
            raise ValueError('Reticulum BLE requires an explicit device name or identifier')
    elif value['connection'] not in ('usb','bluetooth') or not isinstance(value['port'],str) or not value['port'].startswith('/dev/'):
        raise ValueError('Reticulum requires an explicit USB or Bluetooth device port')
    else:absolute('port')
    if 'prepare_nokia_spp' in value:
        if type(value['prepare_nokia_spp']) is not bool:
            raise ValueError('Reticulum prepare_nokia_spp must be a boolean')
        if value['prepare_nokia_spp'] and (value['station'],value['connection'],value['port'])!=('n810','bluetooth','/dev/rfcomm0'):
            raise ValueError('Reticulum SPP preparation requires the explicit Nokia Bluetooth device')
    if 'startup_timeout' in value:
        timeout=value['startup_timeout']
        if type(timeout) not in (int,float) or not math.isfinite(timeout) or not 5<=timeout<=120:
            raise ValueError('Reticulum startup_timeout must be a finite number from 5 to 120 seconds')
    low,high=value['minimum_txpower'],value['maximum_txpower']
    if type(low) is not int or type(high) is not int or not -128<=low<=high<=127:
        raise ValueError('Invalid Reticulum transmit power bounds')
    return dict(value)

def saved_reticulum_socket(state_directory):
    """Compatibility accessor for an explicitly saved external endpoint."""
    selection=saved_reticulum_selection(state_directory)
    return Path(selection['socket']) if selection and selection['mode']=='external' else None

def scalar(value):
    return (type(value) is bool or type(value) is int and -(1<<63)<=value<(1<<63) or type(value) is float and math.isfinite(value)
            or isinstance(value,str) and len(value)<=128 and all(c.isprintable() for c in value))

def validate_app_preferences(value):
    if not isinstance(value,dict) or len(value)>64:raise ValueError('invalid application preferences')
    for identifier,items in value.items():
        if not isinstance(identifier,str) or not _ID.fullmatch(identifier) or not isinstance(items,dict) or len(items)>32:raise ValueError('invalid application preference group')
        for key,item in items.items():
            if not isinstance(key,str) or not _ID.fullmatch(key) or not scalar(item):raise ValueError('invalid application preference value')
    if len(pack(value))>16384:raise ValueError('application preferences exceed limit')
    return {key:dict(items) for key,items in value.items()}

class Setting(namedtuple('Setting','id label kind default choices minimum maximum step',defaults=((),None,None,None,))):
    __slots__=()
    id:str
    label:str
    kind:str
    default:object
    choices:tuple
    minimum:object
    maximum:object
    step:object
    def validate(self,value):
        if self.kind=='bool':valid=type(value) is bool
        elif self.kind=='choice':valid=any(type(value) is type(choice) and value==choice for choice in self.choices)
        else:
            valid=(type(value) is int if self.kind=='int' else type(value) in (int,float))
            valid=valid and scalar(value) and self.minimum<=value<=self.maximum
        if not valid:raise ValueError('invalid setting: '+self.id)
        return value

class ServiceUse(namedtuple('ServiceUse','id required',defaults=(True,))):
    __slots__=()
    id:str
    required:bool

def setting(data):
    if not isinstance(data,dict):raise ValueError('invalid setting declaration')
    kind=data.get('kind');required={'id','label','kind','default'}
    extra={'choices'} if kind=='choice' else {'minimum','maximum','step'} if kind in ('int','float') else set()
    if kind not in ('bool','choice','int','float') or set(data)!=required|extra:raise ValueError('invalid setting declaration')
    if not isinstance(data['id'],str) or not _ID.fullmatch(data['id']):raise ValueError('invalid setting id')
    if not isinstance(data['label'],str) or not 1<=len(data['label'])<=80 or not data['label'].isprintable():raise ValueError('invalid setting label')
    if not scalar(data['default']):raise ValueError('invalid setting default')
    if kind=='choice' and not isinstance(data['choices'],(tuple,list)):raise ValueError('invalid setting choices')
    choices=tuple(data.get('choices',()))
    if kind=='choice' and (not 1<=len(choices)<=32 or any(not scalar(v) for v in choices) or len({(type(v),v) for v in choices})!=len(choices)):raise ValueError('invalid setting choices')
    if kind in ('int','float'):
        for key in ('minimum','maximum','step'):
            value=data[key]
            if not (type(value) is int if kind=='int' else type(value) in (int,float)) or not scalar(value):raise ValueError('invalid setting range')
        if data['minimum']>=data['maximum'] or data['step']<=0:raise ValueError('invalid setting range')
    result=Setting(data['id'],data['label'],kind,data['default'],choices,data.get('minimum'),data.get('maximum'),data.get('step'))
    result.validate(result.default)
    return result

def service_use(data):
    if not isinstance(data,dict) or not {'id'}<=set(data)<={'id','required'}:raise ValueError('invalid service declaration')
    if not isinstance(data['id'],str) or not _ID.fullmatch(data['id']) or type(data.get('required',True)) is not bool:raise ValueError('invalid service declaration')
    return ServiceUse(data['id'],data.get('required',True))

class AppContext(namedtuple('AppContext','registry identifier services',defaults=())):
    __slots__=()
    registry:object
    identifier:str
    services:object
    @property
    def preferences(self):return MappingProxyType(self.registry.preferences(self.identifier))
    def open_settings(self):return self.registry.open_settings(self.identifier)


class Registration(namedtuple('Registration','id title preferred_size minimum_size description category help factory directory resources resource_option settings uses commands',defaults=((),'resource_root',(),(),(),))):
    __slots__=()
    id:str
    title:str
    preferred_size:tuple
    minimum_size:tuple
    description:str
    category:str
    help:tuple
    factory:object
    directory:Path
    resources:tuple
    resource_option:str
    settings:tuple
    uses:tuple
    commands:tuple


def normalize(data,directory):
    identifier=data['id'];title=data['title'];factory=data['factory']
    if not isinstance(identifier,str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',identifier):raise ValueError('invalid app id')
    if not isinstance(title,str) or not 1<=len(title)<=80 or not title.isprintable():raise ValueError('invalid app title')
    if not callable(factory):raise ValueError('app factory must be callable')
    def size(key,default):
        value=tuple(data.get(key,default))
        if len(value)!=2 or any(type(n) is not int or not 1<=n<=4096 for n in value):raise ValueError('invalid app size')
        return value
    preferred=size('preferred_size',(80,24));minimum=size('minimum_size',(12,4))
    if any(a>b for a,b in zip(minimum,preferred)):raise ValueError('app minimum exceeds preferred size')
    resources=tuple(data.get('resources',()))
    if any(not isinstance(n,str) or Path(n).is_absolute() or '..' in Path(n).parts for n in resources):raise ValueError('invalid app resource path')
    option=data.get('resource_option','resource_root')
    if not isinstance(option,str) or not option.isidentifier():raise ValueError('invalid app resource option')
    settings=tuple(setting(item) for item in data.get('settings',()))
    uses=tuple(service_use(item) for item in data.get('uses',()))
    from app_command import normalize_commands
    commands=normalize_commands(data.get('commands',()))
    if len(settings)>32 or len({item.id for item in settings})!=len(settings):raise ValueError('duplicate or excessive settings')
    if len(uses)>16 or len({item.id for item in uses})!=len(uses):raise ValueError('duplicate or excessive service dependencies')
    if (settings or uses) and resources and option=='app_context':raise ValueError('resource option conflicts with app context')
    help_pages=tuple((str(title),tuple(lines) if not isinstance(lines,str) else (lines,)) for title,lines in data.get('help',()))
    return Registration(identifier,title,preferred,minimum,str(data.get('description','')),str(data.get('category','Applications')),help_pages,factory,Path(directory),resources,option,settings,uses,commands)


class LazyApplication:
    """One owner per desktop lifetime; closing a pane pauses, final close disposes."""
    def __init__(self,registry,entry,host):
        self.registry=registry;self.entry=entry;self.host=host;self.owner=None;self.error='';self.closed=False
        self.width,self.height=entry.preferred_size;self.saved={};self._session_callback=None;self.restore_pending=False;self._wakeup=None
    def bind_wakeup(self,callback):
        self._wakeup=callback
        if self.owner is not None and callable(getattr(self.owner,'bind_wakeup',None)):self.owner.bind_wakeup(callback)
    @property
    def form(self):return getattr(self.owner,'view',self.owner)
    @property
    def navigation_form(self):return None if self.error else getattr(self.form,'navigation_form',self.form)
    def _ensure(self):
        if self.owner is None and not self.error and not self.closed:
            try:
                self.owner=self.entry.factory(self.host,**self.registry.options(self.entry))
                if self.owner is None:raise TypeError('app factory returned no owner')
                if self._wakeup is not None and callable(getattr(self.owner,'bind_wakeup',None)):self.owner.bind_wakeup(self._wakeup)
                if self.saved and hasattr(self.form,'restore_session'):self.form.restore_session(self.saved)
                self._bind_owner_session()
            except Exception as error:self.error=str(error)
        return self.owner
    def open(self,activate=True):
        if self.closed:return False
        self.restore_pending=False
        previous=(self.host.desktop,self.host.focus,list(self.host.windows))
        owner=self._ensure()
        if activate:
            window=self.host.window(self.entry.title)
            if not window.opened:window.desktop=self.host.desktop
            self.host.activate(self.entry.title)
        self.host.window_cleanup[self.entry.title]=self.on_close
        if owner is not None:
            try:
                if hasattr(owner,'open'):owner.open()
            except Exception as error:self.error=str(error)
        if not activate:
            self.host.desktop,self.host.focus,self.host.windows=previous
        return owner is not None and not self.error
    def set_active(self,opened):
        window=self.host.window(self.entry.title)
        if opened and self.owner is None and not self.error and not self.restore_pending and self.host.shown(window) and not window.rolled:self.open(activate=False)
        if self.owner is not None and hasattr(self.owner,'set_active'):self.owner.set_active(opened)
    def poll_interval(self):
        if self.error:return None
        if self.owner is not None and hasattr(self.owner,'poll_interval'):return self.owner.poll_interval()
        return None
    def presentation_interval(self):
        form=self.form
        method=getattr(form,'presentation_interval',None) if not self.error else None
        return method() if method is not None else None
    def readiness_sources(self):
        if self.error or self.owner is None:return ()
        method=getattr(self.owner,'readiness_sources',None)
        return method() if method is not None else ()
    def readiness_error(self,error):self.error=str(error)
    def poll(self):
        if self.owner is not None and not self.error:
            form=self.form
            if hasattr(form,'width'):form.width=self.width
            if hasattr(form,'height'):form.height=self.height
            try:
                if hasattr(self.owner,'poll'):self.owner.poll()
            except Exception as error:self.error=str(error)
    def key(self,key):
        if self.error:
            if key.lower()=='r':
                if self.owner is not None and hasattr(self.owner,'close'):self.owner.close()
                self.owner=None;self.error='';self.open();return True
            return key not in ('?','help') and len(key)==1 and key.isprintable()
        handled=bool(self.form.key(key)) if self.form is not None and hasattr(self.form,'key') else False
        # App focus owns ordinary typing. Unknown letters must not become WM
        # commands; the existing WM escape is handled before app dispatch.
        return handled or key not in ('?','help') and len(key)==1 and key.isprintable()
    def pointer(self,*args,**kwargs):
        return self.form.pointer(*args,**kwargs) if self.form is not None and hasattr(self.form,'pointer') else False
    def pointer_event(self,event,width):
        if self.form is None:return False
        from pointer_events import deliver_pointer
        return deliver_pointer(self.form,event,event[2],event[3],width)
    def selected_entities(self):
        method=getattr(self.form,'selected_entities',None) if not self.error else None
        return method() if callable(method) else ()
    def entities_at(self,column,row):
        method=getattr(self.form,'entities_at',None) if not self.error else None
        return method(column,row) if callable(method) else ()
    @property
    def key_event_supported(self):
        return not self.error and self.form is not None and callable(getattr(self.form,'key_event',None)) and callable(getattr(self.form,'cancel_keys',None))
    def key_event(self,key,kind,now):
        if self.key_event_supported:return self.form.key_event(key,kind,now)
        return False
    def cancel_keys(self,now=None):
        if self.form is not None and hasattr(self.form,'cancel_keys'):self.form.cancel_keys(now)
    @property
    def pointer_captured(self):return bool(getattr(self.form,'pointer_captured',False))
    def cancel_pointer(self):
        if self.form is not None and hasattr(self.form,'cancel_pointer'):self.form.cancel_pointer()
    def lines(self):
        if self.error:return (self.entry.title+' could not open.',self.error[:max(1,self.width)],'', 'R: retry   ?: help')
        if self.restore_pending:return ('Restoring '+self.entry.title+'…',)
        if self.form is not None:
            if hasattr(self.form,'width'):self.form.width=self.width
            if hasattr(self.form,'height'):self.form.height=self.height
            return self.form.lines()
        return ('Open '+self.entry.title+' from Applications to start it.',)
    def spans(self):return self.form.spans() if self.form is not None and hasattr(self.form,'spans') and not self.error else ()
    def layer(self):
        if self.error:return None
        form=self.form
        if form is None:return None
        value=getattr(form,'layer',None)
        if value is not None:return value() if callable(value) else value
        return self.host.window(self.entry.title).layer if getattr(form,'layer_only',False) else None
    def help_pages(self):
        if self.form is not None and hasattr(self.form,'help_pages'):return self.form.help_pages()
        return self.entry.help
    def bind_session(self,callback):
        self._session_callback=callback
        if self.owner is not None:self._bind_owner_session()
    def _bind_owner_session(self):
        form=self.form
        if form is None or not hasattr(form,'session_state'):return
        if not callable(getattr(form,'bind_session',None)):
            raise TypeError('Persisted app requires change notifications: '+self.entry.title)
        form.bind_session(self._session_callback)
        if self._session_callback and form.session_state()!=self.saved:self._session_callback()
    def session_state(self):return self.form.session_state() if self.form is not None and hasattr(self.form,'session_state') else self.saved
    def restore_session(self,state):self.saved=state if isinstance(state,dict) else {}
    def presented(self,now=None):
        if self.owner is not None and hasattr(self.owner,'presented'):self.owner.presented(now)
    def on_close(self):
        self.cancel_keys()
        if self.owner is not None:
            if getattr(self.owner,'dispose_on_close',False):
                owner,self.owner=self.owner,None
                owner.close()
                return
            if hasattr(self.owner,'on_close'):self.owner.on_close()
            elif hasattr(self.owner,'set_active'):self.owner.set_active(False)
    def close(self):
        if self.closed:return
        self.cancel_keys()
        if self.owner is not None and hasattr(self.owner,'close'):self.owner.close()
        self.closed=True


class Registry:
    def __init__(self,root=None,resource_roots=(),providers=None):
        self.root=Path(root) if root else Path(__file__).resolve().parent
        self.resource_roots=tuple(Path(p) for p in resource_roots)+(self.root,)
        self.entries={};self.by_title={};self.forms={};self.errors=[];self.providers=dict(providers or {});self.host=None;self.settings_opener=None
    def configure_meshcore(self,socket_path=None,local_state=None,local_options=None,register=False,availability_only=False):
        # Reuse the existing private package and binary provider implementation.
        self.configure_reticulum(register=False)
        import importlib
        directory=self.root/'vendor/apps/domains/reticulum'
        package='_pocket_reticulum_'+str(abs(hash(str(directory.resolve()))))
        module=importlib.import_module(package+'.provider')
        if socket_path is not None:return module.Provider(socket_path,transport=module.SocketTransport(str(socket_path),availability_only=availability_only))
        return module.MeshCoreProvider(local_state,availability_only=availability_only,**(local_options or {}))

    def configure_reticulum(self,socket_path=None,local_state=None,local_options=None,register=True,availability_only=False):
        """Register the app and connect only to an explicitly selected owner.

        Domain imports use a private package namespace, with no sys.path change
        or global aliases for generic names such as owner and profiles.
        Existing/forwarded sockets never start a local service.
        The caller owns the returned Provider's desktop lifetime.
        """
        if socket_path is not None and local_state is not None:raise ValueError('Select one Reticulum owner mode')
        options={}
        if local_options is not None:
            if local_state is None:raise ValueError('Local Reticulum options require local state')
            selection=validate_reticulum_selection({'mode':'local','state':str(local_state),**local_options})
            options={key:value for key,value in selection.items() if key not in ('mode','state')}
        candidates=(self.root/'vendor/apps/domains/reticulum',)
        directory=next((p for p in candidates if (p/'manager.py').is_file() and (p/'provider.py').is_file()),None)
        if directory is None:raise ImportError('Reticulum domain is not installed')
        name='_pocket_reticulum_'+str(abs(hash(str(directory.resolve()))))
        if name not in sys.modules:
            package=ModuleType(name);package.__path__=[str(directory)];package.__package__=name
            sys.modules[name]=package
        import importlib
        manager=importlib.import_module(name+'.manager') if register else None
        if register and 'rnode-bluetooth' not in self.entries:
            from rnode_ble_view import descriptor as bluetooth_descriptor
            self.register(bluetooth_descriptor(), self.root)
        if socket_path is None and local_state is None:
            if register:self.register(manager.descriptor(),directory)
            return None
        provider_module=importlib.import_module(name+'.provider')
        factory=provider_module.CarrierProvider if 'carriers' in options else provider_module.LocalProvider
        provider=(factory(Path(local_state).expanduser(),availability_only=availability_only,**options) if local_state is not None
                  else provider_module.Provider(Path(socket_path).expanduser(),transport=provider_module.SocketTransport(str(Path(socket_path).expanduser()),availability_only=availability_only)))
        try:
            if register:
                self.register(manager.descriptor(),directory)
                self.providers['reticulum']=provider
        except BaseException:
            provider.close();raise
        return provider
    def register(self,data,directory=None):
        entry=normalize(data,directory or self.root)
        if entry.id in self.entries or entry.title in self.by_title:raise ValueError('duplicate app registration')
        self.entries[entry.id]=entry;self.by_title[entry.title]=entry.id;return entry
    def discover(self,definitions=BUILTINS):
        modules={}
        for relative,method in definitions:
            source=self.root/relative
            if not source.is_file():continue
            try:
                if source not in modules:
                    name='_desktop_app_registration_'+re.sub('[^a-zA-Z0-9_]','_',relative)
                    spec=importlib.util.spec_from_file_location(name,source);module=importlib.util.module_from_spec(spec);sys.modules[name]=module;spec.loader.exec_module(module);modules[source]=module
                module=modules[source]
                if hasattr(module,method):self.register(getattr(module,method)(),source.parent)
            except (OSError,ImportError,ValueError,KeyError,TypeError) as error:self.errors.append((relative,str(error)))
        return self
    def preferences(self,identifier):
        entry=self.entries[identifier];saved=getattr(self.host,'app_preferences',{}).get(identifier,{})
        result={}
        for item in entry.settings:
            try:result[item.id]=item.validate(saved.get(item.id,item.default))
            except ValueError:result[item.id]=item.default
        return result

    def set_setting(self,identifier,key,value):
        if self.host is None:raise ValueError('Registry is not bound to a desktop')
        entry=self.entries[identifier];item=next((item for item in entry.settings if item.id==key),None)
        if item is None:raise ValueError('unknown application setting')
        item.validate(value)
        if self.preferences(identifier)[key]==value:return False
        values={name:dict(row) for name,row in self.host.app_preferences.items()}
        values.setdefault(identifier,{})[key]=value
        self.host.set_preference('app_preferences',validate_app_preferences(values))
        form=self.forms.get(entry.title)
        if form is not None and form.owner is not None:
            notify=getattr(form.owner,'preferences_changed',None)
            if callable(notify):
                try:notify(self.preferences(identifier))
                except Exception as error:form.error='Settings could not apply: '+str(error)
        return True

    def open_service(self,identifier):
        from service_catalog import OWNER_IDS
        if identifier not in (*OWNER_IDS,'receive','system','connections') or 'connections' not in self.entries:return False
        self.open('connections')
        form=self.forms[self.entries['connections'].title].owner
        if form is None:return False
        return form.select_service(identifier if identifier in OWNER_IDS else 'receive')

    def open_settings(self,identifier):
        entry=self.entries[identifier]
        if not entry.settings and not entry.uses:raise ValueError('Application has no settings page')
        if self.settings_opener is None:raise RuntimeError('Settings UI is unavailable')
        return self.settings_opener('App: '+entry.title)

    def settings_categories(self):
        from controls import Toggle,Choice,Slider
        result=[]
        for entry in self.entries.values():
            if not entry.settings and not entry.uses:continue
            rows=[]
            for item in entry.settings:
                get=lambda entry=entry,item=item:self.preferences(entry.id)[item.id]
                set=lambda value,entry=entry,item=item:self.set_setting(entry.id,item.id,value)
                control=Toggle(item.label,get,set) if item.kind=='bool' else Choice(item.label,get,set,item.choices) if item.kind=='choice' else Slider(item.label,get,set,item.minimum,item.maximum,item.step)
                rows.append(control.row())
            pages=[('Preferences',rows)] if rows else []
            if entry.uses:
                dependencies=[(use.id+(' (required)' if use.required else ' (optional)'),lambda use=use:getattr(self.providers.get(use.id),'label','Provided') if self.providers.get(use.id) is not None else 'Unavailable',lambda direction,use=use:self.open_service(use.id)) for use in entry.uses]
                pages.append(('Services',dependencies))
            result.append(('App: '+entry.title,('  =  ',' [ ] ','  =  '),entry.description,pages))
        return tuple(result)

    def options(self,entry):
        result={}
        if entry.resources:
            relative=entry.directory.relative_to(self.root)
            candidates=tuple(root/relative for root in self.resource_roots)
            directory=next((p for p in candidates if all((p/name).is_file() for name in entry.resources)),entry.directory)
            result[entry.resource_option]=directory
        if entry.settings or entry.uses:
            missing=[use.id for use in entry.uses if use.required and self.providers.get(use.id) is None]
            if missing:raise RuntimeError('Service unavailable: '+', '.join(missing))
            result['app_context']=AppContext(self,entry.id,MappingProxyType({use.id:self.providers.get(use.id) for use in entry.uses}))
        return result
    def windows(self,width,height):
        from core import Window
        return [Window(e.title,max(0,(width-min(width,e.preferred_size[0]))//2),min(2,max(0,height-4)),min(width,e.preferred_size[0]),min(height-1,e.preferred_size[1]),visible=False,opened=False) for e in self.entries.values()]
    def bind(self,host):
        self.host=host
        self.forms={entry.title:LazyApplication(self,entry,host) for entry in self.entries.values()}
        host.app_forms.update(self.forms)
        host.minimum_sizes.update({e.title:e.minimum_size for e in self.entries.values()})
    def menu_entries(self):return tuple((e.title,'app:'+e.id) for e in self.entries.values())
    def open(self,identifier):return self.forms[self.entries[identifier].title].open()
    def snapshot(self):
        result={}
        for name,form in self.forms.items():
            window=form.host.window(name);stats=getattr(form.owner,'stats',{})
            result[form.entry.id]=dict(title=name,created=form.owner is not None,error=form.error,
                opened=window.opened,surface_cells=len(window.layer[4]) if window.layer else 0,
                stats={str(k):v for k,v in stats.items() if isinstance(v,(int,float,bool))} if isinstance(stats,dict) else {})
        return result


def discover():
    resources=tuple(p for p in os.environ.get('CURRENT_WORLD_RESOURCES','').split(os.pathsep) if p)
    return Registry(resource_roots=resources).discover()


def instantiated_forms(forms):
    """Snapshot existing owners for readiness/deadlines, including hidden ones.

    Uncreated exact lazy wrappers return no sources or intervals. Subclasses
    may implement their own lifecycle and must retain the generic path.
    Recompute after presentation callbacks so a newly created owner is included.
    """
    return tuple((name,form) for name,form in forms.items()
                 if type(form) is not LazyApplication or form.owner is not None)
