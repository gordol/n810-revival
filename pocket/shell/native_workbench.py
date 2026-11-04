"""Local analysis presentation. Only cached snapshots and explicit commands."""
from app_widgets import AdaptivePanels,PanelSpec,Canvas,DetailBlock,SelectList,TextInput


class WorkbenchView:
    def __init__(self,command):
        self.command=command;self.width=92;self.height=28;self.snapshot={};self.revision=None;self.notice=''
        self.layout=AdaptivePanels((PanelSpec('file','File & jobs',30,34),PanelSpec('result','Results',28,58)))
        self.path=TextInput(limit=1024);self.tone=TextInput('700',limit=8);self.wpm=TextInput('20',limit=5)
        self.controls=SelectList(('File path','Inspect file','Tone Hz','Speed WPM','Run CW replay','Cancel job','Refresh evidence','Open retained result'))
        self.history=SelectList(());self.mode='result';self.scroll=0;self._spans=();self._rects={};self._hits=[];self._body_key=None;self._body=None

    def update(self,snapshot):
        if snapshot.get('revision')==self.revision:return
        self.snapshot=snapshot;self.revision=snapshot.get('revision');self.scroll=0
        rows=tuple(reversed(snapshot.get('history') or ()))
        self.history.replace(tuple(str(row.get('kind','job'))+' · '+str(row.get('status','unknown')) for row in rows),tuple(row['id'] for row in rows))

    def invoke(self,index):
        if index==1:
            if not self.path.text.strip():self.notice='Enter a local file path first';return
            self.mode='result';self.command('select',self.path.text.strip())
        elif index==4:
            try:tone=float(self.tone.text);wpm=float(self.wpm.text)
            except ValueError:self.notice='Tone and speed must be numbers';return
            self.mode='result';self.command('run_cw',tone=tone,wpm=wpm)
        elif index==5:self.command('cancel')
        elif index==6:self.mode='result';self.command('refresh_evidence');self.layout.select('result')
        elif index==7:self.mode='history';self.history.index=0;self.layout.select('result')

    def key(self,key):
        if self.layout.focus=='result' and self.mode=='history' and self.history.search_key(key):return True
        if key in ('\t','backtab'):self.layout.cycle(-1 if key=='backtab' else 1);return True
        if self.layout.focus=='file':
            if key in ('up','down'):return self.controls.key(key)
            index=self.controls.index
            if key in ('\r','\n'):
                self.invoke(1 if index==0 else 4 if index in (2,3) else index);return True
            if index in (0,2,3):return {0:self.path,2:self.tone,3:self.wpm}[index].key(key)
        elif self.mode=='history':
            if key in ('\r','\n'):
                if self.history.rows:
                    rows=tuple(reversed(self.snapshot.get('history') or ()))
                    self.mode='result';self.command('load_result',rows[self.history.index]['id'])
                return True
            if key in ('escape','\x1b'):self.mode='result';return True
            return self.history.key(key)
        elif key in ('up','down','pageup','pagedown','home'):
            self.scroll=0 if key=='home' else max(0,self.scroll+(-1 if key in ('up','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1));return True
        return False

    def pointer(self,column,row,width,button=0,released=False):
        if released or button&32:return False
        if button==0:
            for x,y,w,kind,value in self._hits:
                if y==row and x<=column<x+w:
                    if kind=='pane':self.layout.select(value)
                    elif kind=='control':
                        self.layout.select('file');self.controls.index=value
                        if value not in (0,2,3):self.invoke(value)
                    return True
        for key,(x,y,w,h) in self._rects.items():
            if x<=column<x+w and y<=row<y+h:
                self.layout.select(key)
                if button&64:return self.key('down' if button&1 else 'up')
                if key=='result' and self.mode=='history' and row>y and button==0:
                    return self.history.pointer_at(column-x,row-y-1,w,max(1,h-1))
                return button==0
        return False

    def body(self,width):
        cache_key=(self.revision,width)
        if cache_key==self._body_key:return self._body
        body=DetailBlock(width);state=self.snapshot;result=state.get('result') or {}
        report=(result.get('report') or {}).get('result') if result.get('kind')=='history' else result
        report=report or {}
        selected=(report.get('input') or report.get('metadata')) if result.get('kind')=='history' else state.get('selected')
        if result.get('kind')=='history':body.section('Retained result')
        if selected:
            body.section(selected.get('name') or 'Selected file')
            for label,key in (('Format','kind'),('Bytes','bytes'),('Rate Hz','sample_rate'),('Channels','channels'),('Seconds','seconds')):
                if key in selected:body.field(label,selected[key])
            body.text('CW ready · 8 kHz mono S16' if selected.get('cw_supported') else selected.get('note') or 'Inspection only','status')
        if report.get('text') is not None:
            body.section('Decoded candidates');body.text(report.get('text') or 'No text candidates');body.text('Unverified offline analysis','muted')
        for entry in report.get('items') or ():
            body.section(str(entry.get('title') or entry.get('id') or 'Evidence'))
            body.text(entry.get('text') or entry.get('error') or entry.get('status') or 'Unavailable')
        if state.get('error'):body.section('Job failed');body.text(state['error'],'warning')
        if state.get('persistence_error'):body.section('History could not be saved');body.text(state['persistence_error'],'warning')
        if not selected and not result and not state.get('error'):
            body.section('Local analysis');body.text('Inspect a file, replay a supported WAV, or reopen a retained result.')
            body.section('CW replay');body.text('8 kHz · mono · 16-bit PCM WAV. File inspection and decoding run in the application worker.')
        if state.get('history'):body.field('History',str(len(state['history']))+' retained jobs')
        self._body_key=cache_key;self._body=body;return body

    def lines(self):
        c=Canvas(self.width,self.height);self._hits=[];state=self.snapshot
        c.put(0,0,'Workbench · local files & analysis');c.role(0,0,self.width,'toolbar')
        status=state.get('status','unavailable');progress=state.get('progress') or {};fraction=progress.get('fraction')
        label=status.capitalize()+(' · '+str(progress.get('kind')) if progress.get('kind') else '')
        if fraction is not None:label+=' · '+str(round(100*fraction))+'%'
        c.put(0,1,label);c.role(0,1,self.width,'status')
        raw=self.layout.layout(self.width,max(1,self.height-4));self._rects={key:(x,y+2,w,h) for key,(x,y,w,h) in raw.items()}
        if self.layout.tabbed:
            x=0
            for panel in self.layout.panels:
                label=('['+panel.title+']') if panel.key==self.layout.focus else panel.title
                c.put(x,2,label);c.role(x,2,len(label),'control');self._hits.append((x,2,len(label),'pane',panel.key));x+=len(label)+2
        else:c.divider(raw['file'][2],2,max(1,self.height-4))
        for key,(x,y,w,h) in self._rects.items():
            c.pane(x,y,w,h,'File & jobs' if key=='file' else 'Job history' if self.mode=='history' else 'Results',self.layout.focus==key,inset=key=='file')
            if key=='file':
                labels=('Path: '+self.path.text,'[ Inspect file ]','Tone Hz: '+self.tone.text,'WPM: '+self.wpm.text,'[ Run CW replay ]','[ Cancel job ]','[ Refresh evidence ]','[ Open retained result ]')
                for index,label in enumerate(labels):
                    row=y+1+index
                    if row>=y+h:break
                    if index in (0,2,3) and self.controls.index==index and self.layout.focus=='file':
                        prefix,field={0:('Path: ',self.path),2:('Tone Hz: ',self.tone),3:('WPM: ',self.wpm)}[index]
                        label=prefix+field.draw(max(1,w-len(prefix)))
                    c.put(x,row,label[-w:] if index==0 else label,w);c.role(x,row,w,'selected' if self.controls.index==index and self.layout.focus=='file' else 'control' if index not in (0,2,3) else 'body');self._hits.append((x,row,w,'control',index))
            elif self.mode=='history':
                self.history.draw(c,x,y+1,w,max(1,h-1))
                if not self.history.rows:c.put(x,y+1,'No retained jobs yet',w)
            else:self.scroll=self.body(w).draw(c,x,y+1,w,max(1,h-1),self.scroll)
        c.put(0,self.height-2,self.notice or 'Offline · select a file explicitly · no capture');c.role(0,self.height-2,self.width,'warning' if self.notice else 'muted')
        c.put(0,self.height-1,'Tab pane · ↑↓ choose/scroll · Enter activate');c.role(0,self.height-1,self.width,'control')
        self._spans=c.styled_spans();return c.lines()

    def spans(self):return self._spans
