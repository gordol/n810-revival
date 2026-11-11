"""Installed Symbian applications, discovered lazily from AppArc."""
class Launcher:
    def __init__(self,host):
        self.host=host;self.width=58;self.height=14;self.index=0;self.rows=[];self.notice='';self.open()
    def open(self):
        from symbian_catalog import applications,packages
        self.rows=applications()+packages();self.index=min(self.index,max(0,len(self.rows)-1))
        self.notice='Enter: launch/install   R: refresh'
        from pathlib import Path
        try:
            code=Path('/run/n810-pocket-native/symbian-result').read_text().split('\t',1)[0]
            if code not in ('0','130','-15'):self.notice='Last application stopped (status '+code+'). R refreshes.'
        except OSError:pass
    def lines(self):
        rows=['Symbian applications',self.notice,'']
        rows += [('> ' if i==self.index else '  ')+row['title'] for i,row in enumerate(self.rows)]
        if not self.rows:rows+=['Install applications, then refresh this list.']
        return tuple(rows)
    def key(self,key):
        if key in ('up','down'):
            if self.rows:self.index=(self.index+(1 if key=='down' else -1))%len(self.rows)
            return True
        if key in ('r','R'):self.open();return True
        if key not in ('enter','\n','\r'):return False
        if not self.rows:return True
        from symbian_launch import launch
        try:
            selected=self.rows[self.index];opener=getattr(self.host,'symbian_window',None)
            if opener and not selected['id'].startswith('install:'):opener(selected)
            else:launch(selected['id'])
            self.notice='Launching '+selected['title']+'…'
        except (OSError,RuntimeError,ValueError) as error:self.notice=str(error)
        return True
    def close(self):pass

def descriptor():
    return dict(id='symbian',title='Symbian',factory=Launcher,preferred_size=(62,18),minimum_size=(30,8),category='Applications',description='Installed Symbian applications',help=(('Launch',('Arrows: choose an application','Enter: launch','R: refresh the installed list','Exit the application to return to Pocket.')),))
