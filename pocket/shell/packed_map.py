"""Classic receive map under the prepared-only device policy."""
from pathlib import Path
from dataclasses import dataclass,field
from types import MappingProxyType
from concurrent.futures import CancelledError
import hashlib,importlib.util,json,math,os,time,sys,types
from offline_map import Renderer as BaseRenderer,Image
from map_palette import PALETTE_VERSION,BREAKPOINTS
from map_tiles import Archive,BoundPackReader
PACK_SET='fixed-v2-close-v2'
MANIFESTS={'detail': '4b730e494a313ff37a3f93f93e3f27150765ec99822eb525dc346c82a3e81cf8', 'overview': 'b565d1fc294f920488c9e10f81dc00f5e885231a85078199874b72b5841fb9ba', 'rainier': '10071a800ea502e69893f658213f0222c71d3cfa0a6f912e4bc12b1f0bba52a2', 'lakewood-fine': 'f579462a1cf3847e41704bfea2eaee43a5a4cd6bfbf8595d6b5e886b0afe6e1a'}
DEFAULT=Path('/usr/local/share/n810-map-packs')/PACK_SET

@dataclass(frozen=True,slots=True)
class PackedImage(Image):
    pack_status:object=None

@dataclass(frozen=True)
class ProviderSelection:
    generation:int
    reference:object
    root:str
    opener:object=field(compare=False,hash=False,repr=False)
    is_map_provider:bool=field(default=True,init=False,compare=False)

class ProviderOverview:
    """Retain selected-provider imagery instead of unrelated built-in context."""
    def __init__(self,owner):self.owner=owner
    def image(self,module,width,height):
        image=self.owner._image;selection=self.owner.renderer.provider_selection
        state=getattr(image,'pack_status',None) or {}
        if selection is not None and state.get('artifact_id')==selection.reference.artifact_id and state.get('entry_sha256')==selection.reference.entry_sha256:
            return image
        return None

class Renderer(BaseRenderer):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.loading_phase='idle'
        base=Path(os.environ.get('N810_MAP_PACKS',DEFAULT))
        self.pack_paths=tuple(base/name for name in MANIFESTS);self.archives=[];self.pack_errors=[];self.active_archive=None
        self.pack_checked=False;self.pack_state=dict(state='unopened',reason=None)
    def configure_library(self,root,opener):
        if hasattr(self,'_library_config'):raise ValueError('Map library already configured')
        if not Path(root).is_absolute() or not callable(opener):raise ValueError('Invalid map library configuration')
        self._library_config=(str(root),opener);self.provider_selection=None;self._provider_generation=0;self._provider_archive=None
    def select_provider(self,reference):
        from map_library_provider import ApprovedProviderRef
        if getattr(self,'_closed',False):raise ValueError('Map renderer closed')
        if not hasattr(self,'_library_config'):raise ValueError('Map library unavailable')
        if reference is not None and not isinstance(reference,ApprovedProviderRef):reference=ApprovedProviderRef.from_mapping(reference)
        old=self.provider_selection
        if (old.reference if old is not None else None)==reference and not self.error:return False
        self._provider_generation+=1
        if reference is not None:self._provider_lifecycle=True
        root,opener=self._library_config
        self.provider_selection=None if reference is None else ProviderSelection(self._provider_generation,reference,root,opener)
        self._wanted=None;self.error=None
        cleanup=getattr(self,'_provider_cleanup',None)
        if self.pool and (cleanup is None or cleanup.done()):self._provider_cleanup=self.pool.submit(self._retire_stale_provider)
        return True
    def _retire_stale_provider(self):
        current=getattr(self,'_provider_archive',None)
        if current is not None and current[0]!=self.provider_selection:self._retire_provider(current[0])
    def _retire_provider(self,expected=None):
        current=getattr(self,'_provider_archive',None)
        if current is not None and (expected is None or current[0]==expected):
            current[1].close();self._provider_archive=None
    def _render_provider(self,key):
        try:return self._render_provider_frame(key)
        except BaseException:
            self._retire_provider(key[-1]);raise
    def _render_provider_frame(self,key):
        selection=key[-1];reference=selection.reference
        def cancelled():return key!=self._wanted or selection!=self.provider_selection
        if cancelled():raise CancelledError()
        _,center,span,width,height,terrain,roads=key[:-1]
        if not terrain or not roads:raise ValueError('Selected map requires terrain and roads')
        # Revalidate membership and approval for each uncached worker request.
        # Cached frame presentation never calls this path.
        self._retire_provider()
        archive=None
        try:
            archive,entry=selection.opener(Path(selection.root),reference,Path(__file__).resolve().parent)
            if not getattr(archive,'bound',False):raise ValueError('Imported archive has no bound reader')
            if entry.get('artifact_id')!=reference.artifact_id:raise ValueError('Admitted artifact identity differs')
            if cancelled():raise CancelledError()
            self._provider_archive=(selection,archive,entry);archive=None
        finally:
            if archive is not None:archive.close()
        archive=self._provider_archive[1];entry=self._provider_archive[2]
        # The selected viewport helper comes from the exact admitted installed
        # source layout, never the default renderer's independent helper root.
        viewer=entry.get('viewer') or {}
        if entry.get('version')!=2 or viewer.get('layout')!='installed-selected-packet-v2':raise ValueError('Unknown admitted viewer layout')
        expected=((viewer.get('sources') or {}).get('n810-map-next.py') or {}).get('sha256')
        source_root=Path(__file__).resolve().parent/'vendor/packet-console'
        reader=BoundPackReader(source_root)
        try:raw=reader.read('n810-map-next.py',2*1024*1024)
        finally:reader.close()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Executing viewport helper differs from admission')
        helper=getattr(self,'_provider_module',None)
        if helper is None or helper[0]!=expected:
            name='_admitted_map_viewport_'+expected[:16];module=types.ModuleType(name);module.__file__=str(source_root/'n810-map-next.py');sys.modules[name]=module
            try:exec(compile(raw,module.__file__,'exec'),module.__dict__)
            except BaseException:sys.modules.pop(name,None);raise
            self._provider_module=(expected,module)
        module=self._provider_module[1]
        view=module.Viewport(center,span,width,height);candidates=[]
        requested=1000*span/max(1,width-1)
        for level in archive.levels:
            plan=archive.plan(view,allow_coarse=True,level_id=level['id'],allow_downsample=True)
            if plan is not None:
                spacing=level['spacing_m'];fine=spacing<=requested
                candidates.append((0 if fine else 1,-spacing if fine else spacing,plan))
        if not candidates:raise ValueError('Selected imported map does not cover this view')
        tier,_,plan=min(candidates,key=lambda item:item[:2])
        frame=archive.render(view,cancel=cancelled,allow_coarse=True,level_id=plan[0]['id'],allow_downsample=True)
        if cancelled():raise CancelledError()
        state=dict(state='ready',provider='imported',artifact_id=reference.artifact_id,entry_sha256=reference.entry_sha256,
                   semantic_identity=archive.manifest['identity'],selection_generation=selection.generation,
                   raw_manifest_sha256=entry.get('raw_manifest_sha256'),canonical_manifest_sha256=entry.get('canonical_manifest_sha256'),
                   executing_viewer_sha256=(entry.get('viewer') or {}).get('sha256'),
                   pack='imported',coverage=True,**archive.resolution(view,plan))
        self.pack_state=state
        return PackedImage(width,height,frame.cells,'Local overview' if key[0]=='context' else 'Imported prepared map',(),frame.seconds,view,
                           'cached-overview' if key[0]=='context' else 'regional-pack',MappingProxyType(state))
    def _open_packs(self):
        if self.pack_checked:return
        self.pack_checked=True;digests={}
        for path in self.pack_paths:
            try:
                archive=Archive(path,hot_tiles=24);m=archive.manifest;p=m['palette']
                digest=hashlib.sha256(json.dumps(m,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                if digest!=MANIFESTS[path.name]:raise ValueError('Pack manifest differs from release')
                if p['version']!=PALETTE_VERSION or p['breakpoints']!=json.loads(json.dumps(BREAKPOINTS)):raise ValueError('Palette differs')
                if hashlib.sha256(Path(__file__).with_name('map_palette.py').read_bytes()).hexdigest()!=p['sha256']:raise ValueError('Palette source differs')
                for row in m['sources']:
                    relative=Path(row['file'])
                    if relative.is_absolute() or '..' in relative.parts:raise ValueError('Source path invalid')
                    source=self.maps/Path(*relative.parts[1:]) if relative.parts[0]=='maps' else self.root/relative
                    if source not in digests:digests[source]=hashlib.sha256(source.read_bytes()).hexdigest()
                    if digests[source]!=row['sha256']:raise ValueError('Source differs: '+row['file'])
                identity=dict(sources=m['sources'],palette=p,center=m['levels'][0]['center'],span=m['levels'][0]['span'],widths=[l['width'] for l in m['levels']],terrain=m['terrain'],roads=m['roads'])
                if hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()!=m['identity']:raise ValueError('Pack identity differs')
                self.archives.append(archive)
            except (OSError,ValueError,KeyError,TypeError) as error:self.pack_errors.append(dict(pack=path.name,reason=str(error)))
    def _render(self,key):
        if key!=self._wanted:raise CancelledError()
        started=time.monotonic();self.loading_phase='pack';self._open_packs()
        if key[0]!='map':return self._missing('This candidate provides prepared 2D maps only')
        _,center,span,width,height,terrain,roads=key
        if self.module is None:
            spec=importlib.util.spec_from_file_location('packed_aprs_viewport',self.root/'n810-map-next.py')
            self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
        view=self.module.Viewport(center,span,width,height);candidates=[]
        requested=1000*span/max(1,width-1)
        for archive in self.archives:
            m=archive.manifest
            if bool(terrain)!=m['terrain'] or bool(roads)!=m['roads']:continue
            for level in archive.levels:
                plan=archive.plan(view,allow_coarse=True,level_id=level['id'],allow_downsample=True)
                if plan is None:continue
                spacing=level['spacing_m'];fine=spacing<=requested
                candidates.append((0 if fine else 1,-spacing if fine else spacing,archive,plan))
        for tier,_,archive,plan in sorted(candidates,key=lambda item:item[:2]):
            level,_,_,keys=plan;m=archive.manifest
            if self.active_archive is not archive:
                for other in self.archives:
                    if other is not archive:other.clear_hot()
                self.active_archive=archive
            resolution=archive.resolution(view,plan)
            west,south,east,north=view.bbox
            dem='DEM 10x14 m' if west>=-122.58 and south>=47.13640625 and east<=-122.48 and north<=47.25359375 else 'DEM 329x487 m' if west>=-124.8 and south>=46.2990625 and east<=-120.6 and north<=48.7009375 else 'Regional/coarse DEM'
            self.pack_state=dict(state='loading',identity=m['identity'],pack=archive.root.name,level=level['id'],tiles=len(keys),coverage=True,reason=None,dem_resolution=dem,quality='adequate grid' if tier==0 else 'resolution-limited fallback',**resolution)
            try:frame=archive.render(view,cancel=lambda:key!=self._wanted,allow_coarse=True,level_id=level['id'],allow_downsample=True)
            except CancelledError:raise
            except (OSError,ValueError,KeyError) as error:
                self.pack_errors=(self.pack_errors+[dict(pack=archive.root.name,reason=str(error))])[-4:];continue
            self.pack_state=dict(self.pack_state,state='ready',missing_tiles=0)
            image=PackedImage(width,height,frame.cells,'Fixed v2 '+archive.root.name+' · source-scale roads · nearest samples',(),time.monotonic()-started,view,'regional-pack',MappingProxyType(dict(self.pack_state)))
            self.loading_phase='ready';return image
        reason='No prepared map covers this view; choose a covered region or load more map data'
        if not self.archives:reason='Prepared map packs unavailable or incompatible'
        elif not (terrain and roads):reason='Prepared packs require terrain and roads enabled'
        return self._missing(reason)
    def _request(self,key):
        image=super()._request(key)
        if image is not None and getattr(image,'pack_status',None) is not None:self.pack_state=dict(image.pack_status)
        return image
    def _missing(self,reason):
        self.pack_state=dict(state='unavailable',reason=reason,coverage=False)
        raise ValueError(reason+'; runtime map generation is disabled')
    def loading_message(self):
        if self.loading_phase=='pack':return 'Loading prepared map tiles…'
        return super().loading_message()
    def region_status(self,image=None):
        result=super().region_status(image)
        displayed=getattr(image,'pack_status',None)
        result['pack']=dict(displayed) if displayed is not None else dict(self.pack_state) if image is None else dict(state='unknown',reason='Displayed image has no pack provenance')
        result['pack_requested']=dict(self.pack_state)
        if hasattr(self,'_library_config'):
            selection=self.provider_selection
            result['provider_selected']=dict(kind='builtin') if selection is None else dict(kind='imported',artifact_id=selection.reference.artifact_id,entry_sha256=selection.reference.entry_sha256,generation=selection.generation)
            result['provider_displayed']=dict(getattr(image,'pack_status',None) or {}) if image is not None else None
        result['packs']=dict(set=PACK_SET,provider_policy='prepared-only',generation_enabled=False,errors=list(self.pack_errors),archives=[dict(identity=a.manifest['identity'],name=a.root.name,cache=a.snapshot()) for a in self.archives])
        return result
