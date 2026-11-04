"""Guarded home APRS read-only reporting and authorized Wide transaction."""
import json
import os
from pathlib import Path
import stat
import tempfile
import time

REQUEST=Path('/dev/shm/n810-radio-bandwidth-request.json')
RESULT=Path('/dev/shm/n810-radio-bandwidth-result.json')
ACTION='home_aprs_bandwidth_wide'
READ_ACTION='home_aprs_read_only'
STOP_ACTION='home_disable_auto_location'
TUNE_ACTION='tune_repeater'


def private_read(path):
    try:
        info=path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode&0o077 or info.st_size>4096:
            raise ValueError('Unsafe bandwidth request file')
        value=json.loads(path.read_text())
        return value if isinstance(value,dict) else {}
    except FileNotFoundError:return {}


def atomic(path,value):
    fd,name=tempfile.mkstemp(prefix='.radio-bandwidth-',dir=path.parent)
    temp=Path(name)
    try:
        with os.fdopen(fd,'w') as stream:json.dump(value,stream,separators=(',',':'))
        temp.replace(path)
    finally:temp.unlink(missing_ok=True)


def bits(raw,offset,width):return (int.from_bytes(raw,'big')>>(len(raw)*8-offset-width))&((1<<width)-1)


def validate_channel(raw,writable=True):
    if len(raw) not in (25,27):raise ValueError('Unknown channel layout size')
    if raw[0]!=0:raise ValueError('Channel identity is not APRS memory 0')
    if bits(raw,8,2)!=0 or bits(raw,40,2)!=0:raise ValueError('APRS memory is not FM')
    if bits(raw,10,30)!=144390000 or bits(raw,42,30)!=144390000:raise ValueError('Fresh APRS RX/TX frequency is not 144.390 MHz')
    if writable and bits(raw,113,1):raise ValueError('Radio marks bandwidth fixed')


def wide_only(original,desired):
    validate_channel(original)
    if desired!=original[:13]+bytes([original[13]|0x10])+original[14:]:
        raise ValueError('Write changes more than the bandwidth bit')
    return desired


def disable_beacon_only(original,desired):
    if len(original) not in (50,52):raise ValueError('Unknown BSS layout size')
    if desired!=original[:1]+bytes([original[1]&~0x10])+original[2:]:
        raise ValueError('Write changes more than should_share_location bit')
    return desired


def check_mapping(status,settings,beacon,read_only=False):
    if len(status)!=4 or len(settings)!=22 or len(beacon) not in (50,52):raise ValueError('Unknown fresh metadata layout')
    if not bits(status,0,1) or (not read_only and bits(status,1,1)):raise ValueError('Radio off or transmitting')
    if bits(status,20,6)!=0:raise ValueError('Fresh active bank is not expected Ham bank 0')
    if (bits(status,26,4)<<4)|bits(status,8,4):raise ValueError('Fresh selected memory is not APRS 0')
    # Decode settings offsets from the checked-in bitfield layout, not re-encoding.
    layouts=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_text())
    offset=0;values={}
    for name,width,_ in layouts['Settings']:
        values[name]=bits(settings,offset,width);offset+=width
    digital=(values['auto_share_loc_ch_upper']<<5)|values['auto_share_loc_ch']
    if digital!=1 or not values['kiss_en']:raise ValueError('Fresh digital/KISS mapping is not memory 0')
    if (values['channel_a_upper']<<4)|values['channel_a_lower']:raise ValueError('Fresh A memory is not APRS 0')
    offset=0;callsign=None
    for name,width,kind in layouts['BSSSettings']:
        if name=='aprs_callsign':callsign=bits(beacon,offset,width).to_bytes(width//8,'big').split(b'\0',1)[0].decode('ascii','replace')
        offset+=width
    if callsign!='N0ANT' or bits(beacon,16,4)!=0:raise ValueError('Fresh home callsign/SSID does not match N0ANT-0')


class Transaction:
    def __init__(self,send,request=REQUEST,result=RESULT):
        self.send=send;self.request_path=request;self.result_path=result
        try:self.seen=private_read(request).get('id')
        except (OSError,ValueError):self.seen=None
        self.active=False;self.waiting=None;self.reads={};self.result={}

    def save(self):
        self.result['updated_at']=time.time();atomic(self.result_path,self.result)

    def fail(self,reason):
        self.result.update(state='failed',error=str(reason),write_may_have_occurred=self.result.get('write_attempted',False))
        self.active=False;self.waiting=None;self.save()

    def tick(self,now=None):
        now=time.monotonic() if now is None else now
        if self.active:
            if self.waiting is not None and now>self.deadline:self.fail('Reply timeout; no automatic write retry or rollback')
            elif self.waiting is None and now>=self.quiet_until:self.advance(now)
            return
        try:request=private_read(self.request_path)
        except (OSError,ValueError):return
        identity=request.get('id')
        if not isinstance(identity,str) or not identity or identity==self.seen:return
        self.seen=identity
        action=request.get('action')
        self.result=dict(id=identity,action=action,state='checking',read_only=action==READ_ACTION,write_attempted=False,reads={},read_times={})
        created=request.get('created_at')
        if action not in (ACTION,READ_ACTION,STOP_ACTION,TUNE_ACTION) or not isinstance(created,(int,float)) or isinstance(created,bool) or not 0<=time.time()-created<=30:
            self.fail('Unsupported or stale bandwidth request');return
        self.active=True;self.reads={};self.waiting=None;self.quiet_until=now+1
        self.queue=[('status_before',20,b''),('settings_before',10,b''),('beacon_before',33,b'\x02'),
                    ('channel_before',13,b'\0'),('settings_prewrite',10,b''),('beacon_prewrite',33,b'\x02'),('channel_prewrite',13,b'\0'),('status_prewrite',20,b'')]
        self.phase='before'
        if action==READ_ACTION:
            self.phase='read'
            self.queue=[('status_before',20,b''),('settings_before',10,b''),('beacon_before',33,b'\x02'),('channel_before',13,b'\0'),('status_after',20,b'')]
        if action==STOP_ACTION:
            self.phase='stop_before'
            self.queue=[('status_before',20,b''),('settings_before',10,b''),('beacon_before',33,b'\x02'),
                        ('channel_before',13,b'\0'),('beacon_prewrite',33,b'\x02'),('status_prewrite',20,b'')]
        if action==TUNE_ACTION:
            import importlib.util
            spec=importlib.util.spec_from_file_location('uvpro_tune',Path(__file__).with_name('uvpro_tune.py'))
            tune=importlib.util.module_from_spec(spec);spec.loader.exec_module(tune)
            try:self.tune_payload=tune.payload(request['repeater'])
            except (KeyError,ValueError) as error:self.fail(str(error));return
            self.repeater=request['repeater']
            spec=importlib.util.spec_from_file_location('uvpro_secondary',Path(__file__).with_name('uvpro_secondary.py'))
            self.secondary=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.secondary)
            self.settings_layout=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_text())['Settings']
            self.phase='secondary_meta';self.queue=[('tune_status',20,b''),('tune_settings',10,b''),('tune_beacon',33,b'\x02'),('tune_device',4,b'\x03')]
            if self.repeater.get('restore') is True:
                self.backup=private_read(self.result_path.with_name('n810-radio-tune-backup.json'))
                if type(self.backup.get('memory_index')) is not int:
                    self.fail('No saved tuning session to restore');return
                self.tune_slot=self.backup['memory_index']
                self.phase='restore_check';self.queue=[('restore_status',20,b''),('restore_settings',10,b''),('restore_channel',13,bytes([self.tune_slot]))]
        self.save()

    def advance(self,now):
        try:
            if not self.queue:
                if self.phase=='restore_check':
                    backup=self.backup
                    if bits(self.reads['restore_status'],1,1):raise ValueError('Radio transmitting')
                    if self.reads['restore_settings'].hex()!=backup['desired_settings'] or self.reads['restore_channel'].hex()!=backup['desired_channel']:raise ValueError('Radio changed since tuning; no automatic restore')
                    self.original_channel=self.reads['restore_channel'];self.reads['tune_settings']=self.reads['restore_settings']
                    self.phase='restore_verify';self.queue=[('restore_settings_write',11,bytes.fromhex(backup['original_settings'])),('restore_channel_write',14,bytes.fromhex(backup['original_channel'])),('restored_settings',10,b''),('restored_channel',13,bytes([self.tune_slot]))]
                elif self.phase=='restore_verify':
                    if self.reads['restored_settings'].hex()!=self.backup['original_settings'] or self.reads['restored_channel'].hex()!=self.backup['original_channel']:raise ValueError('Restore readback mismatch')
                    self.result.update(state='secondary_restored',completed=True,readback_verified=True,aprs_configuration_preserved=True)
                    self.active=False;self.save();return
                elif self.phase=='secondary_meta':
                    status=self.reads['tune_status']
                    if len(status)!=4 or not bits(status,0,1) or bits(status,1,1):raise ValueError('Radio is off or transmitting')
                    self.aprs_slot,digital=self.secondary.protected(self.reads['tune_settings'],self.settings_layout)
                    if self.aprs_slot!=digital:raise ValueError('Preserving APRS requires A to be the dedicated digital channel')
                    device=self.reads['tune_device']
                    if len(device)<10:raise ValueError('Unknown device capabilities')
                    count=bits(device,64,8)
                    if not 1<count<=128:raise ValueError('Unsupported channel count')
                    self.phase='secondary_scan'
                    self.queue=[('candidate_'+str(i),13,bytes([i])) for i in range(count) if i!=self.aprs_slot]
                elif self.phase=='secondary_scan':
                    rows=[raw for key,raw in self.reads.items() if key.startswith('candidate_')]
                    match=next((r for r in rows if self.secondary.matches(r,self.repeater)),None)
                    empty=next((r for r in reversed(rows) if bits(r,42,30)==0),None)
                    prior=private_read(self.result_path.with_name('n810-radio-tune-backup.json'))
                    owned=next((r for r in rows if r.hex()==prior.get('desired_channel') and (prior.get('managed_slot') is True or r[15:25]==b'PocketTune')),None)
                    chosen=match or owned or empty
                    if chosen is None:raise ValueError('No matching or empty memory; existing presets preserved')
                    self.tune_slot=chosen[0];self.original_channel=chosen
                    self.desired_channel=chosen if match and chosen is not owned else self.secondary.channel(chosen,self.tune_slot,self.repeater)
                    self.desired_settings=self.secondary.settings(self.reads['tune_settings'],self.tune_slot,self.settings_layout)
                    self.result.update(memory_index=self.tune_slot,original_channel=chosen.hex(),original_settings=self.reads['tune_settings'].hex(),desired_channel=self.desired_channel.hex(),aprs_memory=self.aprs_slot)
                    atomic(self.result_path.with_name('n810-radio-tune-backup.json'),dict(managed_slot=match is None or chosen is owned,memory_index=self.tune_slot,original_channel=chosen.hex(),desired_channel=self.desired_channel.hex(),original_settings=self.reads['tune_settings'].hex(),desired_settings=self.desired_settings.hex()))
                    self.phase='secondary_prewrite';self.queue=[('secondary_status',20,b''),('secondary_settings',10,b'')]
                elif self.phase=='secondary_prewrite':
                    if bits(self.reads['secondary_status'],1,1):raise ValueError('Radio transmitting; tuning cancelled')
                    if self.reads['secondary_settings']!=self.reads['tune_settings']:raise ValueError('Settings changed during tuning preparation')
                    self.phase='secondary_channel'
                    self.queue=[] if self.original_channel==self.desired_channel else [('secondary_channel_write',14,self.desired_channel)]
                    self.queue.append(('secondary_channel_check',13,bytes([self.tune_slot])))
                elif self.phase=='secondary_channel':
                    if self.reads['secondary_channel_check']!=self.desired_channel:raise ValueError('Repeater memory readback mismatch; B not selected')
                    self.phase='secondary_select';self.queue=[('secondary_settings_write',11,self.desired_settings),('secondary_settings_check',10,b''),('secondary_beacon_check',33,b'\x02')]
                elif self.phase=='secondary_select':
                    if self.reads['secondary_settings_check']!=self.desired_settings:raise ValueError('B selection readback mismatch')
                    if self.reads['secondary_beacon_check']!=self.reads['tune_beacon']:raise ValueError('APRS beacon configuration changed')
                    self.result.update(state='secondary_tuned',completed=True,readback_verified=True,aprs_configuration_preserved=True)
                    self.active=False;self.save();return
                elif self.phase=='stop_before':
                    for key in ('status_before','status_prewrite'):
                        check_mapping(self.reads[key],self.reads['settings_before'],self.reads['beacon_before'],read_only=True)
                    if self.reads['beacon_before']!=self.reads['beacon_prewrite']:raise ValueError('BSS settings changed during fresh reads')
                    validate_channel(self.reads['channel_before'],writable=False)
                    self.original_beacon=self.reads['beacon_prewrite']
                    self.desired_beacon=disable_beacon_only(self.original_beacon,self.original_beacon[:1]+bytes([self.original_beacon[1]&~0x10])+self.original_beacon[2:])
                    self.result.update(original_beacon_raw=self.original_beacon.hex(),desired_beacon_raw=self.desired_beacon.hex(),beacon_mask='byte1:0x10 clear')
                    self.phase='stop_after'
                    self.queue=[] if self.desired_beacon==self.original_beacon else [('beacon_write',34,self.desired_beacon)]
                    self.queue += [('beacon_after',33,b'\x02'),('channel_after',13,b'\0'),('status_after',20,b''),('settings_after',10,b'')]
                elif self.phase=='stop_after':
                    check_mapping(self.reads['status_after'],self.reads['settings_after'],self.reads['beacon_after'],read_only=True)
                    if self.reads['beacon_after']!=self.desired_beacon:raise ValueError('Full BSS readback differs from desired bytes')
                    if self.reads['channel_before']!=self.reads['channel_after']:raise ValueError('Channel changed during beacon disable')
                    if self.reads['settings_before']!=self.reads['settings_after']:raise ValueError('Settings changed during beacon disable')
                    self.result.update(state='beacon_disabled',completed=True,readback_verified=True,should_share_location=False,changed=self.original_beacon!=self.desired_beacon)
                    self.active=False;self.save();return
                elif self.phase=='read':
                    for key in ('status_before','status_after'):
                        check_mapping(self.reads[key],self.reads['settings_before'],self.reads['beacon_before'],read_only=True)
                    raw=self.reads['channel_before'];validate_channel(raw,writable=False)
                    self.result.update(state='read',completed=True,channel_raw=raw.hex(),reported=dict(
                        bank_index=0,memory_index=raw[0],rx_hz=bits(raw,42,30),tx_hz=bits(raw,10,30),
                        bandwidth=bits(raw,107,1),bandwidth_khz=25 if bits(raw,107,1) else 12.5,
                        pre_de_emph_bypass=bool(bits(raw,108,1)),fixed_bandwidth=bool(bits(raw,113,1))))
                    self.active=False;self.save();return
                elif self.phase=='before':
                    check_mapping(self.reads['status_before'],self.reads['settings_before'],self.reads['beacon_before'])
                    check_mapping(self.reads['status_prewrite'],self.reads['settings_prewrite'],self.reads['beacon_prewrite'])
                    if any(self.reads[k+'_before']!=self.reads[k+'_prewrite'] for k in ('settings','beacon')):raise ValueError('Settings changed during fresh read')
                    if self.reads['channel_before']!=self.reads['channel_prewrite']:raise ValueError('Channel changed during fresh read')
                    self.original=self.reads['channel_prewrite'];validate_channel(self.original)
                    self.desired=wide_only(self.original,self.original[:13]+bytes([self.original[13]|0x10])+self.original[14:])
                    self.result.update(original_raw=self.original.hex(),desired_raw=self.desired.hex(),bandwidth_mask='byte13:0x10')
                    self.phase='after'
                    self.queue=[] if self.desired==self.original else [('write',14,self.desired)]
                    self.queue += [('channel_after',13,b'\0'),('status_after',20,b''),('settings_after',10,b''),('beacon_after',33,b'\x02')]
                else:
                    check_mapping(self.reads['status_after'],self.reads['settings_after'],self.reads['beacon_after'])
                    if self.reads['channel_after']!=self.desired:raise ValueError('Full channel readback differs from desired bytes')
                    if any(self.reads[k+'_before']!=self.reads[k+'_after'] for k in ('settings','beacon')):raise ValueError('Settings/beacon changed during transaction')
                    self.result.update(state='verified',changed=self.original!=self.desired,readback_verified=True)
                    self.active=False;self.save();return
            name,command,payload=self.queue.pop(0);self.waiting=(name,command);self.deadline=now+4
            if command in (11,14,34,35):
                if self.result['action']!=TUNE_ACTION and self.result['action']!={11:TUNE_ACTION,14:ACTION,34:STOP_ACTION,35:TUNE_ACTION}[command]:raise ValueError('Action cannot issue this write')
                self.result['write_attempted']=True;self.save()
            original=(self.original_channel if command==14 else self.reads['tune_settings'] if command==11 else None) if self.result['action']==TUNE_ACTION else self.original if command==14 else self.original_beacon if command==34 else None
            self.send(command,payload,original)
            self.result['stage']=name;self.save()
        except (OSError,ValueError,RuntimeError) as exc:self.fail(exc)

    def consume(self,word,body):
        if not self.active or self.waiting is None or word!=(self.waiting[1]|0x8000):return
        name,command=self.waiting
        try:
            if not body or body[0]!=0:raise ValueError('Radio rejected '+name)
            raw=body[1:]
            if command==11:
                if raw:raise ValueError('Unexpected settings acknowledgement')
            elif command==35:
                if raw:raise ValueError('Unexpected VFO acknowledgement')
            elif command==14:
                if raw!=bytes([self.tune_slot if self.result['action']==TUNE_ACTION else 0]):raise ValueError('Write reply identity mismatch')
            elif command==34:
                if raw:raise ValueError('Unknown BSS write reply layout')
            else:
                if command==13:
                    expected=int(name.split('_')[1]) if name.startswith('candidate_') else self.tune_slot if self.result['action']==TUNE_ACTION else 0
                    if len(raw) not in (25,27) or raw[0]!=expected:raise ValueError('Read channel identity/layout mismatch')
                self.reads[name]=raw;self.result['reads'][name]=raw.hex();self.result['read_times'][name]=time.time()
            self.waiting=None;self.quiet_until=0
            self.advance(time.monotonic())
        except (ValueError,OSError) as exc:self.fail(exc)
