"""Walk probe schedule and return-evidence model."""
import time


class Plan:
    def __init__(self,budget=20):
        self.budget=budget;self.count=0;self.armed=False;self.due=None;self.pending=None;self.probes=[];self.reason='Receive only; not armed'
    def disarm(self,reason):
        self.armed=False;self.due=None;self.reason=reason
    def arm(self,now,healthy):
        if not healthy:raise ValueError('Need connected radio and fresh GPS fix (accuracy <=100 m)')
        if self.count>=self.budget:raise ValueError('Probe budget exhausted; start a new session to test again')
        self.armed=True;self.due=now+60;self.reason='Armed; first automatic probe in 60 seconds'
    def tick(self,now,healthy):
        if self.pending and now-self.pending['mono']>=30:self.pending['status']='No return confirmed';self.pending=None
        if self.armed and not healthy:self.disarm('Radio/GPS unavailable; re-arm explicitly')
        return self.armed and self.pending is None and now>=self.due
    def submitted(self,now,position,payload):
        self.count+=1;self.due=now+60
        row=dict(number=self.count,mono=now,time=time.time(),position=dict(position),payload=payload.decode(),status='Submitted; awaiting repeated copy')
        self.probes.append(row);self.pending=row
        if self.count>=self.budget:self.disarm('Probe limit reached; receive only')
        return row
    def returned(self,payload,route):
        for row in reversed(self.probes):
            if row['payload'].encode()==payload:
                if row.get('return_path'):return None
                row['return_path']=route;row['return_time']=time.time();row['status']='Repeated copy observed'
                if self.pending is row:self.pending=None
                return row
