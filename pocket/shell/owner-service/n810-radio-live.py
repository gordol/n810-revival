#!/usr/bin/env python3
"""Read-only radio telemetry owned by the existing Bluetooth receiver."""
import importlib.util
import copy
import json
import os
from pathlib import Path
import struct
import time

STATE=Path('/dev/shm/n810-radio-live.json')
CONTROL=Path('/dev/shm/n810-radio-live-control.json')
GPS_CONTROL=Path('/dev/shm/n810-walk-gps.json')


def atomic(path,value):
    temp=path.with_name(path.name+'.%d.tmp'%os.getpid())
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(value,f)
    temp.replace(path)


def read(path=STATE):
    try:return json.loads(path.read_text())
    except (OSError,ValueError):return {}


def enable(value,path=CONTROL):atomic(path,{'enabled':bool(value)})


def request(command,payload=b''):
    if (command,payload) not in ((6,b'\x01'),(6,b'\x05'),(6,b'\x06'),(20,b''),(10,b''),(33,b'\x02'),(76,b'')):
        raise ValueError('Unsupported telemetry request')
    return b'\xff\x01\x00'+bytes([len(payload)])+struct.pack('>HH',2,command)+payload


def parse_position(raw):
    # Firmware >=49: coordinates; >=133: also accuracy. Require a GPS timestamp.
    if len(raw)<16:return None
    lat=int.from_bytes(raw[:3],'big',signed=True)/30000
    lon=int.from_bytes(raw[3:6],'big',signed=True)/30000
    stamp=int.from_bytes(raw[12:16],'big')
    if not (-90<=lat<=90 and -180<=lon<=180) or not stamp:return None
    result={'lat':lat,'lon':lon,'time':stamp}
    if len(raw)>=18:result['accuracy']=int.from_bytes(raw[16:18],'big')
    return result


class Telemetry:
    def __init__(self,send,state=STATE,control=CONTROL,gps_control=GPS_CONTROL,bandwidth_send=None):
        self.send=send;self.path=state;self.control=control;self.gps_control=gps_control;self.buffer=bytearray()
        self.layouts=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_text())
        spec=importlib.util.spec_from_file_location('radio_decode',Path(__file__).with_name('n810-radio-backup.py'))
        decode=importlib.util.module_from_spec(spec);spec.loader.exec_module(decode);self.decode=decode.decode
        self.state={'version':2,'connection_observed_at':time.time(),'connected':True,'enabled':False,'fields':{},'requests':0,'events':0}
        spec=importlib.util.spec_from_file_location('radio_read_request',Path(__file__).with_name('n810-radio-read-request.py'))
        reads=importlib.util.module_from_spec(spec);spec.loader.exec_module(reads)
        self.read_type=reads.ReadRequest;self.read_session=None;self.read_history={}
        self.due={};self.pending={};self.subscribed=False
        self.gps_until=None;self.bandwidth_requested=False;self._published=None
        self.bandwidth=None
        if bandwidth_send is not None:
            spec=importlib.util.spec_from_file_location('radio_bandwidth',Path(__file__).with_name('n810-radio-bandwidth.py'))
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            self.bandwidth=module.Transaction(bandwidth_send)
        self.refresh_controls()
        self.publish()

    def tune_repeater(self,identity,repeater):
        transaction=self.bandwidth
        if transaction is None:raise ValueError('Tuning transport unavailable')
        if repeater is None:
            result=read(transaction.result_path)
            return result if result.get('id')==identity else {'state':'pending','id':identity}
        if transaction.active or self.read_session and self.read_session.state in ('pending','reading'):raise ValueError('Radio owner is busy')
        spec=importlib.util.spec_from_file_location('uvpro_tune',Path(__file__).with_name('uvpro_tune.py'))
        tune=importlib.util.module_from_spec(spec);spec.loader.exec_module(tune);tune.payload(repeater)
        spec=importlib.util.spec_from_file_location('radio_bandwidth',Path(__file__).with_name('n810-radio-bandwidth.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        module.atomic(transaction.request_path,dict(id=identity,action='tune_repeater',created_at=time.time(),repeater=repeater))
        self.bandwidth_requested=True
        return {'state':'pending','id':identity}

    def start_read(self,value,now=None,wall=None):
        now=time.monotonic() if now is None else now;wall=time.time() if wall is None else wall
        if not isinstance(value,dict) or value.get('version')!=1 or value.get('operation')!='read_current':raise ValueError('Unsupported read request')
        ident=value.get('request_id')
        if not isinstance(ident,str) or not 1<=len(ident)<=80:raise ValueError('Invalid request ID')
        for key,(stamp,session) in list(self.read_history.items()):
            if wall-stamp>300 and session is not self.read_session:del self.read_history[key]
        if ident in self.read_history:return self.read_history[ident][1].snapshot()
        start=value.get('requested_at');expires=value.get('expires_at')
        if type(start) not in (int,float) or type(expires) not in (int,float) or not wall-30<=start<=wall+5 or not wall<expires<=start+30:raise ValueError('Expired or invalid request window')
        if self.bandwidth is not None and self.bandwidth.active:raise ValueError('Bandwidth transaction active')
        if not self.state.get('connected'):raise ValueError('Radio disconnected')
        if self.pending or self.read_session and (self.read_session.state in ('pending','reading') or self.read_session.pending is not None):raise ValueError('Radio reads busy or draining')
        session=self.read_type(ident,started_at=wall,now=now,owner_idle=True)
        self.read_session=session;self.read_history[ident]=(wall,session)
        while len(self.read_history)>32:del self.read_history[next(iter(self.read_history))]
        self.publish();return session.snapshot()

    def read_state(self):
        """Copy actual owner observations without publishing or changing clocks."""
        return copy.deepcopy(self.state)

    def read_progress(self,request_id):
        if request_id not in self.read_history:raise ValueError('Unknown request ID')
        return self.read_history[request_id][1].snapshot()

    def cancel_read(self,request_id):
        if request_id not in self.read_history:raise ValueError('Unknown request ID')
        session=self.read_history[request_id][1];session.cancel();self.publish();return session.snapshot()

    def publish(self):
        if self.read_session:self.state['read_request']=self.read_session.snapshot()
        value=copy.deepcopy(self.state);value.pop('published_at',None)
        if value==self._published:return
        self.state['published_at']=time.time();atomic(self.path,self.state);self._published=value

    def refresh_controls(self,changed=None,now=None,wall=None):
        now=time.monotonic() if now is None else now
        wall=time.time() if wall is None else wall
        if changed is None or self.control in changed:
            enabled=read(self.control).get('enabled',False) is True
            if enabled and not self.state['enabled']:self.due={20:0,10:0,33:0}
            self.state['enabled']=enabled
        if changed is None or self.gps_control in changed:
            until=read(self.gps_control).get('until',0)
            valid=type(until) in (int,float) and wall<until<wall+120
            self.gps_until=now+(until-wall) if valid else None
            self.state['gps_enabled']=valid
        if self.bandwidth is not None and (changed is None or self.bandwidth.request_path in changed):
            self.bandwidth_requested=True

    def next_deadline(self,now=None):
        now=time.monotonic() if now is None else now
        session=self.read_session
        reading=session is not None and (session.state in ('pending','reading') or session.pending is not None)
        deadlines=[]
        if self.gps_until is not None:deadlines.append(self.gps_until)
        if session is not None:
            if session.state in ('pending','reading'):
                deadlines.append(session.started+20)
                deadlines.append(now if session.pending is None else session.sent+5)
            elif session.pending is not None:deadlines.append(session.sent+5)
        bandwidth=self.bandwidth
        if not reading and bandwidth is not None:
            if self.bandwidth_requested:deadlines.append(now)
            if bandwidth.active:
                deadlines.append(bandwidth.deadline+0.000001 if bandwidth.waiting is not None else bandwidth.quiet_until)
                return min(deadlines)
        if not reading:
            if self.state['enabled']:
                deadlines.extend(self.due.get(cmd,0) for cmd in (20,10,33))
            if self.state.get('gps_enabled'):
                if not self.state['enabled']:deadlines.append(self.due.get(20,0))
                deadlines.append(self.due.get(76,0))
        deadlines.extend(sent+5 for sent in self.pending.values() if now<sent+5)
        return min(deadlines) if deadlines else None

    def tick(self,now=None):
        now=time.monotonic() if now is None else now
        if self.gps_until is not None and now>=self.gps_until:
            self.gps_until=None;self.state['gps_enabled']=False
        session=self.read_session
        if session is not None and session.pending is not None and session.state not in ('pending','reading') and now>=session.sent+5:
            session.pending=None
        read_busy=session is not None and (session.state in ('pending','reading') or session.pending is not None)
        if self.bandwidth is not None and not read_busy:
            if self.bandwidth.active or self.bandwidth_requested:
                self.bandwidth.tick(now);self.bandwidth_requested=False
            if self.bandwidth.active:
                self.publish();return
        if session:
            item=session.next(now)
            if item:
                try:self.send(request(*item))
                except Exception:
                    session.state='failed';session.error='owner_send_failed';session.pending=None
            reading=session.state in ('pending','reading') or session.pending is not None
        else:reading=False
        enabled=self.state['enabled']
        gps_active=self.state.get('gps_enabled',False)
        if not reading and gps_active and not enabled and now>=self.due.get(20,0):
            self.send(request(20));self.due[20]=now+10;self.pending[20]=now
        if not reading and gps_active and now>=self.due.get(76,0):
            self.send(request(76));self.due[76]=now+5;self.pending[76]=now
        if enabled:
            if not self.subscribed:
                for event in (1,5,6):self.send(request(6,bytes([event])))
                self.subscribed=True
            for cmd,interval in ((20,10),(10,30),(33,60)):
                if not reading and now>=self.due.get(cmd,0):
                    self.send(request(cmd,b'\x02' if cmd==33 else b''))
                    self.state['requests']+=1;self.due[cmd]=now+interval;self.pending[cmd]=now
        self.state['timeouts']=[cmd for cmd,sent in self.pending.items() if now-sent>=5]
        self.publish()

    def feed(self,data):
        self.buffer.extend(data)
        while len(self.buffer)>=8:
            if self.buffer[:2]!=b'\xff\x01':del self.buffer[0];continue
            size=8+self.buffer[3]+(self.buffer[2]&1)
            if len(self.buffer)<size:break
            frame=bytes(self.buffer[:size]);del self.buffer[:size]
            group,word=struct.unpack('>HH',frame[4:8]);body=frame[8:8+frame[3]]
            if group!=2:continue
            if self.bandwidth is not None:self.bandwidth.consume(word,body)
            cmd=word&0x7fff;event=None
            if cmd==76 and word&0x8000:
                if not self.state.get('gps_enabled') or 76 not in self.pending:continue
                self.pending.pop(76,None)
                self.state['position_reply_status']=body[0] if body else None
                if body[:1]==b'\0':
                    position=parse_position(body[1:])
                    if position:self.state['position']=position;self.state['fields']['position']=time.time()
                self.publish();continue
            explicit=bool(word&0x8000 and self.read_session and self.read_session.pending==cmd)
            draining=bool(word&0x8000 and not self.state['enabled'] and not explicit and cmd in self.pending and not (self.state.get('gps_enabled') and cmd==20))
            if not self.state['enabled'] and not explicit and not draining and not (self.state.get('gps_enabled') and cmd==20):continue
            if word&0x8000:
                if not body or body[0]!=0:
                    if draining and body:self.pending.pop(cmd,None);self.publish()
                    if explicit and body:
                        self.read_session.state='failed';self.read_session.error='radio_reply_status_'+str(body[0]);self.read_session.pending=None;self.publish()
                    continue
                raw=body[1:]
            elif cmd==9 and body:
                event=body[0];raw=body[1:];self.state['events']+=1
                cmd={1:20,6:10}.get(event,0)
                if event==5:
                    self.due[10]=0;continue
            else:continue
            name={20:'status',10:'settings',33:'beacon'}.get(cmd)
            layout={20:'StatusExt' if len(raw)==4 else 'Status',10:'Settings',33:'BSSSettingsV2' if len(raw)>=52 else 'BSSSettings'}.get(cmd)
            if not name:continue
            if layout not in self.layouts:
                layout='BSS' if cmd==33 else layout
            if layout not in self.layouts:continue
            expected=sum(row[1] for row in self.layouts[layout])
            if len(raw)*8<expected:continue
            if word&0x8000:self.pending.pop(cmd,None)
            if draining:self.publish();continue
            if explicit and self.read_session.state not in ('pending','reading'):
                self.read_session.pending=None;self.publish();continue
            previous=self.state.get(name,{})
            self.state[name]=self.decode(raw,self.layouts[layout])
            self.state['fields'][name]=time.time()
            if explicit:self.read_session.reply(cmd,self.state[name],observed_at=self.state['fields'][name])
            if name=='status' and event is not None and any(previous.get(key)!=self.state[name].get(key) for key in ('curr_region','curr_ch_id_lower','curr_channel_id_upper')):
                self.due[10]=min(self.due.get(10,0),time.monotonic()+1)
            self.publish()

    def close(self):
        if self.bandwidth is not None and self.bandwidth.active:self.bandwidth.fail('Receiver stopped before verification')
        if self.read_session and self.read_session.state in ('pending','reading'):
            self.read_session.state='failed';self.read_session.error='radio_disconnected'
        self.state['connected']=False;self.state['connection_observed_at']=time.time();self.publish()
