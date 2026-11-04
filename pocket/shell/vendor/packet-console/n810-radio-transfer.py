"""Pure review plans for cached radio banks and local drafts. No radio execution."""
import copy
import importlib.util
from pathlib import Path
import uuid


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).parent/path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


library=module('radio_library','n810-radio-library.py')
model=module('radio_model','web-console/radio-read-model.py')


def capabilities():
    return dict(pull_cached=True,pull_live=False,push=False,verify_radio_write=False,
                reason='Shared Bluetooth owner has no bank-transfer write/readback transaction. Selection is browsing only.')


def one(rows,key,value):
    matches=[row for row in rows if type(row.get(key)) is type(value) and row.get(key)==value]
    if len(matches)!=1:raise ValueError('Selected '+key+' is missing or ambiguous')
    return matches[0]


def snapshot_bank(snapshot,bank_index):
    if model.integer(bank_index) is None:raise ValueError('Explicit integer radio bank index required')
    normalized=model.normalize_radio({'radio_snapshot':snapshot},None)
    if not normalized['snapshot']['available']:raise ValueError('Completed downloaded snapshot required')
    return one(normalized['snapshot']['banks'],'index',bank_index)


def plan_pull(snapshot,bank_index,name=None):
    """Propose a new local bank; never replace existing saved banks or save."""
    bank=snapshot_bank(snapshot,bank_index)
    captured=snapshot.get('finished') or snapshot.get('started')
    proposal=dict(id=uuid.uuid4().hex,name=library.validate('name',name or bank['name'] or 'Radio bank'),channels=[])
    raw_bank=one(snapshot['banks'],'index',bank_index)
    blocks=[];warnings=[];slots=[]
    for native in bank['channels']:
        index=native['index'];slots.append(dict(index=index,state=native['state'],local_channel_id=None))
        if native['state']=='empty':continue
        if native['state']!='populated':blocks.append(dict(index=index,reason='Memory read unavailable.'));continue
        reasons=[]
        for field in ('rx_hz','tx_hz','rx_tone','tx_tone','power','bandwidth','scan','tx_enabled','rx_mode','tx_mode'):
            if native.get(field) is None:reasons.append('Unknown '+field)
        for field in ('rx_mode','tx_mode'):
            if native.get(field) not in (None,'FM'):reasons.append(field+' not represented in local draft schema')
        for field in ('rx_tone','tx_tone'):
            if native.get(field,{} ) and native[field]['kind']=='dcs':reasons.append(field+' DCS not represented in local draft schema')
        if reasons:blocks.append(dict(index=index,reason='; '.join(reasons)));continue
        row=library.channel(native.get('name') or 'Memory '+str(index))
        values=dict(name=native.get('name') or 'Memory '+str(index),rx_mhz=native['rx_hz']/1e6,
                    tx_mhz=native['tx_hz']/1e6,rx_ctcss=native['rx_tone']['value'],
                    tx_ctcss=native['tx_tone']['value'],power=native['power'],bandwidth=native['bandwidth'],
                    scan=native['scan'],tx_enabled=native['tx_enabled'])
        try:
            for key,value in values.items():row[key]=library.validate(key,value)
        except ValueError as exc:blocks.append(dict(index=index,reason=str(exc)));continue
        row['radio_origin']=dict(bank_index=bank_index,memory_index=index,captured_at=captured,
                                 raw=copy.deepcopy(one(raw_bank['channels'],'index',index)))
        proposal['channels'].append(row);slots[-1]['local_channel_id']=row['id']
        warnings.append(dict(index=index,reason='Additional native flags/raw fields retained as provenance, not editable draft fields.'))
    return dict(operation='pull_cached',capabilities=capabilities(),source=dict(kind='downloaded_snapshot',bank_index=bank_index,captured_at=captured),
                proposed_bank=proposal,slots=slots,blocks=blocks,warnings=warnings,
                can_apply_locally=not blocks,review_required=True,saved=False,
                effect='Append reviewed copy as a new local draft bank; existing drafts and radio unchanged.')


def apply_pull(local_data,plan):
    """Append a reviewed complete proposal to an in-memory copy, never save."""
    if plan.get('operation')!='pull_cached' or plan.get('blocks') or plan.get('can_apply_locally') is not True:
        raise ValueError('Pull proposal is blocked or incomplete')
    result=copy.deepcopy(local_data);bank=copy.deepcopy(plan['proposed_bank'])
    if bank['id']=='core' or any(row['id']==bank['id'] for row in result['banks']):raise ValueError('Proposed local bank identity already exists')
    result['banks'].append(bank)
    return result


def plan_push(snapshot,bank_index,local_data,local_bank_id,assignments):
    """Review explicit local-channel to radio-slot diffs; execution unsupported."""
    bank=snapshot_bank(snapshot,bank_index);local=library.get_bank(local_data,local_bank_id)
    changes=[];seen=set()
    for assignment in assignments:
        slot=assignment.get('memory_index');identity=assignment.get('channel_id')
        if model.integer(slot) is None or slot in seen:raise ValueError('Unique explicit radio memory indices required')
        seen.add(slot);native=one(bank['channels'],'index',slot)
        draft=library.get_channel(local_data,local_bank_id,identity)
        if local_bank_id=='core' and slot!=draft.get('hardware_slot'):raise ValueError('Core draft reserved slot mapping cannot be changed')
        changes.append(dict(memory_index=slot,local_channel_id=identity,comparison=model.compare_channels(native,model.draft_channel(draft)),
                            native_state=native['state']))
    mapped={row['local_channel_id'] for row in changes}
    return dict(operation='push_review',capabilities=capabilities(),can_execute=False,review_required=True,
                source=dict(local_bank_id=local['id'],radio_bank_index=bank_index,captured_at=snapshot.get('finished') or snapshot.get('started')),
                changes=changes,unmapped_local_channels=[row['id'] for row in local['channels'] if row['id'] not in mapped],
                untouched_radio_slots=[row['index'] for row in bank['channels'] if row['index'] not in seen],
                required_before_execution=['Fresh exclusive-owner read of target bank/settings and recoverable backup.',
                'Explicit selected-slot review; preserve unknown native fields and untouched slots.',
                'Owner-side bank write transaction; never infer support from protocol command definitions.',
                'Read back every affected slot/name/settings and compare actual results; restore active state and report failures.'])
