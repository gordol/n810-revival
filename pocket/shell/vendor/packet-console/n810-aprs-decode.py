"""Shared cached APRS facts; decoded on arrival/history load, not per map cell.
Mic-E follows APRS101 chapter 10. No transport, database, or radio access.
"""
import functools
import json
import math
import re

def plain_evidence(payload):
    found=[]
    advertised='' if payload.startswith((':','}')) else payload
    if payload.startswith(('=','@')):found.append(('messaging','Messaging advertised'))
    elif payload.startswith(('!','/')):found.append(('messaging','Messaging not advertised (support unknown)'))
    if len(payload)>10 and payload[0]==':' and payload[10]==':':
        body=payload[11:]
        found.append(('message','Message activity observed'))
        if re.fullmatch(r'ack[A-Za-z0-9]{1,5}(?:\\x0d)?',body):found.append(('ack','Acknowledgement observed'))
    for kind,pattern in [('BBS',r'\bBBS\b'),('Winlink/RMS',r'\b(?:WINLINK|RMS)\b'),
                         ('mail',r'\b(?:MAILBOX|APMAIL|MAIL)\b'),('node',r'\b(?:NODE|NETROM|NET/ROM)\b')]:
        if re.search(pattern,advertised,re.I):found.append(('service:'+kind,payload[:300]))
    phg=re.search(r'(?<![A-Za-z0-9])PHG([0-9])([0-9:;<=>?@A-Z])([0-9])([0-8])(?![0-9])',advertised)
    if phg:
        power,height,gain,direction=phg.groups()
        feet=10*(2**(ord(height)-ord('0')))
        found.append(('phg',json.dumps(dict(code=phg.group(0),watts=int(power)**2,
            height_ft=feet,height_m=round(feet*.3048),gain_db=int(gain),
            direction=['omnidirectional','NE','E','SE','S','SW','W','NW','N'][int(direction)]))))
    frequency=re.search(r'(?<![\d.])\d{3}\.\d{3}(?:\d*)\s*MHz\b',advertised,re.I)
    if frequency:found.append(('voice',payload[:300]))
    return found


POSITION=re.compile(r'(\d{2})(\d{2}\.\d{2})([NS])(.)(\d{3})(\d{2}\.\d{2})([EW])(.?)')


# Mic-E decoding adapted from aprslib by Rossen Georgiev (GPLv2).
# Attribution and license: licenses/upstream/aprslib-NOTICE.txt and
# licenses/upstream/aprslib-LICENSE.txt at the repository root.
def mice(payload,destination):
    dest=destination.split('-')[0]
    body=re.sub(r'\\x([0-9a-fA-F]{2})',lambda m:chr(int(m[1],16)),payload)[1:]
    if not re.fullmatch(r'[0-9A-LP-Z]{3}[0-9LP-Z]{3}',dest) or len(body)<8:
        raise ValueError('missing/invalid destination or truncated payload')
    if not re.fullmatch(r'[&-\x7f][&-a][\x1c-\x7f]{2}[\x1c-\x7d][\x1c-\x7f][!-~][/\\0-9A-Z]',body[:8]):
        raise ValueError('invalid Mic-E coordinate/symbol bytes')
    digits=''.join(' ' if c in 'KLZ' else str(ord(c)-ord('P')) if 'P'<=c<='Y' else str(ord(c)-ord('A')) if 'A'<=c<='J' else c for c in dest)
    if not re.fullmatch(r'\d{2,6} {0,4}',digits):raise ValueError('invalid latitude digits/ambiguity')
    ambiguity=len(digits)-len(digits.rstrip())
    centered=list(digits)
    if ambiguity:centered[2 if ambiguity==4 else 6-ambiguity]='3' if ambiguity==4 else '5'
    centered=''.join(centered).replace(' ','0')
    minutes=float(centered[2:4]+'.'+centered[4:6]);lat=int(centered[:2])+minutes/60
    degrees=ord(body[0])-28+(100 if dest[4]>='P' else 0)
    if 180<=degrees<=189:degrees-=80
    elif 190<=degrees<=199:degrees-=190
    minute=ord(body[1])-28
    if minute>=60:minute-=60
    minute+=(ord(body[2])-28)/100
    if ambiguity:
        step=(.1,1,10,60)[ambiguity-1]
        minute=30 if ambiguity==4 else (math.floor(minute/step)+.5)*step
    lon=degrees+minute/60
    if not (minutes<60 and 0<=minute<60 and 0<=lat<=90 and 0<=lon<=180):raise ValueError('coordinates outside valid range')
    speed=(ord(body[3])-28)*10+(ord(body[4])-28)//10
    course=((ord(body[4])-28)%10)*100+ord(body[5])-28
    if speed>=800:speed-=800
    if course>=400:course-=400
    if not (0<=speed<=799 and 0<=course<=360):raise ValueError('invalid speed/course')
    bits=''.join('0' if c in '0123456789L' else '1' for c in dest[:3])
    number=int(bits,2);custom=any('A'<=c<='K' for c in dest[:3])
    status=('Emergency','Priority','Special','Committed','Returning','In service','En route','Off duty')[number]
    if custom and number:status='Custom %d'%(7-number)
    return dict(position=[lat if dest[3]>='P' else -lat,-lon if dest[5]>='P' else lon],
                symbol=body[6],symbol_table=body[7],speed_knots=speed,course=course,
                status=status,ambiguity=ambiguity,comment=body[8:])


@functools.lru_cache(maxsize=1024)
def decode(payload,destination=''):
    if payload.startswith('}'):return {'format':'Third-party APRS / outer RF wrapper','evidence':[]}
    result={'format':'APRS','evidence':plain_evidence(payload)}
    if payload.startswith(('`',"'")):
        result['format']='Mic-E'
        # Binary fields are not free-text advertisements.
        result['evidence']=[]
        try:
            result.update(mice(payload,destination))
            result['evidence']+=plain_evidence('>'+result['comment'])
            result['evidence'].append(('mice',json.dumps({k:result[k] for k in ('status','speed_knots','course','ambiguity')})))
        except ValueError as exc:result['error']='Mic-E decode failed: '+str(exc)
    else:
        offset=1 if payload.startswith(('!','=')) else 8 if payload.startswith(('/','@')) else 18 if payload.startswith(';') and len(payload)>10 and payload[10]=='*' else payload.find('!')+1 if payload.startswith(')') and '!' in payload else -1
        match=POSITION.match(payload,offset) if offset>=0 else None
        if match:
            a,b,ns,table,c,d,ew,symbol=match.groups();lat=int(a)+float(b)/60;lon=int(c)+float(d)/60
            if float(b)<60 and float(d)<60 and lat<=90 and lon<=180:
                result.update(position=[lat if ns=='N' else -lat,lon if ew=='E' else -lon],symbol=symbol,symbol_table=table)
                motion=re.match(r'(\d{3})/(\d{3})',payload[match.end():])
                if motion:result.update(course=int(motion[1]),speed_knots=int(motion[2]))
        if offset>=0 and re.search(r'(?:^|[/ ,])W[1-7](?:[,/ ]|$)',payload,re.I):
            result['evidence'].append(('role','APRS digipeater / routing advertised'))
    if 'position' in result:
        result['evidence'].append(('position',json.dumps(result['position'])))
        if result.get('symbol')=='#':result['evidence'].append(('role','APRS digipeater / advertised symbol'))
    return result


def facts(result):
    lines=[result['format']]
    if 'error' in result:return lines+[result['error']]
    if 'position' in result:
        lat,lon=result['position'];lines+=['Position   %.5f, %.5f'%(lat,lon),
            'Symbol     '+result.get('symbol_table','')+result.get('symbol','')]
    if 'speed_knots' in result:lines+=['Motion     %d kn / %03d deg'%(result['speed_knots'],result['course'])]
    if 'status' in result:lines+=['Status     '+result['status']]
    if result.get('ambiguity'):lines+=['Position approximate / ambiguity %d'%result['ambiguity']]
    for kind,detail in result['evidence']:
        if kind=='phg':
            rf=json.loads(detail)
            lines+=['Radio      %d W / %d dB / %s'%(rf['watts'],rf['gain_db'],rf['direction']),
                    'Height     %s ft / %s m HAAT'%(format(rf['height_ft'],','),format(rf['height_m'],','))]
        elif kind in ('messaging','role','message','ack'):lines.append(detail)
        elif kind.startswith('service:') or kind=='voice':lines+=['Advertised '+detail]
    return lines
