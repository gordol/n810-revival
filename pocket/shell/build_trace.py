"""Bounded, optional milestones from actual model construction work."""
from collections import namedtuple,deque
from threading import Lock,local,Event as StopEvent
from concurrent.futures import CancelledError
import time

Event=namedtuple('Event','kind count when')
_context=local()


def checkpoint():
    trace=getattr(_context,'trace',None)
    if trace is not None and trace.stopped.is_set():raise CancelledError()


def mark(kind,count=0):
    checkpoint()
    trace=getattr(_context,'trace',None)
    if trace is not None:trace.mark(kind,count)


def preview(factory):
    trace=getattr(_context,'trace',None)
    if trace is not None:
        wire=factory()
        with trace.lock:trace.preview=wire


class Trace:
    def __init__(self):
        self.stopped=StopEvent();self.events=deque(maxlen=16);self.lock=Lock();self.preview=None
        self.jobs=dict(started=0,completed=0,cancelled=0,failed=0,running=False,last_wall_seconds=None,last_cpu_seconds=None,total_cpu_seconds=0.,last_error=None)
        self.job_start=None
    def mark(self,kind,count=0):
        with self.lock:self.events.append(Event(kind,count,time.monotonic()))
    def cancel(self):self.stopped.set()
    def snapshot(self):
        with self.lock:return tuple(self.events)
    def wire(self):
        with self.lock:return self.preview
    def progress(self):
        with self.lock:
            result=dict(self.jobs)
            result['running_wall_seconds']=max(0,time.monotonic()-self.job_start) if self.jobs['running'] else None
            return result
    def run(self,fn,*args):
        start=time.monotonic();cpu=time.thread_time();failure=None
        with self.lock:
            self.events.clear();self.preview=None;self.job_start=start
            self.jobs['started']+=1;self.jobs['running']=True
        _context.trace=self
        try:
            checkpoint()
            self.mark('request')
            value=fn(*args);self.mark('ready',len(value));return value
        except BaseException as error:
            failure=error;raise
        finally:
            _context.trace=None
            elapsed_cpu=time.thread_time()-cpu
            with self.lock:
                self.jobs['running']=False;self.jobs['last_wall_seconds']=time.monotonic()-start
                self.jobs['last_cpu_seconds']=elapsed_cpu;self.jobs['total_cpu_seconds']+=elapsed_cpu
                self.jobs['last_error']=type(failure).__name__ if failure else None
                self.jobs['cancelled' if isinstance(failure,CancelledError) else 'failed' if failure else 'completed']+=1
