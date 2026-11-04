"""Real private owner streams, with deterministic publication accounting; no radio."""
import argparse
import os
from pathlib import Path
import signal
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum'))
from owner import Owner,serve
from wire import encode
p=argparse.ArgumentParser()
for name in ('socket','state','ready-fd'):p.add_argument('--'+name,required=True)
a=p.parse_args()
signal.signal(signal.SIGTERM,lambda *_:sys.exit(0))
class Fixture(Owner):
    builds=0
    def snapshot_frame(self):
        self.builds+=1
        return encode(dict(version=1,owner_online=True,revision=self.revision,build=self.builds,body='x'*8000))
    def dispatch(self,request):
        action=request.get('action')
        if action=='bump':self.revision+=1
        elif action=='wake':self.wake.send(b'x')
        elif action=='service_call':
            if request.get('payload',{}).get('change'):self.revision+=1
        elif action!='counts':return super().dispatch(request)
        return dict(version=1,builds=self.builds,revision=self.revision)
serve(a.socket,a.state,'fixture',Fixture,ready_fd=int(a.ready_fd))
