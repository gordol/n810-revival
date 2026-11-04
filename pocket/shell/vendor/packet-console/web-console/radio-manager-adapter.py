"""Portable, read-only Radio Manager adapter for retained connector responses."""
import importlib.util
import json
from pathlib import Path
import sys
import time

spec=importlib.util.spec_from_file_location('radio_model',Path(__file__).with_name('radio-read-model.py'))
model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)


def data(envelope):
    envelope=model.obj(envelope)
    return model.obj(envelope['data']) if 'data' in envelope else envelope


def seconds(value):
    if model.number(value):return value
    if isinstance(value,str):
        try:
            import datetime
            return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
        except ValueError:pass
    return None


def observation(state,label,stamp,now):
    stamp=seconds(stamp)
    return dict(state=state,label=label,observed_at=stamp,age_seconds=model.age(stamp,now))


def unique(values,key,wanted):
    matches=[row for row in values if row.get(key)==wanted and type(row.get(key)) is type(wanted)]
    if len(matches)!=1:raise ValueError('Selected identity is missing or ambiguous: '+key)
    return matches[0]


def compare(normalized,selection):
    """Resolve explicit identities against normalized retained catalog only."""
    s=model.obj(selection)
    for key in ('bank_index','memory_index'):
        if model.integer(s.get(key)) is None:raise ValueError('Explicit integer '+key+' required')
    for key in ('preset_bank_id','preset_channel_id'):
        if not isinstance(s.get(key),str) or not s[key]:raise ValueError('Explicit '+key+' required')
    bank=unique(normalized['snapshot']['banks'],'index',s['bank_index'])
    native=unique(bank['channels'],'index',s['memory_index'])
    saved=unique(normalized['presets']['banks'],'id',s['preset_bank_id'])
    draft=unique(saved['channels'],'id',s['preset_channel_id'])
    return model.compare_channels(native,draft)


def adapt(payload,now=None,*,catalog_model=None,owner_context=None):
    p=model.obj(payload);now=time.time() if now is None else now
    catalog=data(p.get('catalog'));live=data(p.get('live'))
    normalized=model.normalize_radio(catalog,live.get('radio_live'),now,catalog_model=catalog_model,owner_context=owner_context)
    # Normalized-only captures cannot recover fresh raw radio observations.
    if not live.get('radio_live') and model.obj(live.get('radio_model')).get('live'):
        normalized['live']=age_normalized(live['radio_model']['live'],live.get('captured'),now,owner_context=owner_context)
    connector=model.obj(p.get('connector'));ssh=model.obj(connector.get('ssh'))
    ssh_age=model.age(seconds(ssh.get('observed_at')),now)
    ssh_state='unknown' if model.flag(ssh.get('success')) is None or ssh_age is None else 'stale' if ssh_age>30 else 'recent' if ssh['success'] is True else 'failed'
    ssh_view=observation(ssh_state,{'unknown':'SSH unverified','stale':'SSH observation stale','recent':'SSH read succeeded','failed':'SSH read failed'}[ssh_state],ssh.get('observed_at'),now)
    feed_age=model.age(seconds(live.get('captured')),now);history=live.get('history_source')
    live_error=model.obj(p.get('live')).get('error')
    subscribed=model.flag(live.get('receive_subscription'));connected=model.flag(live.get('receive_connected'))
    transport_known=connected is False or subscribed is True and connected is True
    if transport_known:
        # Connectivity is a current source fact, not the time of the last packet.
        feed_state='recent' if connected else 'unavailable'
        feed_label='Feed transport connected' if connected else 'Feed transport disconnected'
    else:
        feed_state='unknown' if not isinstance(history,str) or feed_age is None else 'stale' if feed_age>30 or live_error else 'recent' if history.startswith('feed') else 'unavailable'
        feed_label={'unknown':'Feed unverified','stale':'Feed observation stale','recent':'Feed snapshot received','unavailable':'Feed unavailable / saved history'}[feed_state]
    feed_view=observation(feed_state,feed_label,live.get('captured'),now)
    feed_view.update(transport_current_known=transport_known,transport_connected=connected,
                     transport_subscribed=subscribed)
    radio=normalized['live'];state=radio['mode']
    radio['indicators']=model.status_indicators(radio['sections'])
    hb=radio.get('heartbeat_age_seconds');link=dict(model.obj(radio.get('link')))
    link_state=link.get('state','unknown')
    link['label']={'reported_up':'Bluetooth link reported up','reported_down':'Bluetooth link last reported disconnected','unknown':'Bluetooth current link unknown'}.get(link_state,'Bluetooth current link unknown')
    labels={'live':'Radio recent','paused':'Detailed radio telemetry paused','stale':'Radio status stale','owner_unavailable':'Radio observation stale','disconnected':'Radio disconnected','waiting':'Radio waiting','unknown':'Radio status unknown','unavailable':'Radio unavailable'}
    radio_label='Radio connected; detailed telemetry paused' if state=='paused' and link_state=='reported_up' else labels.get(state,'Radio status unknown')
    if state=='disconnected' and not link.get('current_known'):radio_label='Radio last reported disconnected; observation '+link.get('freshness','unknown')
    result=dict(version=1,model=normalized,statusbar=dict(ssh=ssh_view,feed=feed_view,
                radio=dict(state=state,label=radio_label,link=link,
                           sections=radio['sections'],active=radio['active'],indicators=radio['indicators'])),
                capabilities=dict(browse=True,compare=True,hardware_commands=False,telemetry_control=False,
                                  preset_write=False,backup_read=True),
                sources=dict(catalog_captured=catalog.get('captured'),live_captured=live.get('captured')))
    deadlines=[]
    for view in (ssh_view,feed_view):
        if view is feed_view and transport_known:continue
        if view['state'] in ('recent','failed') and view['observed_at'] is not None:
            deadlines.append(view['observed_at']+30.001)
    if model.number(hb) and hb<=15:deadlines.append(now+15-hb+.001)
    for name,section in radio['sections'].items():
        limit={'status':20,'settings':45,'beacon':75}.get(name)
        section_age=section.get('age_seconds')
        if section.get('state')=='fresh' and limit is not None and model.number(section_age):
            deadlines.append(now+limit-section_age+.001)
    result['next_invalidation_at']=min((d for d in deadlines if d>now),default=None)
    if p.get('operation','view')=='compare':result['comparison']=compare(normalized,p.get('selection'))
    elif p.get('operation','view')!='view':raise ValueError('Read-only adapter supports view or compare only')
    return result


def age_normalized(telemetry,captured,now,*,owner_context=None):
    """Advance normalized cached observations without inventing raw timestamps."""
    import copy
    t=copy.deepcopy(model.obj(telemetry));capture_age=model.age(seconds(captured),now)
    if t.get('observation_version')==2:
        prior=model.obj(t.get('link'));sections=model.obj(t.get('sections'))
        raw=dict(version=2,connected=prior.get('last_reported_connected'),
                 connection_observed_at=prior.get('observed_at'),enabled=t.get('enabled'),
                 fields={name:section.get('observed_at') for name,section in sections.items()})
        raw.update({name:section.get('values') for name,section in sections.items()})
        # Normalized sections retain the explicit observation's source, stamp
        # and decoded values. Preserve that evidence when reconstructing raw
        # inputs; an explicit read remains one-shot even with telemetry paused.
        commands={'status':'20','settings':'10','beacon':'33'}
        explicit={commands[name]:dict(observed_at=section.get('observed_at'),decoded=section.get('values'))
                  for name,section in sections.items() if name in commands and section.get('source')=='one_shot'}
        if explicit:raw['read_request']=dict(operation='read_current',results=explicit)
        return model.normalize_radio({},raw,now,owner_context=owner_context)['live']
    prior=model.obj(t.get('link'));reported=model.flag(prior.get('last_reported_connected',t.get('connected')))
    observed=seconds(prior.get('observed_at'));hb=t.get('heartbeat_age_seconds')
    hb=model.age(observed,now) if observed is not None else hb+capture_age if capture_age is not None and model.number(hb) else None
    if not model.number(hb) or hb<0:hb=None
    owner_ok=model.number(hb) and hb<=15
    freshness='recent' if owner_ok else 'stale' if model.number(hb) else 'unknown'
    t['heartbeat_age_seconds']=hb;t['connected']=reported if owner_ok else None;t['owner_freshness']=freshness
    t['link']=dict(state='reported_down' if reported is False and model.number(hb) else 'reported_up' if reported is True and owner_ok else 'unknown',
                   last_reported_connected=reported,observed_at=observed,age_seconds=hb,freshness=freshness,
                   current_known=bool(owner_ok and reported is not None),current_connected=t['connected'],source='radio_owner')
    for name,section in model.obj(t.get('sections')).items():
        age=section.get('age_seconds')
        stamp=section.get('observed_at')
        section['age_seconds']=model.age(stamp,now) if stamp is not None else age+capture_age if model.number(age) and age>=0 and capture_age is not None else None
        if section.get('state')!='unavailable' and not owner_ok:section['state']='owner_unavailable'
        elif t.get('connected') is False:section['state']='disconnected'
        elif t.get('connected') is None and section.get('state')!='unavailable':section['state']='unknown'
        elif section.get('state')=='fresh':
            limit={'status':20,'settings':45,'beacon':75}.get(name)
            section['state']='unknown' if limit is None or section['age_seconds'] is None else 'stale' if section['age_seconds']>limit else 'fresh'
    state=model.obj(model.obj(t.get('sections')).get('status')).get('state','unavailable')
    t['mode']='disconnected' if t['link']['state']=='reported_down' else 'live' if state=='fresh' else state
    t.setdefault('sections',{});t.setdefault('active',{})
    return t


if __name__=='__main__':
    try:
        payload=json.load(sys.stdin)
        print(json.dumps(adapt(payload),allow_nan=False,separators=(',',':')))
    except (ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'error':str(exc),'read_only':True},separators=(',',':')));raise SystemExit(2)
