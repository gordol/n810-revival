"""Opt-in process-owned touch acquisition; UI never opens the input device."""
import atexit
import errno
from runtime_codec import pack,unpack
import os
from pathlib import Path
import _socket as socket
import subprocess
import sys
import threading
from pointer_events import PointerEvent,SourceStamp

LIMIT=2048
CANCEL=('touch_cancel',)

class ProcessTouchSource:
    def __init__(self,path,profile,geometry,columns,rows,*,_source_root=None,native_library=None):
        self.socket,child=socket.socketpair(socket.AF_UNIX,socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,32768)
        child.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,32768)
        child.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,8192)
        self.socket.setsockopt(socket.SOL_SOCKET,socket.SO_SNDBUF,8192)
        self.socket.setblocking(False)
        self.ready=False;self.error=None;self.closed=False;self.captured=False
        self.generation=-1;self.sequence=0;self.request=0;self.waiting=None;self.pending_size=None
        self.pending_cancel=False;self.control=None
        self.snapshot=None
        root=Path(_source_root) if _source_root is not None else Path(__file__).resolve().parent
        config=dict(path=os.fspath(path),profile=os.fspath(profile),geometry=geometry,columns=columns,rows=rows,root=str(root),native_library=str(native_library) if native_library else None)
        try:
            config_packet=pack(config)
            if len(config_packet)>LIMIT:raise ValueError('touch configuration exceeds byte limit')
            self.socket.send(config_packet)
            self.process=subprocess.Popen([sys.executable,'-I',str(Path(__file__).with_name('touch_process_worker.py')),str(child.fileno())],pass_fds=(child.fileno(),),stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except BaseException:
            self.socket.close();raise
        finally:
            if 'process' not in self.__dict__:child.close()
        child.setblocking(False)
        self.reaped=threading.Event()
        self.deadline=None
        def supervise():
            try:
                self.process.wait()
                try:child.send(pack(dict(version=1,kind='error',error='touch worker exited')))
                except OSError:pass
            finally:
                child.close();self.reaped.set()
                if self.deadline is not None:self.deadline.cancel()
                atexit.unregister(self._exit_cleanup)
        self.supervisor=threading.Thread(target=supervise,name='touch-worker-exit',daemon=True)
        atexit.register(self._exit_cleanup)
        self.supervisor.start()

    def fileno(self):return self.socket.fileno()

    def _send(self,message):
        try:self.socket.send(pack(message));return True
        except BlockingIOError:return False
        except OSError as error:
            if error.errno in (errno.EAGAIN,errno.EWOULDBLOCK,errno.ENOBUFS):return False
            self._fail(str(error));return False

    def _fail(self,error):
        self.error=error;self.ready=False;self.pending_cancel=True

    def drain(self):
        if self.closed:return []
        if self.error:raise OSError(self.error)
        if self.control is not None and self._send(self.control):self.control=None
        result=[]
        if self.pending_cancel:result.append(CANCEL);self.pending_cancel=False
        for _ in range(64):
            try:raw=self.socket.recv(LIMIT+1)
            except BlockingIOError:break
            except OSError as error:self._fail(str(error));break
            try:
                if len(raw)>LIMIT:raise ValueError('oversize touch packet')
                message=unpack(raw,LIMIT)
                if not isinstance(message,dict) or message.get('version')!=1:raise ValueError('touch protocol version')
                kind=message['kind']
                if kind=='ready':self.ready=True;self.snapshot=message.get('diagnostics');continue
                if kind=='error':raise OSError(message['error'])
                if kind=='ack':
                    if message['request']==self.waiting:
                        self.generation=message['generation'];self.waiting=None;self.pending_size=None
                    continue
                if kind!='event':raise ValueError('unknown touch packet')
                sequence=message['sequence']
                if type(sequence) is not int or sequence!=self.sequence+1:raise ValueError('touch sequence order')
                self.sequence=sequence
                if self.waiting is not None:continue
                generation=message['generation']
                if type(generation) is not int or generation<0:raise ValueError('touch generation')
                if generation<self.generation:continue
                if generation>self.generation:
                    if self.generation>=0:result=[CANCEL]
                    self.generation=generation
                if 'diagnostics' in message:self.snapshot=message['diagnostics']
                values=message['event']
                if values==['touch_cancel']:result.append(CANCEL);continue
                if (not isinstance(values,list) or len(values)!=5 or values[0]!='mouse'
                    or any(type(v) is not int for v in values[1:4]) or type(values[4]) is not bool):
                    raise ValueError('touch event shape')
                bounds=message['bounds']
                if not isinstance(bounds,list) or len(bounds)!=4 or any(type(v) is not int for v in bounds):
                    raise ValueError('touch bounds')
                stamp=message['stamp']
                result.append(PointerEvent(values,stamp=SourceStamp(**stamp) if stamp else None,bounds=tuple(message['bounds'])))
            except (ValueError,TypeError,KeyError) as error:
                self._fail(str(error));raise ValueError('touch protocol: '+str(error)) from error
        if self.process.poll() is not None and self.error is None:
            self._fail('touch worker exited');raise OSError(self.error)
        return result

    def _reset(self,kind,*,emit_cancel=True,**options):
        if kind=='resize':self.pending_size=(options['columns'],options['rows'])
        elif self.pending_size is not None:
            kind='resize';options=dict(columns=self.pending_size[0],rows=self.pending_size[1])
        self.request+=1;self.waiting=self.request;self.pending_cancel=emit_cancel
        self.control=dict(kind=kind,request=self.request,**options)
        if self._send(self.control):self.control=None

    def resize(self,columns,rows):self._reset('resize',columns=columns,rows=rows)

    def cancel(self,host):
        if self.captured:host.finish(False);host.pointer_origin=None
        self.captured=False;self._reset('cancel',emit_cancel=False)

    def diagnostics(self):
        result=dict(self.snapshot) if self.snapshot is not None else dict(collection_mode='starting',counts={},last_drain={},state={})
        result.update(acquisition='process',ready=self.ready,error=self.error,snapshot_policy='startup-or-last-active-batch')
        return result

    def _kill(self):
        if not self.reaped.is_set():
            try:self.process.kill()
            except ProcessLookupError:pass

    def _close(self,schedule_deadline):
        if self.closed:return
        self.closed=True;self._send(dict(kind='stop'));self.socket.close()
        if not self.reaped.is_set():
            try:self.process.terminate()
            except ProcessLookupError:pass
            if schedule_deadline:
                self.deadline=threading.Timer(1,self._kill)
                self.deadline.daemon=True;self.deadline.start()

    def close(self):self._close(True)

    def _exit_cleanup(self):
        # Interpreter exit may wait; ordinary UI close never does.
        self._close(False)
        if not self.reaped.wait(1):
            self._kill();self.reaped.wait(1)
