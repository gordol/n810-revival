"""Run a native owner through the existing service loop without another interpreter."""
import os
import subprocess
import threading
from owner import serve
from native_owner import NativeBackend

class NativeSession:
    def __init__(self,path,state,station,config,radio,connection,ready_fd,service_socket=None,remote=None):
        self.stopped=threading.Event();self.returncode=None;self.owner=None;self.error=None
        descriptor=os.dup(ready_fd);listening=False
        def factory(directory,name):
            self.owner=NativeBackend(directory,name,config,radio,connection,remote=remote)
            self.owner.service_owner_socket=service_socket
            return self.owner
        def ready():
            nonlocal descriptor,listening
            fd,descriptor=descriptor,None
            try:os.write(fd,b'R')
            finally:os.close(fd)
            listening=True
        def run():
            try:
                serve(path,state,station,factory,ready_fd=ready,stopped=self.stopped)
                self.returncode=0
            except BaseException as error:
                self.error=str(error);self.returncode=1
            finally:
                if not listening and self.owner:self.owner.close()
                if descriptor is not None:
                    try:os.close(descriptor)
                    except OSError:pass
        self.thread=threading.Thread(target=run,name='native-radio-owner',daemon=True);self.thread.start()
    def poll(self):return self.returncode
    def terminate(self):
        self.stopped.set()
        if self.owner:
            if self.owner.stack:
                try:self.owner.stack.cancel_stamp()
                except (OSError,ValueError,ConnectionError):
                    if not self.owner.remote:raise
            self.owner.post(dict(event='data_ready'))
    def wait(self,timeout=None):
        self.thread.join(timeout)
        if self.thread.is_alive():raise subprocess.TimeoutExpired('native radio owner',timeout)
        return self.returncode
    def kill(self):
        # A thread cannot be killed safely; the manager must report failed cleanup.
        self.terminate()
