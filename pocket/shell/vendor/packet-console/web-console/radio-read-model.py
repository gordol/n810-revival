"""Pure normalization of downloaded radio data and existing owner telemetry."""
import copy
import math
import time

MODES={0:'FM',1:'AM',2:'DMR'}
COMPARE=('name','rx_hz','tx_hz','rx_tone','tx_tone','power','bandwidth','scan','tx_enabled',
         'rx_mode','tx_mode','mute','talk_around','emphasis_bypass')
DRAFT_FIELDS=COMPARE[:9]


def obj(value):return value if isinstance(value,dict) else {}
def rows(value):return value if isinstance(value,list) else []
def number(value):return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
def integer(value):return value if isinstance(value,int) and not isinstance(value,bool) else None
def flag(value):return value if isinstance(value,bool) else None


def age(stamp,now):
    if not number(stamp) or stamp<=0 or stamp>now+5:return None
    return max(0,now-stamp)


def tone(raw):
    if integer(raw) is None or raw<0:return None
    if raw==0:return {'kind':'off','value':None}
    return {'kind':'dcs','value':raw} if raw<6700 else {'kind':'ctcss','value':raw/100}


def channel(row,bank_index):
    row=obj(row);p=obj(row.get('decoded'));response=obj(row.get('response'))
    index=integer(row.get('index'));decoded_index=integer(p.get('channel_id'))
    mismatch=decoded_index is not None and decoded_index!=index
    diagnostics=[]
    if index is None or not 0<=index<=255:diagnostics.append('Invalid memory slot identity.')
    if mismatch:diagnostics.append('Decoded memory identity disagrees with requested slot.')
    if 'status' in response and response['status']!=0:diagnostics.append('Radio memory read failed.')
    available=bool(p) and not diagnostics
    bits=p.get('_decoded_bits');total=p.get('_available_bits')
    if number(bits) and number(total) and bits<total:
        available=False;diagnostics.append('Memory reply is incomplete.')
    rx=integer(p.get('rx_freq'));tx=integer(p.get('tx_freq'))
    state='unavailable' if not available or rx is None or rx<0 else 'empty' if rx==0 else 'populated'
    high=flag(p.get('tx_at_max_power'));medium=flag(p.get('tx_at_med_power'))
    power='High' if high is True else 'Medium' if high is False and medium is True else 'Low' if high is False and medium is False else None
    disabled=flag(p.get('tx_disable'))
    return dict(bank_index=bank_index,index=index,decoded_index=decoded_index,
                index_mismatch=mismatch,diagnostics=diagnostics,state=state,
                name=p.get('name_str') if isinstance(p.get('name_str'),str) else None,
                rx_hz=rx if available else None,tx_hz=tx if available and tx is not None and tx>=0 else None,
                offset_hz=tx-rx if state=='populated' and tx is not None and tx>0 else None,
                rx_tone=tone(p.get('rx_sub_audio')) if available else None,
                tx_tone=tone(p.get('tx_sub_audio')) if available else None,
                rx_mode=MODES.get(integer(p.get('rx_mod'))) if available else None,
                tx_mode=MODES.get(integer(p.get('tx_mod'))) if available else None,
                rx_mode_raw=p.get('rx_mod'),tx_mode_raw=p.get('tx_mod'),
                power=power if available else None,
                bandwidth={0:'Narrow',1:'Wide'}.get(integer(p.get('bandwidth'))) if available else None,
                tx_enabled=not disabled if available and disabled is not None else None,
                scan=flag(p.get('scan')) if available else None,mute=flag(p.get('mute')) if available else None,
                talk_around=flag(p.get('talk_around')) if available else None,
                emphasis_bypass=flag(p.get('pre_de_emph_bypass')) if available else None,
                fixed_freq=flag(p.get('fixed_freq')) if available else None,
                fixed_bandwidth=flag(p.get('fixed_bandwidth')) if available else None,
                fixed_tx_power=flag(p.get('fixed_tx_power')) if available else None,
                sign=flag(p.get('sign')) if available else None,
                source='downloaded_snapshot')


def draft_channel(row):
    p=obj(row)
    def hz(key):
        value=p.get(key)
        return round(value*1000000) if number(value) and value>0 else None
    def ctcss(key):
        if key not in p:return None
        value=p[key]
        if value is None:return {'kind':'off','value':None}
        return {'kind':'ctcss','value':value} if number(value) and value>0 else None
    return dict(id=p.get('id'),hardware_slot=integer(p.get('hardware_slot')),name=p.get('name'),
                rx_hz=hz('rx_mhz'),tx_hz=hz('tx_mhz'),rx_tone=ctcss('rx_ctcss'),tx_tone=ctcss('tx_ctcss'),
                power=p.get('power') if p.get('power') in ('Low','Medium','High') else None,
                bandwidth=p.get('bandwidth') if p.get('bandwidth') in ('Narrow','Wide') else None,
                scan=flag(p.get('scan')),tx_enabled=flag(p.get('tx_enabled')),
                source='saved_draft',represented_fields=list(DRAFT_FIELDS))


def compare_channels(native,draft):
    """Compare one explicitly selected normalized pair against a download."""
    native=obj(native);draft=obj(draft);result=[]
    for field in COMPARE:
        a=native.get(field);b=draft.get(field)
        state='not_represented' if field not in draft.get('represented_fields',[]) else 'unknown' if native.get('state')!='populated' or a is None or b is None else 'equal' if a==b else 'different'
        result.append(dict(field=field,state=state,native=a,draft=b))
    return {'source':'downloaded_snapshot','fields':result}


def packed(p,lower,upper,shift,short=False):
    low=integer(p.get(lower));high=integer(p.get(upper))
    if low is None or low<0 or low>=(1<<shift):return None
    if high is None:
        if not short:return None
        high=0
    if high<0:return None
    return (high<<shift)|low


def status_indicators(sections):
    """Project only recent status observations as current relative signal/activity."""
    section=obj(obj(sections).get('status'));values=obj(section.get('values'))
    state=section.get('state','unavailable');fresh=state=='fresh'
    raw=integer(values.get('rssi'))
    if raw is not None and not 0<=raw<=15:raw=None
    rx=flag(values.get('is_in_rx'));tx=flag(values.get('is_in_tx'))
    metadata=dict(observed_at=section.get('observed_at'),age_seconds=section.get('age_seconds'))
    return dict(signal=dict(metadata,state='unknown' if fresh and raw is None else state,
                            raw=raw if fresh else None,last_reported_raw=raw,maximum=15,unit='relative'),
                activity=dict(metadata,state='unknown' if fresh and (rx is None or tx is None) else state,
                              rx=rx if fresh else None,tx=tx if fresh else None,
                              last_reported_rx=rx,last_reported_tx=tx))


def normalize_catalog(catalog_radio):
    """Project retained memory data independently of live observation ages."""
    catalog=obj(catalog_radio)
    snapshot=obj(catalog.get('radio_snapshot'))
    accepted=snapshot.get('complete') is True and ('restore_bank' not in snapshot or snapshot.get('restored') is True)
    banks=[]
    for bank in rows(snapshot.get('banks')) if accepted else []:
        bank=obj(bank);index=integer(bank.get('index'))
        if index is None:continue
        channels=[channel(row,index) for row in rows(bank.get('channels'))]
        banks.append(dict(index=index,name=bank.get('name'),channels=channels,total=len(channels),
                          populated=sum(c['state']=='populated' for c in channels)))
    banks.sort(key=lambda b:b['index'])
    saved=obj(catalog.get('radio_banks'));drafts=[]
    for bank in rows(saved.get('banks')):
        bank=obj(bank);channels=[draft_channel(row) for row in rows(bank.get('channels'))]
        drafts.append(dict(id=bank.get('id'),name=bank.get('name'),source='saved_draft',
                           channel_count=len(channels),channels=channels))
    return dict(snapshot=dict(available=accepted,banks=banks,
                captured_at=snapshot.get('finished') or snapshot.get('started') if accepted else None,
                source='downloaded_snapshot'),
                presets=dict(banks=drafts,profiles=copy.deepcopy(obj(obj(catalog.get('radio_profiles')).get('profiles'))),source='saved_draft'))


def owner_observation(context):
    """Live context is caller-supplied outside retained JSON; fail closed."""
    result=dict(state='unknown',instance_id=None,radio={})
    if context is None:return result
    c=obj(context);state=obj(c.get('state'));owner=obj(state.get('owner'))
    identity=owner.get('instance_id');radio=obj(state.get('radio'))
    valid=(type(state.get('version')) is int and state['version']==1 and state.get('type')=='state'
           and owner.get('context')=='live_owner' and type(identity) is str and len(identity)==32
           and all(char in '0123456789abcdefABCDEF' for char in identity)
           and (radio.get('connected') is None or type(radio.get('connected')) is bool))
    stamp=radio.get('observed_at')
    try:valid=valid and (stamp is None or type(stamp) in (int,float) and math.isfinite(stamp) and stamp>=0)
    except OverflowError:valid=False
    if not valid:return result
    available=c.get('transport_connected') is True and c.get('subscribed_on_this_stream') is True
    return dict(state='available' if available else 'unavailable',instance_id=identity,radio=radio)


def normalize_radio(catalog_radio,telemetry,now=None,*,catalog_model=None,owner_context=None):
    t=obj(telemetry);now=time.time() if now is None else now
    retained=normalize_catalog(catalog_radio) if catalog_model is None else catalog_model
    heartbeat_age=age(t.get('heartbeat'),now);connected=flag(t.get('connected'));enabled=flag(t.get('enabled'))
    fields=obj(t.get('fields'));sections={}
    owner_ok=heartbeat_age is not None and heartbeat_age<=15
    owner_freshness='unknown' if heartbeat_age is None else 'recent' if owner_ok else 'stale'
    link=dict(state='reported_down' if connected is False and heartbeat_age is not None else
                    'reported_up' if connected is True and owner_ok else 'unknown',
              last_reported_connected=connected,observed_at=t.get('heartbeat') if heartbeat_age is not None else None,
              age_seconds=heartbeat_age,freshness=owner_freshness,current_known=owner_ok and connected is not None,
              current_connected=connected if owner_ok else None,source='radio_owner')
    owner=owner_observation(owner_context)
    event_owner=(type(t.get('version')) is int and t['version']==2) or owner['instance_id'] is not None
    if event_owner:
        owner_ok=owner['state']=='available';heartbeat_age=None
        owner_freshness='current' if owner_ok else owner['state']
        observed=owner['radio'].get('observed_at') if owner['instance_id'] is not None else t.get('connection_observed_at')
        try:
            if not number(observed) or observed<0:observed=None
        except OverflowError:observed=None
        reported=flag(owner['radio'].get('connected')) if owner['instance_id'] is not None else flag(t.get('connected'))
        connected=reported if owner_ok else None
        link=dict(state='reported_up' if owner_ok and connected is True else 'reported_down' if owner_ok and connected is False else 'unknown',
                  last_reported_connected=reported,observed_at=observed,age_seconds=age(observed,now),
                  freshness=owner_freshness,current_known=owner_ok and connected is not None,
                  current_connected=connected,source='feed_live_owner' if owner['instance_id'] is not None else 'retained_telemetry')
    for key,limit in (('status',20),('settings',45),('beacon',75)):
        values=obj(t.get(key));stamp=fields.get(key);seconds=age(stamp,now)
        read_request=obj(t.get('read_request'))
        command={'status':'20','settings':'10','beacon':'33'}[key]
        result=obj(obj(read_request.get('results')).get(command))
        explicit=(read_request.get('operation')=='read_current' and stamp is not None
                  and result.get('observed_at')==stamp and result.get('decoded')==values)
        if not t:state='unavailable'
        elif not owner_ok:state='owner_unavailable'
        elif connected is False:state='disconnected'
        elif connected is not True:state='unknown'
        elif enabled is False and not explicit:state='paused'
        elif not values or stamp is None:state='waiting'
        elif seconds is None or (enabled is not True and not explicit):state='unknown'
        else:state='stale' if seconds>limit else 'fresh'
        sections[key]=dict(state=state,observed_at=stamp,age_seconds=seconds,values=copy.deepcopy(values),
                           source='one_shot' if explicit else 'owner_telemetry')
    status=obj(t.get('status'));settings=obj(t.get('settings'))
    digital=packed(settings,'auto_share_loc_ch','auto_share_loc_ch_upper',5)
    tx=flag(status.get('is_in_tx'));rx=flag(status.get('is_in_rx'))
    activity='TX' if tx is True else 'RX' if tx is False and rx is True else 'Idle' if tx is False and rx is False else None
    mode={'fresh':'live'}.get(sections['status']['state'],sections['status']['state'])
    if link['state']=='reported_down':mode='disconnected'
    active=dict(bank_index=integer(status.get('curr_region')),
                selected_memory_index=packed(status,'curr_ch_id_lower','curr_channel_id_upper',4,status.get('_decoded_bits')==16),
                a_memory_index=packed(settings,'channel_a_lower','channel_a_upper',4),
                b_memory_index=packed(settings,'channel_b_lower','channel_b_upper',4),
                digital_memory_index=digital-1 if digital is not None and digital>0 else None,
                digital_current=digital==0 if digital is not None else None,activity=activity,
                source='owner_telemetry')
    result=dict(version=1,comparison_fields=list(COMPARE),snapshot=retained['snapshot'],presets=retained['presets'],
                live=dict(mode=mode,connected=link['current_connected'],link=link,owner_freshness=owner_freshness,enabled=enabled,heartbeat_age_seconds=heartbeat_age,sections=sections,active=active,indicators=status_indicators(sections)),
                limits=['Memory properties are downloaded, not live.','Browser selection does not tune the radio.',
                        'Preset comparisons require an explicitly selected pair; no automatic matching.'])
    if event_owner:result['live'].update(observation_version=2,owner=dict(state=owner['state'],instance_id=owner['instance_id']))
    return result
