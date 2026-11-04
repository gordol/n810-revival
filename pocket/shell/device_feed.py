"""Bounded receive snapshots over the existing device owner subscription."""
import threading
from console_source import Source


class RawReceive(Source):
    """Observe the existing receive owner without a second station projection."""
    def _publish(self, online, error=None, rows=None):
        if self.stopped.is_set():return
        old=self.state
        if rows is None and online==old['online'] and error==old['error']:return
        self.records=rows if rows is not None else self.records
        self.state=dict(old,online=online,error=error,raw_records=self.records,revision=old['revision']+1)
        self.starting=False
        self._notify()


def bounded_receive(state, encode, budget=16000):
    rows=state.get('raw_records',())
    selected=[];size=0
    for row in reversed(rows):
        try:length=len(encode(row))
        except (ValueError,TypeError):break
        if size+length>budget:break
        selected.append(row);size+=length
    selected.reverse()
    return dict(online=bool(state.get('online')),error=state.get('error'),
                revision=state.get('revision',0),raw_records=selected,
                omitted_records=len(rows)-len(selected))


class ServiceReceive(Source):
    """Reuse receive decoding/Directory ingest with a subscribed device provider."""
    def __init__(self, provider, directory=None, sources=None):
        self.provider=provider;self.changed=threading.Event();self.changed.set()
        super().__init__('/unused','/unused',directory=directory,sources=sources)
    def refresh(self):self.changed.set()
    def _work(self):
        previous=None
        while not self.stopped.is_set():
            self.changed.wait();self.changed.clear()
            if self.stopped.is_set():break
            try:
                snapshot=self.provider.snapshot()
                if not isinstance(snapshot,dict):raise ValueError('Invalid device snapshot')
                if snapshot.get('owner_online') is not True:
                    previous=None
                    self.gap_possible |= self.state['captured'] is not None
                    self._publish(False,snapshot.get('error') or 'Device service offline')
                    continue
                state=snapshot.get('receive')
                if not isinstance(state,dict):raise ValueError('Device receive feed unavailable')
                if type(state.get('online')) is not bool:raise ValueError('Invalid receive connection state')
                if type(state.get('revision')) is not int or state['revision']<0:raise ValueError('Invalid receive revision')
                rows=state.get('raw_records')
                if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):
                    raise ValueError('Invalid receive records')
                omitted=state.get('omitted_records',0)
                if type(omitted) is not int or omitted<0:raise ValueError('Invalid receive omission count')
                if state.get('error') is not None and not isinstance(state['error'],str):raise ValueError('Invalid receive error')
                key=(snapshot.get('pid'),snapshot.get('implementation'),state['revision'],state['online'],state.get('error'))
                if key==previous:continue
                self.gap_possible |= bool(omitted)
                if state['online']:
                    self._publish(True,state.get('error'),rows)
                else:
                    self.gap_possible |= self.state['captured'] is not None
                    self._publish(False,state.get('error'))
                previous=key
            except Exception as error:
                previous=None
                self._publish(False,'Receive projection failed: '+str(error)[:200])
    def close(self):
        self.stopped.set();self.changed.set()
        self.worker.join(timeout=3);self.control.close();self._wakeup=None
