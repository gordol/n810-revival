"""APRS message protocol, bounded state and delivery evidence; no UI or I/O."""
import collections
import copy
import datetime
import itertools
import re
import secrets

# Keep complete capture timestamps in replay identities; legacy streams still
# supply time-of-day only. Noncapturing groups preserve the parser contract.
TIMESTAMP=r'(?:\d\d:\d\d:\d\d|\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:\d\d(?::\d\d(?:[.,]\d+)?)?))'
PACKET=re.compile(r'^('+TIMESTAMP+r') (\S+)>(\S+) ctl=(?:03|13) pid=f0 (.*)$')
CALL=re.compile(r'^([A-Z0-9]{1,6})(?:-(\d{1,2}))?$')

def callsign(value):
    value=value.strip().upper();m=CALL.fullmatch(value)
    if not m or int(m[2] or 0)>15:raise ValueError('Use a callsign with optional SSID 0–15')
    return value

def parse_message(line):
    m=PACKET.match(line)
    if not m:return None
    stamp,source,route,payload=m.groups()
    for _ in range(3):
        if not payload.startswith('}'):break
        inner=re.match(r'}([^>]+)>([^:]+):(.*)',payload)
        if not inner:return None
        source,route,payload=inner.groups()
    payload=re.sub(r'(?:\\x0[dDaA])+$','',payload)
    if len(payload)<11 or payload[0]!=':' or payload[10]!=':':return None
    recipient=payload[1:10].strip().upper();body=payload[11:]
    if not recipient:return None
    identifier='';reply_ack='';kind='MSG';text=body
    if re.fullmatch(r'(ack|rej)[A-Za-z0-9]{1,5}',body):kind=body[:3].upper();identifier=body[3:];text=''
    else:
        match=re.search(r'\{([A-Za-z0-9]{1,5})(?:\}([A-Za-z0-9]{0,5}))?$',body)
        if match:text=body[:match.start()];identifier=match[1];reply_ack=match[2] or ''
    return dict(time=stamp,source=source.upper(),to=recipient,text=text,kind=kind,id=identifier,reply_ack=reply_ack,raw=line)

MAX_FRAME=65536
MAX_BSS_FIELDS=256


def classify_frame(frame):
    """Classify one unescaped KISS frame without confusing BSS with AX.25."""
    if not isinstance(frame,bytes) or not 1<=len(frame)<=MAX_FRAME:raise ValueError('Invalid frame size/type')
    if frame[0]!=0:return 'kiss_control' if frame[0]&15 else 'unknown'
    packet=frame[1:]
    if packet[:1]==b'\x01':return 'bss'
    offset=0;addresses=0
    while offset+7<=len(packet) and addresses<10:
        raw=packet[offset:offset+7];name=bytes(x>>1 for x in raw[:6]).rstrip(b' ')
        if not name or any(x&1 for x in raw[:6]) or any(not(48<=x<=57 or 65<=x<=90) for x in name):return 'unknown'
        addresses+=1;offset+=7
        if raw[6]&1:return 'ax25' if addresses>=2 and offset<len(packet) else 'unknown'
    return 'unknown'


def parse_bss(frame):
    """Strict native BSS fields; missing and explicitly empty values differ."""
    if classify_frame(frame)!='bss':raise ValueError('Not a BSS data frame')
    fields=[];values={};counter=None;offset=2
    while offset<len(frame):
        if len(fields)>=MAX_BSS_FIELDS:raise ValueError('Too many BSS fields')
        length=frame[offset]
        if length==0x85:
            if offset+3>len(frame) or counter is not None:raise ValueError('Invalid BSS counter')
            counter=int.from_bytes(frame[offset+1:offset+3],'big')
            fields.append(dict(type='counter',value_hex=frame[offset+1:offset+3].hex()))
            offset+=3;continue
        if length<1 or offset+1+length>len(frame):raise ValueError('Truncated/zero BSS field')
        kind=frame[offset+1];value=frame[offset+2:offset+1+length]
        fields.append(dict(type=kind,value_hex=value.hex()))
        if kind in (0x20,0x21,0x24):
            if kind in values:raise ValueError('Ambiguous duplicate BSS text field')
            try:values[kind]=value.decode('utf-8')
            except UnicodeDecodeError as exc:raise ValueError('Invalid BSS UTF-8') from exc
        offset+=1+length
    return dict(protocol='bss',source=values.get(0x20),to=values.get(0x21),
                text=values.get(0x24),id=counter,fields=fields)


def parse_receive(record):
    """Classify a raw capture; expand BSS without synthesizing an APRS line."""
    if not isinstance(record,dict):raise ValueError('Capture must be an object')
    encoded=record.get('frame')
    if not isinstance(encoded,str) or not 2<=len(encoded)<=MAX_FRAME*2:raise ValueError('Invalid frame hex')
    try:frame=bytes.fromhex(encoded)
    except ValueError as exc:raise ValueError('Invalid frame hex') from exc
    if record.get('time') is not None and not isinstance(record['time'],str):raise ValueError('Capture time must be text or absent')
    if record.get('direction') is not None and not isinstance(record['direction'],str):raise ValueError('Capture direction must be text or absent')
    protocol=classify_frame(frame)
    result=parse_bss(frame) if protocol=='bss' else dict(protocol=protocol)
    result.update(raw_hex=encoded,time=record.get('time'),direction=record.get('direction'),
                  capture=copy.deepcopy(record))
    return result


def apply_peer_ack(pending,received,call):
    """Match native APRS evidence only; submission is not an acknowledgement."""
    if received.get('protocol','aprs')!='aprs':return False
    ack=received['id'] if received['kind'] in ('ACK','REJ') else received.get('reply_ack')
    if ack and received['to']==call and pending['id']==ack and pending['to']==received['source'] and pending['status']!='Draft':
        pending['status']='Rejected' if received['kind']=='REJ' else 'Acknowledged'
        return True
    return False


def address(call,last=False):
    m=CALL.fullmatch(callsign(call));ssid=int(m[2] or 0)
    return bytes(ord(c)<<1 for c in m[1].ljust(6))+bytes([0x60|(ssid<<1)|int(last)])

def payload_for(to,text,identifier,kind='MSG'):
    to=callsign(to)
    if not re.fullmatch(r'[A-Za-z0-9]{1,5}',identifier):raise ValueError('Invalid message ID')
    if kind=='MSG':
        if not text or len(text)>67 or any(not 32<=ord(c)<=126 or c in '|~{' for c in text):
            raise ValueError('Message: 1–67 printable ASCII characters, excluding | ~ {')
        body=text+'{'+identifier
    elif kind=='ACK':body='ack'+identifier
    else:raise ValueError('Unsupported message type')
    return (':'+to.ljust(9)+':'+body).encode('ascii')

def kiss_frame(source,path,to,text,identifier,kind='MSG'):
    addresses=['APN810',callsign(source)]+[callsign(c) for c in path]
    if len(path)>2:raise ValueError('Use at most two digipeaters')
    encoded=[address(c,i==len(addresses)-1) for i,c in enumerate(addresses)]
    encoded[0]=encoded[0][:-1]+bytes([encoded[0][-1]|0x80])
    ax25=b''.join(encoded)+b'\x03\xf0'+payload_for(to,text,identifier,kind)
    framed=b'\x00'+ax25
    return b'\xc0'+framed.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')+b'\xc0'

def outbox_document(rows):
    return dict(version=1,outbox=copy.deepcopy(list(rows)[:100]))


def restore_outbox(data):
    """Read the existing version1 shape without claiming delivery after restart."""
    result=[]
    if not isinstance(data,dict) or data.get('version')!=1:return result
    rows=data.get('outbox',[])
    if not isinstance(rows,list):return result
    for value in rows[:100]:
        if isinstance(value,dict) and all(k in value for k in ('to','text','id','kind','status','time')):
            row=copy.deepcopy(value)
            if row['status'] in ('Submitting','Submitted'):row['status']='Unconfirmed'
            result.append(row)
    return result


class State:
    def __init__(self,call,outbox=(),clock=None,identifier_factory=None):
        self.call=callsign(call) if call else '';self.received=collections.deque(maxlen=200);self.outbox=[]
        self.seen=collections.OrderedDict();self.status='Connecting to feed';self.notice=''
        self.clock=clock or (lambda:datetime.datetime.now().strftime('%H:%M:%S'))
        self.identifier_factory=identifier_factory or (lambda:secrets.token_hex(2).upper())
        self.outbox=restore_outbox(dict(version=1,outbox=list(outbox)))

    def add_record(self,record):
        row=parse_receive(record)
        if row['direction']!='radio_to_host' or row['protocol']!='bss' or row['text'] is None:return None
        stamp=row['time']
        key=('bss',stamp,row['raw_hex'])
        if stamp is not None and key in self.seen:return None
        if stamp is not None:
            self.seen[key]=None
            if len(self.seen)>2000:self.seen.popitem(last=False)
        row.update(kind='MSG',raw=row['raw_hex'])
        self.received.appendleft(row)
        return row

    def add(self,line):
        row=parse_message(line)
        if not row:
            if not PACKET.match(line) and line.strip():self.status=line.strip()
            return
        if line in self.seen:return
        self.seen[line]=None
        if len(self.seen)>2000:self.seen.popitem(last=False)
        self.received.appendleft(row)
        for pending in self.outbox:
            if apply_peer_ack(pending,row,self.call):
                self.notice=pending['to']+' '+pending['status'].lower()

    def rows(self,tab):
        if tab==2:return self.outbox
        return [r for r in self.received if r['to']==self.call] if tab==0 else list(self.received)

    def draft(self,to,text,kind='MSG',identifier=None):
        to=callsign(to);identifier=identifier or self.identifier_factory()
        payload_for(to,text,identifier,kind)
        row=dict(to=to,text=text,kind=kind,id=identifier,time=self.clock(),status='Draft')
        self.outbox.insert(0,row);del self.outbox[100:];return row

    def thread(self,peer,protocol='aprs'):
        """Separate bounded RX and outbox snapshots; no invented cross-date order."""
        if protocol=='aprs':peer=callsign(peer)
        elif protocol!='bss' or not isinstance(peer,str):raise ValueError('Invalid protocol/peer')
        return dict(peer=peer,
                    received=[copy.deepcopy(row) for row in self.received if row['source']==peer and row['to']==self.call and row.get('protocol','aprs')==protocol],
                    outbox=[copy.deepcopy(row) for row in self.outbox if row['to']==peer and row.get('protocol','aprs')==protocol])

    def begin_submission(self,row,path):
        """Record one local attempt and return bytes; performs no I/O."""
        if row.get('protocol','aprs')!='aprs':raise ValueError('Only APRS submission is supported')
        wire=kiss_frame(self.call,path,row['to'],row['text'],row['id'],row['kind'])
        row['wire_hex']=wire.hex();row['source']=self.call;row['path']=list(path)
        row['payload']=payload_for(row['to'],row['text'],row['id'],row['kind']).decode('ascii')
        row['status']='Submitting';row['attempts']=row.get('attempts',0)+1
        row['last_attempt']=self.clock();self.notice='Submitting to radio broker'
        return wire

    def submitted(self,row):
        """Local socket queue drained; does not establish RF or peer delivery."""
        ack=row['kind']=='ACK'
        row['status']='ACK submitted' if ack else 'Submitted'
        self.notice='Acknowledgement submitted; RF delivery unconfirmed' if ack else 'Submitted to broker; waiting for peer acknowledgement'

    def unconfirmed(self,row,notice=None):
        row['status']='Unconfirmed'
        if notice is not None:self.notice=notice



def detail_lines(row,outgoing=False,source=None,path=()):
    """Protocol/debug text independent of terminal dimensions and attributes."""
    if row.get('protocol')=='bss':
        return ['BSS RECEIVE DETAILS','Source: '+repr(row['source']),
                'Destination: '+repr(row['to']),'Native counter: '+str(row['id']),
                'Capture time: '+str(row['time']),'Direction: '+str(row['direction']),
                'Text: '+repr(row['text']),'Raw KISS hex: '+row['raw_hex'],
                'Native BSS; no APRS route or acknowledgement is inferred.']
    if outgoing:
        source=row.get('source',source);route=row.get('path',path)
        wire=row.get('wire_hex') or kiss_frame(source,route,row['to'],row['text'],row['id'],row['kind']).hex()
        payload=row.get('payload') or payload_for(row['to'],row['text'],row['id'],row['kind']).decode('ascii')
        lines=['TRANSMIT DETAILS', '', 'Status: '+row['status'], 'Message ID: '+row['id'],
               'Last attempt: '+row.get('last_attempt',row['time']),
               'Source: '+source, 'Recipient: '+row['to'], 'Path: '+(','.join(route) or 'direct'),
               '', 'TNC2 representation:',source+'>APN810'+(','+','.join(route) if route else '')+':'+payload,
               '', 'APRS information field (repr):',repr(payload), '',
               'KISS bytes submitted' if row.get('wire_hex') else 'KISS bytes reconstructed (older attempt):',
               ' '.join(wire[i:i+2] for i in range(0,len(wire),2)), '',
               'These are local submission bytes, not a capture of the RF transmission.']
    else:lines=['RECEIVE DETAILS','',row['raw']]
    return lines


def conversation_groups(call,received=(),outbox=(),traffic='mine',limit=200):
    """Detached endpoint-pair groups; preserve each input's order separately."""
    call=callsign(call) if call else ''
    if traffic not in ('mine','all'):raise ValueError('Traffic must be mine or all')
    limit=max(1,min(200,int(limit)));groups={}
    def group(row,outgoing,ordinal):
        protocol=row.get('protocol','aprs')
        source=row.get('source',call if outgoing else None);destination=row.get('to')
        # Native identities are not normalized into APRS callsigns.
        mine=bool(call) and (destination==call or source==call)
        if traffic=='mine' and not mine:return
        if protocol=='aprs' and mine:
            peer=destination if source==call else source
            endpoints=(call,peer)
        else:
            endpoints=(source,destination)
        key=(protocol,)+endpoints
        if source is None:key+=('unknown_source',ordinal)
        if key not in groups:
            groups[key]=dict(key=key,protocol=protocol,endpoints=endpoints,
                             mine=mine,received=[],outbox=[])
        groups[key]['outbox' if outgoing else 'received'].append(copy.deepcopy(row))
    for ordinal,row in enumerate(itertools.islice(received,limit)):group(row,False,ordinal)
    for ordinal,row in enumerate(itertools.islice(outbox,min(limit,100))):group(row,True,ordinal)
    for item in groups.values():
        item['counts']=dict(received=len(item['received']),outbox=len(item['outbox']),
                            drafts=sum(row.get('status')=='Draft' for row in item['outbox']))
    return list(groups.values())


def receive_diagnostic(record):
    """Retain capture evidence when classification or native decoding fails."""
    result=dict(capture=copy.deepcopy(record),raw_hex=record.get('frame') if isinstance(record,dict) else None,
                protocol='unknown',stages=[],observation=None)
    def stage(name,status,reason):
        result['stages'].append(dict(stage=name,status=status,reason=reason))
    if not isinstance(record,dict):
        stage('capture','invalid','Capture must be an object');return result
    encoded=record.get('frame')
    if not isinstance(encoded,str) or not 2<=len(encoded)<=MAX_FRAME*2:
        stage('capture_hex','invalid','Invalid frame hex size/type');return result
    try:frame=bytes.fromhex(encoded)
    except ValueError:
        stage('capture_hex','invalid','Invalid frame hex');return result
    if not frame:
        stage('capture_hex','invalid','Empty frame');return result
    stage('capture_hex','recognized','Original unescaped frame retained')
    command=frame[0]&15;port=frame[0]>>4
    result.update(kiss_command=command,kiss_port=port)
    if command:
        result['protocol']='kiss_control'
        stage('kiss','unsupported','Non-data KISS command');return result
    stage('kiss','recognized','KISS data command')
    if port:
        stage('discriminator','unsupported','Existing classifier supports data port 0 only');return result
    protocol=classify_frame(frame);result['protocol']=protocol
    if protocol=='unknown':
        stage('discriminator','unsupported','No recognized native marker or AX.25 address shape');return result
    stage('discriminator','recognized',protocol)
    if protocol=='ax25':
        stage('ax25','not_tried','Address shape recognized; control/PID and payload not validated here')
        stage('aprs','not_tried','No APRS payload decoder invoked');return result
    try:result['observation']=parse_receive(record)
    except ValueError as exc:
        stage('native_bss' if str(exc) not in ('Capture time must be text or absent','Capture direction must be text or absent') else 'capture_metadata','invalid',str(exc))
        return result
    stage('native_bss','recognized','Strict BSS TLV decode succeeded')
    stage('typed_message','recognized' if result['observation']['text'] is not None else 'unsupported',
          'BSS text field present' if result['observation']['text'] is not None else 'BSS text field absent')
    return result
