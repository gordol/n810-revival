"""Receive-only APRS-IS evidence. Never writes into the radio heard database."""
import datetime
import re
import sqlite3

CALL=re.compile(r'[A-Z0-9]{1,9}(?:-[A-Z0-9]{1,2})?\Z')


class InternetEvidence:
    def __init__(self,path,ttl_seconds=86400):
        self.ttl_seconds=ttl_seconds
        self.db=sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS internet_packets (id INTEGER PRIMARY KEY, observed TEXT NOT NULL, source TEXT NOT NULL, destination TEXT NOT NULL, payload TEXT NOT NULL, raw TEXT NOT NULL)')
        self.db.execute('CREATE INDEX IF NOT EXISTS internet_source ON internet_packets(source,id)')
        self.db.execute("DELETE FROM internet_packets WHERE substr(payload,1,1)!=':' OR substr(payload,11,1)!=':'")
        if str(path)!=':memory:':
            import os
            os.chmod(path,0o600)
        self.db.commit()
    def close(self):self.db.close()
    def expire(self,now=None):
        now=now or datetime.datetime.now(datetime.timezone.utc)
        cutoff=(now-datetime.timedelta(seconds=self.ttl_seconds)).isoformat()
        self.db.execute('DELETE FROM internet_packets WHERE observed < ?', (cutoff,));self.db.commit()
    def clear(self):
        self.db.execute('DELETE FROM internet_packets');self.db.commit()

    def ingest(self,line,observed=None):
        line=line.rstrip('\r\n')
        if not line or line.startswith('#'):return False
        if len(line.encode('utf-8'))>510 or any(ord(c)<32 for c in line):raise ValueError('Invalid APRS-IS line')
        header,sep,payload=line.partition(':');source,arrow,route=header.partition('>')
        if not sep or not arrow or not CALL.fullmatch(source):raise ValueError('Invalid APRS-IS packet')
        destination=route.split(',')[0]
        # Retain only addressed message/ACK evidence; position fill stays in RAM.
        if not payload.startswith(':') or len(payload)<11 or payload[10]!=':':return False
        stamp=observed or datetime.datetime.now(datetime.timezone.utc).isoformat()
        instant=datetime.datetime.fromisoformat(stamp.replace('Z','+00:00'))
        if instant.tzinfo is None:raise ValueError('UTC-aware observation time required')
        stamp=instant.astimezone(datetime.timezone.utc).isoformat()
        self.expire(instant)
        self.db.execute('INSERT INTO internet_packets(observed,source,destination,payload,raw) VALUES(?,?,?,?,?)',(stamp,source,destination,payload,line))
        self.db.execute('DELETE FROM internet_packets WHERE id <= (SELECT COALESCE(MAX(id),0)-4096 FROM internet_packets)')
        self.db.commit();return True
    def message_evidence(self,source,recipient,text,identifier,since):
        """Full calls/SSID, message ID and time scope; observation is not delivery."""
        if not CALL.fullmatch(source) or not CALL.fullmatch(recipient) or not re.fullmatch('[A-Za-z0-9]{1,5}',identifier):raise ValueError('Invalid message identity')
        since=datetime.datetime.fromisoformat(since.replace('Z','+00:00')).astimezone(datetime.timezone.utc).isoformat()
        result={'internet_seen':False,'recipient_ack':False,'recipient_rejected':False,'evidence':[]}
        for stamp,sender,payload,raw in self.db.execute('SELECT observed,source,payload,raw FROM internet_packets WHERE observed>=? AND source IN (?,?) ORDER BY id',(since,source,recipient)):
            if not payload.startswith(':') or len(payload)<11 or payload[10]!=':':continue
            target=payload[1:10].strip();body=payload[11:]
            kind=None
            if sender==source and target==recipient and body==text+'{'+identifier:kind='internet_seen'
            elif sender==recipient and target==source and body=='ack'+identifier:kind='recipient_ack'
            elif sender==recipient and target==source and body=='rej'+identifier:kind='recipient_rejected'
            if kind:result[kind]=True;result['evidence'].append({'kind':kind,'observed':stamp,'transport':'aprs-is','raw':raw})
        return result


def login(call,filter_expression):
    if not CALL.fullmatch(call) or not filter_expression or len(filter_expression)>256 or any(ord(c)<32 or ord(c)>126 for c in filter_expression):raise ValueError('Invalid receive-only feed selection')
    return f'user {call} pass -1 vers Pocket 1.0 filter {filter_expression}\r\n'


def outgoing_evidence(source,row,path=None):
    """Read bounded evidence for a dated outbox row without changing RF state."""
    from pathlib import Path
    path=Path(path) if path else Path.home()/'.local/state/pocket/aprs-internet.sqlite3'
    if not path.exists() or row.get('status')=='Draft':return ''
    try:
        stamp=datetime.datetime.fromisoformat(row['time'].replace('Z','+00:00'))
        if stamp.tzinfo is None:return 'Internet evidence unavailable: message has no dated UTC timestamp'
        now=datetime.datetime.now(datetime.timezone.utc)
        since=max(stamp,now-datetime.timedelta(hours=24)).isoformat()
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=.05) as db:
            events=db.execute('SELECT source,payload FROM internet_packets WHERE observed>=? AND source IN (?,?) ORDER BY id',(since,source,row['to'])).fetchall()
        seen=ack=rej=False
        for sender,payload in events:
            if len(payload)<11 or payload[0]!=':' or payload[10]!=':':continue
            target=payload[1:10].strip();body=payload[11:]
            seen|=sender==source and target==row['to'] and body==row['text']+'{'+row['id']
            ack|=sender==row['to'] and target==source and body=='ack'+row['id']
            rej|=sender==row['to'] and target==source and body=='rej'+row['id']
        return 'Internet: '+('recipient rejection observed' if rej else 'recipient ACK observed' if ack else 'outgoing message seen; no recipient ACK observed' if seen else 'no matching evidence in last 24h')
    except (OSError,ValueError,KeyError,sqlite3.Error):return 'Internet evidence unavailable'
