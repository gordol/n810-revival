"""Pure bounded one-shot read scheduling for the existing radio owner."""
import copy

READS=((20,b''),(10,b''),(33,b'\x02'))

class ReadRequest:
    def __init__(self,request_id,*,started_at,now,owner_idle):
        if not isinstance(request_id,str) or not 1<=len(request_id)<=80:raise ValueError('Bounded request ID required')
        if owner_idle is not True:raise ValueError('Existing owner transactions must drain first')
        self.id=request_id;self.started_at=started_at;self.started=now
        self.state='pending';self.index=0;self.pending=None;self.sent=None;self.results={};self.error=None
    def next(self,now):
        if self.state not in ('pending','reading'):return None
        if now-self.started>=20 or self.pending is not None and now-self.sent>=5:
            self.state='failed';self.error='read_timeout';return None
        if self.pending is not None:return None
        command,payload=READS[self.index];self.pending=command;self.sent=now;self.state='reading'
        return command,payload
    def reply(self,command,decoded,*,observed_at):
        # Owner must validate vendor reply status/layout before calling this.
        if self.state!='reading' or command!=self.pending:return False
        if not isinstance(decoded,dict):raise ValueError('Validated decoded reply required')
        self.results[str(command)]={'observed_at':observed_at,'decoded':copy.deepcopy(decoded)}
        self.index+=1;self.pending=None
        if self.index==len(READS):self.state='complete'
        return True
    def cancel(self):
        if self.state in ('pending','reading'):self.state='cancelled'
    def snapshot(self):
        return copy.deepcopy(dict(version=1,request_id=self.id,operation='read_current',state=self.state,
            started_at=self.started_at,completed=len(self.results),total=len(READS),
            pending_command=self.pending,results=self.results,error=self.error))
