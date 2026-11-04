"""Typed local app actions executed by the existing desktop main-loop socket."""
import math
from runtime_codec import pack

RADIO_SUMMARY_VERSION=1
MAX_RADIO_SUMMARY_BYTES=4096


def text_summary(value,limit):
    return None if value is None else ''.join(char if char.isprintable() else ' ' for char in str(value)).encode('utf-8')[:limit].decode('utf-8','ignore')


def number_summary(value):
    return value if type(value) in (int,float) and abs(value)<=1e20 and math.isfinite(value) else None


def radio_summary(state,accepted):
    publication=state.read_job;progress=publication.get('progress');client=state.read_client
    request_id=publication.get('request_id')
    # IDs are never truncated: these are generated UUID hex by the existing client.
    if request_id is not None and (not isinstance(request_id,str) or len(request_id.encode('utf-8'))>64):raise ValueError('Radio request identity exceeds summary limit; outcome may be unknown')
    job=dict(state=text_summary(publication.get('state'),32),request_id=request_id,
             error=text_summary(publication.get('error'),256),uncertain=bool(publication.get('uncertain')),progress=None)
    if isinstance(progress,dict):
        results=progress.get('results') or {}
        job['progress']=dict(completed=number_summary(progress.get('completed')),total=number_summary(progress.get('total')),
            pending_command=number_summary(progress.get('pending_command')),started_at=number_summary(progress.get('started_at')),
            observed_at={key:number_summary(results[key].get('observed_at')) for key in ('20','10','33') if isinstance(results.get(key),dict)})
    summary=dict(summary_version=RADIO_SUMMARY_VERSION,configured=state.can_read,
                endpoint_error=text_summary(getattr(client,'endpoint_error',None),160),accepted=accepted,
                job=job,message=text_summary(state.read_message,160))
    if len(pack(summary))>MAX_RADIO_SUMMARY_BYTES:raise ValueError('Radio summary exceeds limit; outcome may be unknown')
    return summary


def dispatch(host,launch,identity,request):
    if not isinstance(request,dict):raise ValueError('Expected an object')
    command=request.get('command')
    if command=='system-status':
        if set(request)!={'command'}:raise ValueError('Unsupported command fields')
        form=host.app_forms.get('System')
        if form is None:raise ValueError('System is unavailable')
        # Observe the actual UI publication without sampling or waking sources.
        return dict(ok=True,identity=dict(identity),system=dict(form.state.result),
                    links=form.state.current.get('connectivity'),attachment=dict(form.state.attachment))
    if command in ('radio-status','radio-read','radio-check','radio-cancel'):
        if set(request)!={'command'}:raise ValueError('Unsupported command fields')
        form=host.app_forms.get('Radio Manager')
        if form is None:raise ValueError('Radio Manager is unavailable')
        accepted=None if command=='radio-status' else form.action(command[6:])
        return dict(ok=True,identity=dict(identity),radio=radio_summary(form.state,accepted))
    fields={'open-map':{'command'},'status':{'command'},'pan':{'command','direction'},
            'zoom':{'command','direction'},'set-view':{'command','latitude','longitude','span'},'pointer-trace':{'command','enabled'}}
    if command not in fields or set(request)!=fields[command]:raise ValueError('Unsupported command or fields')
    if command=='pointer-trace':
        trace=getattr(host,'pointer_trace',None)
        if trace is None:raise ValueError('Pointer diagnostics unavailable')
        return dict(ok=True,pointer_trace=trace.set_enabled(request['enabled']))
    form=host.app_forms.get('Station Map')
    if form is None:raise ValueError('Station Map is unavailable')
    try:window=host.window('Station Map')
    except (StopIteration,KeyError):raise ValueError('Station Map is unavailable') from None
    if hasattr(form,'owner'):
        if command=='status' and form.owner is None:
            return dict(ok=True,focus=host.focus,identity=dict(identity),desktop_damage_cells=len(host.damage),map=dict(opened=window.opened,visible=window.visible,created=False))
        if command=='open-map':form._ensure()
        form=form.owner
        if form is None:raise ValueError('Open Station Map first')
    if command=='open-map':launch('window:Station Map')
    if command in ('pan','zoom','set-view'):
        if hasattr(form,'reset_double_tap'):form.reset_double_tap()
        if not window.opened:raise ValueError('Open Station Map first')
        if form.filter_open:raise ValueError('Close the map filter before changing its view')
        if command in ('pan','zoom'):
            direction=request['direction']
            options={'left':'left','right':'right','up':'up','down':'down'} if command=='pan' else {'in':'+','out':'-'}
            if not isinstance(direction,str) or direction not in options:raise ValueError('Invalid direction')
            form.key(options[direction])
        else:
            values=[request[key] for key in ('latitude','longitude','span')]
            if any(type(value) not in (int,float) or not math.isfinite(value) for value in values):raise ValueError('Finite numeric view values required')
            latitude,longitude,span=values
            if not -85<=latitude<=85 or not -180<=longitude<=180 or not .25<=span<=2000:raise ValueError('View outside supported range')
            form.cancel_pointer();form.tracks.pause();form.center=(latitude,longitude);form.span=span
    engine=getattr(form.renderer,'__dict__',{}).get('engine')
    stats=getattr(engine,'__dict__',{}).get('stats',{})
    cache=stats.get('cache') if isinstance(stats,dict) else None
    image=getattr(form,'_image',None);view=getattr(form,'_image_view',None)
    provenance=getattr(form.renderer,'region_status',None)
    image_cache=provenance(image) if callable(provenance) else None
    coherent=image is not None and view==(tuple(form.center),form.span) and getattr(form.renderer,'pending',None) is None
    return dict(ok=True,focus=host.focus,identity=dict(identity),desktop_damage_cells=len(host.damage),
                map=dict(opened=window.opened,visible=host.shown(window),center=list(form.center),span=form.span,double_tap_interval_ms=form.double_tap.interval_ns//1_000_000,
                         cache=cache if cache in ('prepared','ram','cold') else None,
                         pending=getattr(form.renderer,'pending',None) is not None,
                         image_ready=image is not None,coherent=coherent,image_cache=image_cache,
                         viewport=[getattr(form,'width',None),max(1,form.height-3) if hasattr(form,'height') else None],
                         presented_view=getattr(form,'_image_view',None)))
