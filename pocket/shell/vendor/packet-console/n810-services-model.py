"""Bounded receive-only Services state and readable packet facts."""
import collections
import re


TIMESTAMP = r'(?:\d\d:\d\d:\d\d|\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:\d\d(?::\d\d(?:[.,]\d+)?)?))'
PACKET = re.compile(r'^('+TIMESTAMP+r') (\S+)>(\S+) ctl=([0-9a-f]+) pid=f0 (.*)$')



FREQUENCY = re.compile(r'(?<![\d.])(\d{3}\.\d{3})(?:\d*)\s*MHz\b', re.I)



def hints(payload):
    # Free-text evidence, never a statement that a gateway is reachable.
    result = []
    for expression, label in ((r'\b(?:WINLINK|RMS)\b', 'Winlink mention'),
                              (r'\bBBS\b', 'BBS mention'),
                              (r'\b(?:NODE|NETROM|NET/ROM)\b', 'Node mention'),
                              (r'\bIGATE\b', 'IGate mention'),
                              (r'\bAPMAIL\b', 'APMAIL flag')):
        if re.search(expression, payload, re.I): result.append(label)
    return result



def message(payload):
    if len(payload) < 11 or payload[0] != ':' or payload[10] != ':': return None
    recipient = payload[1:10].strip()
    if not recipient: return None
    body = payload[11:]
    if re.fullmatch(r'(?:ack|rej)[A-Za-z0-9]{1,5}', body):
        return dict(to=recipient, text=body[3:], kind='ACK' if body[:3]=='ack' else 'REJ', id=body[3:])
    text, sep, identifier = body.rpartition('{')
    if not sep or not re.fullmatch(r'[A-Za-z0-9]{1,5}(?:\}[A-Za-z0-9]{0,5})?', identifier):
        text, identifier = body, ''
    return dict(to=recipient, text=text, kind='MSG', id=identifier)



class State:
    def __init__(self, call):
        self.call = call.upper().split('-')[0]
        self.stations = collections.OrderedDict()
        self.messages = collections.deque(maxlen=200)
        self.seen = collections.OrderedDict()
        self.status = 'Connecting to feed'
        self.total = 0

    def add(self, line):
        found = PACKET.match(line)
        if not found:
            if line.strip(): self.status = line.strip()[:200]
            return
        stamp, source, route, control, payload = found.groups()
        if line in self.seen: return
        self.seen[line] = None
        if len(self.seen) > 2000: self.seen.popitem(last=False)
        self.total += 1
        # AX.25 broadcasts with the APRS PID are the relevant packet type here.
        if control not in ('03', '13'): return
        row = dict(time=stamp, call=source, route=route, payload=payload, raw=line,
                   hints=hints(payload), frequencies=FREQUENCY.findall(payload))
        # Object advertisements belong to the named object, with its sender kept.
        row['entity'] = source
        if payload.startswith(';') and len(payload) > 10:
            if payload[10] == '_':
                self.stations.pop(source + '/' + payload[1:10].strip(), None)
                return
            if payload[10] == '*': row['entity'] = source + '/' + payload[1:10].strip()
        if not payload.startswith(':'):
            self.stations[row['entity']] = row
            self.stations.move_to_end(row['entity'])
            if len(self.stations) > 256: self.stations.popitem(last=False)
        msg = message(payload)
        if msg:
            row.update(msg)
            row['ours'] = msg['to'].upper().split('-')[0] == self.call
            self.messages.appendleft(row)
        self.status = 'Packet received'

    def rows(self, tab):
        if tab == 2: return list(self.messages)
        rows = list(reversed(self.stations.values()))
        if tab == 0: rows = [row for row in rows if row['hints'] or row['frequencies']]
        return rows



POSITION = re.compile(r'(\d{2})(\d{2}\.\d{2})([NS])(.)(\d{3})(\d{2}\.\d{2})([EW])(.)', re.S)



def readable(payload):
    # Only the presentation copy interprets the monitor's escaped bytes.
    return re.sub(r'\\x([0-9a-fA-F]{2})', lambda m: chr(int(m[1],16)), payload)



def details(row):
    payload = readable(row['payload'])
    lines = ['From: '+row['call']+'   Packet time: '+row['time']]
    route = row['route'].split(',')
    if 'kind' in row:
        lines.append('To: '+row['to']+(' (your callsign)' if row['ours'] else ''))
        if row['kind'] == 'ACK': lines.append('Acknowledgement for message '+row['id'])
        elif row['kind'] == 'REJ': lines.append('Rejection for message '+row['id'])
        else:
            lines.append('Message: '+row['text'])
            if row['id']: lines.append('Message ID: '+row['id'])
    else:
        offset = None
        if payload[:1] in ('!', '='): offset=1
        elif payload[:1] in ('/', '@'): offset=8
        elif payload.startswith(';'): offset=18
        comment = payload
        if offset is not None:
            position = POSITION.match(payload,offset)
            if position:
                latd,latm,ns,table,lond,lonm,ew,symbol=position.groups()
                lines.append('Position: '+latd+' deg '+latm+"' "+ns+' / '+lond+' deg '+lonm+"' "+ew)
                comment = payload[position.end():]
        elif payload[:1] in ("`", "'") and len(payload)>=9:
            lines.append('Position: Mic-E encoded (coordinates not decoded here)')
            comment=payload[9:]
        elif payload.startswith('>'): comment=payload[1:]
        comment = ''.join(c if c.isprintable() else ' ' for c in comment).strip()
        if row['frequencies']:
            lines.append('Advertised frequency: '+', '.join(f+' MHz' for f in row['frequencies']))
        tone=re.search(r'\bT(\d{3})\b',comment)
        if tone: lines.append('Tone code: T'+tone[1]+' (as advertised)')
        if row['hints']: lines.append('Clues: '+', '.join(row['hints']))
        if comment: lines.append('Comment: '+comment)
    lines.append('AX.25 destination: '+route[0])
    lines.append('Path: '+(', '.join(route[1:]) if len(route)>1 else 'direct / none listed'))
    return lines



def summary(row):
    if 'kind' in row:
        if row['kind']=='ACK': return 'Acknowledged message '+row['id']
        if row['kind']=='REJ': return 'Rejected message '+row['id']
        return row['text']
    fields = [f+' MHz' for f in row['frequencies']] + row['hints']
    if fields: return ', '.join(fields)
    for line in details(row):
        if line.startswith('Comment: '): return line[9:]
    return 'Position / station packet'



def fields(row):
    result=[('Station',row['call']),('Packet time',row['time'])]
    position=[]
    for line in details(row)[1:]:
        name,sep,value=line.partition(': ')
        if not sep: name,value='Status',line
        name={'Advertised frequency':'Frequency','AX.25 destination':'AX.25 dest'}.get(name,name)
        if name=='Position': position.append((name,value.replace('Mic-E encoded (coordinates not decoded here)','Mic-E; coordinates not decoded')))
        else: result.append((name,value))
    return result+position
