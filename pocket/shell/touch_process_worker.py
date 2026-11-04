"""Private exec worker: sole touch owner with bounded nonblocking handoff."""
import errno
from pathlib import Path
import selectors
import signal
import _socket as socket
import sys

LIMIT=2048
CAPACITY=64
sys.path.insert(0,str(Path(__file__).resolve().parent))
from runtime_codec import pack,unpack

def main():
    channel=socket.socket(fileno=int(sys.argv[1]))
    config=unpack(channel.recv(LIMIT+1),LIMIT);channel.setblocking(False);sys.path.insert(0,config['root'])
    from touch_evdev import TouchSource
    from pointer_events import coalesce_motion
    source=None;selector=selectors.DefaultSelector();queue=[];generation=0;sequence=0
    def envelope(kind,**data):return dict(version=1,kind=kind,**data)
    def suppress():
        source.mapper.down=False
        source.reader.suppress_until_release()
    def cancel():
        nonlocal generation
        generation+=1
        ready=[m for m in queue if m['kind']=='ready'][:1]
        acks=[m for m in queue if m['kind']=='ack']
        queue[:]=ready+([max(acks,key=lambda m:m['request'])] if acks else [])
        suppress()
        queue.append(envelope('event',generation=generation,event=['touch_cancel'],stamp=None,bounds=None))
    def append(event):
        if event[0]=='mouse' and queue and queue[-1]['kind']=='event' and queue[-1]['event'][0]=='mouse':
            from pointer_events import PointerEvent,SourceStamp
            previous=queue[-1]
            a=PointerEvent(previous['event'],stamp=SourceStamp(**previous['stamp']) if previous['stamp'] else None,bounds=tuple(previous['bounds']))
            merged=coalesce_motion(a,event)
            if merged is not None:queue.pop();event=merged
        if len(queue)>=CAPACITY:
            cancel();return False
        stamp=getattr(event,'stamp',None)
        queue.append(envelope('event',generation=generation,event=list(event),stamp=stamp._asdict() if stamp else None,bounds=getattr(event,'bounds',None)))
        return True
    stopping=False
    def stop(signum,frame):
        nonlocal stopping
        stopping=True
        try:channel.close()
        except OSError:pass
    signal.signal(signal.SIGTERM,stop)
    try:
        options={}
        if config.get('native_library'):
            from touch_evdev import EventReader
            import importlib.util
            spec=importlib.util.spec_from_file_location('_cellengine',config['native_library'])
            native=importlib.util.module_from_spec(spec);spec.loader.exec_module(native)
            options['reader_factory']=lambda path:EventReader(path,native=native)
        source=TouchSource(config['path'],Path(config['profile']),config['geometry'],config['columns'],config['rows'],**options)
        queue.append(envelope('ready',diagnostics=source.diagnostics()))
        selector.register(source,selectors.EVENT_READ,'source')
        selector.register(channel,selectors.EVENT_READ|selectors.EVENT_WRITE,'channel')
        while not stopping:
            selector.modify(channel,selectors.EVENT_READ|(selectors.EVENT_WRITE if queue else 0),'channel')
            for key,mask in selector.select():
                if key.data=='source':
                    batch=source.drain()
                    for event in batch:
                        if not append(event):break
                    if batch and queue and queue[-1]['kind']=='event':
                        queue[-1]['diagnostics']=source.diagnostics()
                else:
                    if mask&selectors.EVENT_READ:
                        raw=channel.recv(LIMIT+1)
                        if len(raw)>LIMIT:raise ValueError('oversize control')
                        control=unpack(raw,LIMIT);kind=control['kind']
                        if kind=='stop':return
                        if kind in ('resize','cancel'):
                            cancel()
                            # Caller already invalidated capture; ack is not another cancel event.
                            queue[:]=[m for m in queue if m['kind']!='event']
                            if kind=='resize':source.resize(control['columns'],control['rows'])
                            queue.insert(0,envelope('ack',request=control['request'],generation=generation))
                        else:raise ValueError('unknown control')
                    if mask&selectors.EVENT_WRITE and queue:
                        message=dict(queue[0])
                        if message['kind']=='event':message['sequence']=sequence+1
                        raw=pack(message)
                        if len(raw)>LIMIT:raise ValueError('oversize event')
                        try:channel.send(raw)
                        except OSError as error:
                            if error.errno in (errno.EAGAIN,errno.EWOULDBLOCK,errno.ENOBUFS):continue
                            raise
                        queue.pop(0)
                        if message['kind']=='event':sequence+=1
    except BaseException as error:
        try:channel.send(pack(envelope('error',error=str(error)[:200])))
        except OSError:pass
    finally:
        if source is not None:source.close()
        selector.close();channel.close()

if __name__=='__main__':main()
