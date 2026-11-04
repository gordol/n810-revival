"""Opt-in bounded pointer/camera diagnostic; no worker and no gesture decisions."""
from collections import deque
from pathlib import Path
import time
from runtime_codec import pack

class PointerTrace:
    def __init__(self,path=None):
        self.output_path=Path(path) if path else Path.home()/'.local/state/current-world/pointer-trace.msgpack'
        self.path=Path(path) if path else None;self.rows=deque(maxlen=128);self.next_write=0.;self.last_view=None;self.error=None;self.input_source=None
    def set_enabled(self,enabled):
        if type(enabled) is not bool:raise ValueError('Pointer trace enabled must be boolean')
        if enabled and self.path is None:
            self.output_path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            self.path=self.output_path;self.rows.clear();self.last_view=None;self.write(True)
        elif enabled:
            self.write(True)
        elif not enabled and self.path is not None:
            self.write(True);self.path=None
        return dict(enabled=self.path is not None,path=str(self.output_path),capacity=128,error=self.error)
    @staticmethod
    def state(form):
        form=getattr(form,'owner',form)
        return dict(captured=bool(getattr(form,'pointer_captured',False)),dragged=bool(getattr(form,'_pan_dragged',False)),requested=[getattr(form,'center',None),getattr(form,'span',None)],presented=getattr(form,'_image_view',None),pending=getattr(getattr(form,'renderer',None),'pending',None) is not None)
    def record(self,host,form,event,column,row,width,route,before,handled):
        if self.path is None:return
        stamp=getattr(event,'stamp',None)
        self.rows.append(dict(kind='dispatch',processed_ns=time.monotonic_ns(),target=type(form).__name__,focus=host.focus,route=route,event=list(event),local=[column,row],width=width,source_stamp=stamp._asdict() if stamp else None,bounds=getattr(event,'bounds',None),origin=host.origin,before=before,after=self.state(form),handled=bool(handled)))
    def received(self,source,events):
        if self.path is None:return
        self.rows.append(dict(kind='ingress',processed_ns=time.monotonic_ns(),event_count=len(events),input=source.diagnostics(),
            source_events=[dict(event=list(event),stamp=getattr(event,'stamp',None)._asdict() if getattr(event,'stamp',None) else None) for event in events]))
    def sample(self,host):
        if self.path is None:return
        form=host.app_forms.get('Station Map')
        if form is None:return
        state=self.state(form);key=repr((host.focus,host.origin,state,len(host.damage)))
        if key!=self.last_view:
            self.last_view=key;self.rows.append(dict(kind='presentation',processed_ns=time.monotonic_ns(),focus=host.focus,origin=host.origin,damage_cells=len(host.damage),state=state))
    def frame(self,host,start,composed,finished,changed,computed,output_bytes):
        if self.path is None:return
        self.rows.append(dict(kind='frame',processed_ns=finished[0],
            compose_ns=composed[0]-start[0],compose_cpu_ns=composed[1]-start[1],
            output_stage_ns=finished[0]-composed[0],output_stage_cpu_ns=finished[1]-composed[1],
            changed=changed,computed=computed,output_bytes=output_bytes,damage_cells=len(host.damage),
            backend=host.render_backend,reason=host.render_reason,native_error=host.native_error,
            preview=list(host.drag[2]) if host.drag else None))

    def write(self,force=False):
        if self.path is None:return
        now=time.monotonic()
        if not force and now<self.next_write:return
        self.next_write=now+.1
        try:
            temp=self.path.with_name(self.path.name+'.tmp');temp.write_bytes(pack(dict(version=1,capacity=128,source_time_notice='Source timestamps and terminal byte-ingress times are distinct; processed_ns is diagnostic only.',events=list(self.rows),input=self.input_source() if self.input_source else None)));temp.replace(self.path)
        except OSError as error:self.error=str(error)
    def close(self):self.write(True)
