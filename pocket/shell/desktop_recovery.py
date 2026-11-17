"""A recovery desktop never overwrites the session that triggered a failure."""
import json
from pathlib import Path
from runtime_codec import unpack

class Recovery:
    def __init__(self,report,store,restore,resume=None):
        self.width=72;self.height=24;self.index=0;self.restore=restore;self.resume=resume;self.status=''
        try:self.report=json.loads(Path(report).read_text())
        except (OSError,ValueError):self.report={'message':'Pocket stopped unexpectedly.','log':str(report)}
        try:
            path=store.path
            if not path.exists():path=path.with_suffix('.json')
            raw=path.read_bytes()
            if len(raw)>65536:raise ValueError('Session exceeds limit')
            if raw.lstrip().startswith(b'{'):
                from legacy_state import decode
                data=decode(raw)
            else:data=unpack(raw,65536)
            self.apps=[name for name,value in data.get('windows',{}).items() if value.get('opened',True)]
        except (OSError,ValueError,TypeError,AttributeError):self.apps=[]
    def lines(self):
        return tuple(line[:self.width] for line in [
            'Pocket stopped unexpectedly.',str(self.report.get('message','')),'',
            'Saved apps and settings have been preserved.',
            'A: restore all apps   Enter: restore selected app',
            'S: stay here   Up/Down: select an app',
            'C: keep this desktop and resume saving',
            'Saved desktop is protected until you press C.','',
            *[('> ' if i==self.index else '  ')+name for i,name in enumerate(self.apps)],
            '',self.status,'Log: '+str(self.report.get('log',''))])
    def key(self,key):
        if key in ('up','down'):self.index=max(0,min(len(self.apps)-1,self.index+(-1 if key=='up' else 1)))
        elif key.lower()=='a':self.status=self.restore(None)
        elif key in ('\r','\n') and self.apps:self.status=self.restore(self.apps[self.index])
        elif key.lower()=='c' and self.resume:self.status=self.resume()
        elif key.lower()=='s':self.status='You can open apps individually from Applications.'
        else:return False
        return True
