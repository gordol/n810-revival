"""Local saved-bank domain API. No terminal, transport or radio dependencies."""
import csv
import io
import json
import math
import os
from pathlib import Path
import tempfile
import uuid

STORE=Path('~/.local/state/n810-radio/banks.json').expanduser()
FIELDS=[('name','Name'),('rx_mhz','RX MHz'),('tx_mhz','TX MHz'),('rx_ctcss','RX tone Hz'),
        ('tx_ctcss','TX tone Hz'),('power','Power'),('bandwidth','Bandwidth'),('scan','Scan'),('tx_enabled','Transmit')]


def channel(name='New channel',rx=146.520):
    return dict(id=uuid.uuid4().hex,name=name,rx_mhz=rx,tx_mhz=rx,rx_ctcss=None,tx_ctcss=None,
                power='Low',bandwidth='Wide',scan=True,tx_enabled=False)


CATEGORIES=['Voice Alert','Winlink','Repeaters','FRS','GMRS','MURS','Emcomm',
            'Law','Outdoor','Parks','Sheriff','Interop']


def core_bank():
    rows=[channel('Digital',144.390),channel('VHF calling',146.520),channel('UHF calling',446.000)]
    for slot,row in enumerate(rows):row['hardware_slot']=slot;row['id']='core-'+str(slot)
    return dict(id='core',name='Core',channels=rows)


def ensure_core(data):
    core=next((bank for bank in data['banks'] if bank['id']=='core'),None)
    if core is None:data['banks'].insert(0,core_bank())
    else:
        slots=[row.get('hardware_slot') for row in core['channels']]
        if slots != [0,1,2]:raise ValueError('Core must reserve slots 0 digital, 1 VHF calling, 2 UHF calling')
        data['banks'].remove(core);data['banks'].insert(0,core)
    return data


def validate(key,value):
    if key=='name':
        text=str(value).strip()
        if not text or len(text)>48 or any(ord(c)<32 for c in text):raise ValueError('Use 1–48 printable characters')
        return text
    if key in ('scan','tx_enabled'):
        if isinstance(value,bool):return value
        if str(value).lower() in ('true','1','on','yes'):return True
        if str(value).lower() in ('false','0','off','no'):return False
        raise ValueError('Use on/off')
    if key in ('power','bandwidth'):
        choices=('Low','Medium','High') if key=='power' else ('Narrow','Wide')
        text=str(value).capitalize()
        if text not in choices:raise ValueError('Use '+', '.join(choices))
        return text
    if key in ('rx_ctcss','tx_ctcss') and (value is None or str(value).lower() in ('off','none','0','')):return None
    number=float(value)
    if not math.isfinite(number):raise ValueError('Use a finite number')
    if key in ('rx_mhz','tx_mhz'):
        if not (136<=number<=174 or 400<=number<=520):raise ValueError('Use a VHF/UHF frequency')
    elif not 60<=number<=260:raise ValueError('Use CTCSS Hz, or off')
    return number


def load(path):
    path=Path(path)
    if not path.exists():
        return {'version':1,'banks':[core_bank()]+[dict(id=uuid.uuid4().hex,name=name,channels=[]) for name in CATEGORIES]}
    data=json.loads(path.read_text())
    if data.get('version')!=1 or not isinstance(data.get('banks'),list):raise ValueError('Unsupported bank library')
    identities=set()
    for bank in data['banks']:
        bank['name']=validate('name',bank['name'])
        if bank['id'] in identities:raise ValueError('Duplicate bank ID')
        identities.add(bank['id'])
        for row in bank['channels']:
            if not isinstance(row.get('id'),str):raise ValueError('Channel ID missing')
            for key,_ in FIELDS:row[key]=validate(key,row[key])
    return ensure_core(data)


def save(path,data):
    ensure_core(data)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.banks-')
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2);f.write('\n')
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def import_csv(data,text,name):
    # Parse completely before touching the library.
    rows=[]
    for values in csv.DictReader(io.StringIO(text)):
        row=channel()
        for key,_ in FIELDS:
            if key in values and values[key] is not None and values[key]!='':row[key]=validate(key,values[key])
        if not values.get('name') or not values.get('rx_mhz'):raise ValueError('CSV needs name and rx_mhz')
        if not values.get('tx_mhz'):row['tx_mhz']=row['rx_mhz']
        rows.append(row)
    if not rows:raise ValueError('CSV contains no channels')
    bank=dict(id=uuid.uuid4().hex,name=validate('name',name),channels=rows)
    data['banks'].append(bank);return bank


def export_csv(bank):
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=[k for k,_ in FIELDS]);writer.writeheader()
    for row in bank['channels']:writer.writerow({k:row[k] for k,_ in FIELDS})
    return out.getvalue()



def read_saved(path):
    """Read actual saved drafts without inserting editor default banks."""
    path=Path(path)
    if not path.exists():return None
    data=json.loads(path.read_text())
    if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('banks'),list):raise ValueError('Unsupported bank library')
    banks=set()
    for bank in data['banks']:
        if not isinstance(bank,dict):raise ValueError('Invalid saved bank')
        if not isinstance(bank.get('id'),str) or not bank['id'] or bank['id'] in banks:raise ValueError('Invalid or duplicate bank ID')
        banks.add(bank['id']);validate('name',bank.get('name',''));channels=set()
        if not isinstance(bank.get('channels'),list):raise ValueError('Invalid bank channels')
        for row in bank['channels']:
            if not isinstance(row,dict):raise ValueError('Invalid saved channel')
            if not isinstance(row.get('id'),str) or not row['id'] or row['id'] in channels:raise ValueError('Invalid or duplicate channel ID')
            channels.add(row['id'])
            for key,_ in FIELDS:
                if key not in row:raise ValueError('Saved channel field missing: '+key)
                validate(key,row[key])
    return data


def get_bank(data,bank_id):
    matches=[bank for bank in data['banks'] if bank['id']==bank_id]
    if len(matches)!=1:raise ValueError('Saved bank identity is missing or ambiguous')
    return matches[0]


def get_channel(data,bank_id,channel_id):
    matches=[row for row in get_bank(data,bank_id)['channels'] if row['id']==channel_id]
    if len(matches)!=1:raise ValueError('Saved channel identity is missing or ambiguous')
    return matches[0]


def edit(data,operation,**params):
    """Apply one explicit local-draft edit to a copy; never save or touch radio."""
    import copy
    result=copy.deepcopy(data)
    bank_id=params.get('bank_id')
    bank=get_bank(result,bank_id) if bank_id is not None else None
    protected=bank is not None and bank['id']=='core'
    if operation=='add_bank':
        result['banks'].append(dict(id=uuid.uuid4().hex,name=validate('name',params['name']),channels=[]))
    elif operation=='import_csv':import_csv(result,params['text'],params['name'])
    elif bank is None:raise ValueError('Explicit saved bank required')
    elif operation=='copy_bank':
        cloned=copy.deepcopy(bank);cloned['id']=uuid.uuid4().hex
        cloned['name']=validate('name',params.get('name',bank['name'][:42]+' copy'))
        for row in cloned['channels']:row['id']=uuid.uuid4().hex;row.pop('hardware_slot',None)
        result['banks'].append(cloned)
    elif operation in ('rename_bank','delete_bank','add_channel'):
        if protected:raise ValueError('Core slots 0 / 1 / 2 are reserved')
        if operation=='rename_bank':bank['name']=validate('name',params['name'])
        elif operation=='delete_bank':result['banks'].remove(bank)
        else:
            row=channel()
            changes=params.get('changes',{})
            for key,value in changes.items():
                if key not in dict(FIELDS):raise ValueError('Unsupported channel field: '+key)
                row[key]=validate(key,value)
            bank['channels'].append(row)
    elif operation in ('update_channel','delete_channel','assign_channel'):
        row=get_channel(result,bank_id,params['channel_id'])
        if operation=='update_channel':
            for key,value in params['changes'].items():
                if key not in dict(FIELDS):raise ValueError('Unsupported channel field: '+key)
                row[key]=validate(key,value)
        elif operation=='delete_channel':
            if protected:raise ValueError('Core slots 0 / 1 / 2 are reserved')
            bank['channels'].remove(row)
        else:
            target=get_bank(result,params['target_bank_id'])
            if target['id']=='core':raise ValueError('Core slots 0 / 1 / 2 are reserved')
            move=params.get('move',False)
            if not isinstance(move,bool):raise ValueError('Move must be boolean')
            if move and protected:raise ValueError('Core slots 0 / 1 / 2 are reserved')
            assigned=copy.deepcopy(row);assigned.pop('hardware_slot',None)
            if move:
                if target is bank:raise ValueError('Source and target bank are identical')
                if any(c['id']==row['id'] for c in target['channels']):raise ValueError('Target already contains channel identity')
                bank['channels'].remove(row)
            else:assigned['id']=uuid.uuid4().hex
            target['channels'].append(assigned)
    else:raise ValueError('Unsupported local-draft operation')
    return result
