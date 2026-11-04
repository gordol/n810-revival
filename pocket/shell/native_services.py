"""Read-only native service discovery over the existing bounded receive model."""
import importlib.util
from pathlib import Path
import textwrap
import time_display
from app_widgets import AdaptivePanels, Canvas, PanelSpec, SelectList, status_text, connection_summary, Column, Columns, DetailBlock


def load_model():
    root=Path(__file__).resolve().parent
    path=root/'vendor/packet-console/n810-services-model.py'
    spec=importlib.util.spec_from_file_location('native_services_model',path)
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    return model


class Services:
    """Provider returns retained decoded lines or an existing model State plus metadata."""
    actions=(('e','Toggle evidence'),)
    tabs=('Advertisements','Station packets','Message clues')
    def help_pages(self):
        from app_help_content import pages
        return pages('Services')
    def __init__(self,provider,call='N0ANT',model=None):
        self.provider=provider;self.model=model or load_model();self.state=self.model.State(call)
        self.width=76;self.height=25;self.evidence=False;self.tab=0;self.rows=();self.list=SelectList(());self.scroll=0
        self.layout=AdaptivePanels((PanelSpec('list','Discovery',24,44),PanelSpec('details','Details',28,42)))
        self._detail_length=0
        self._empty_payload={};self._update_token=None;self._source_token=None;self._source_payload=None;self.metadata={};self.error=None;self._spans=[];self._hits=[];self._tab_hits=[];self._identity=None
        self.list.column_layout=Columns((Column('Station',10,'heading'),Column('MHz',8,'control'),Column('Clues',12,'body')))
    def update(self):
        try:
            data=self.provider()
            if data is None:data=self._empty_payload
            source_token=(id(data),data.get('revision'))
            token=(source_token,self.tab)
            if token==self._update_token:return
            self.metadata=data
            if source_token!=self._source_token:
                if data.get('state') is not None:self.state=data['state']
                else:
                    for line in data.get('lines',()):self.state.add(line)
                self._source_token=source_token;self._source_payload=data
            rows=tuple(self.state.rows(self.tab));ids=tuple(self.identity(r) for r in rows)
            selected=self._identity
            self.rows=rows;self.list.column_values=tuple(self.columns(row) for row in rows);self.list.replace(tuple(r.get('entity',r['call'])+' · '+self.model.summary(r) for r in rows),ids)
            self.list.index=ids.index(selected) if selected in ids else min(self.list.index,max(0,len(rows)-1))
            self._identity=ids[self.list.index] if ids else None;self.error=None;self._update_token=token
        except (OSError,ValueError,TypeError,KeyError) as error:self.error=str(error)
    @staticmethod
    def columns(row):
        frequencies=', '.join(row.get('frequencies') or ()) or '—'
        kind=('MSG → '+row.get('to','')) if row.get('kind')=='MSG' else row.get('kind') or ', '.join(row.get('hints') or ()) or 'Station'
        return row.get('entity') or row['call'],frequencies,kind
    @staticmethod
    def identity(row):return row.get('entity',row['call']) if 'kind' not in row else row['raw']
    def select(self):
        identity=self.identity(self.rows[self.list.index]) if self.rows else None
        if identity!=self._identity:self.scroll=0
        self._identity=identity
    def key(self,key):
        self.update()
        if (self.layout.resizing or key=='\x12' and not self.list.searching) and self.layout.split_key(key,self.width):return True
        if self.layout.focus=='list' and self.list.search_key(key):
            self.select();return True
        if key in ('\t','backtab'):self.layout.cycle(-1 if key=='backtab' else 1)
        elif key=='e':self.evidence=not self.evidence;self.scroll=0;self.layout.select('details')
        elif key in ('left','right'):
            self.tab=(self.tab+(-1 if key=='left' else 1))%len(self.tabs);self._identity=None;self.scroll=0;self.update()
        elif key in ('\r','\n'):self.layout.select('details')
        elif self.layout.focus=='details' and key in ('up','down','j','k','pageup','pagedown','home','end'):
            if key=='home':self.scroll=0
            elif key=='end':self.scroll=self._detail_length
            else:self.scroll=max(0,self.scroll+(-1 if key in ('up','k','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1))
        elif self.layout.focus=='list' and self.list.key(key):self.select()
        elif key=='f5':pass
        else:return False
        return True
    def pointer(self,column,row,width,button=0,released=False):
        if self.layout.split_pointer(column,row,width,button,released,top=3,bottom=self.height-2):return True
        if released or button&32:return False
        if button&64:
            for x,y,w,h,key in self._hits:
                if x<=column<x+w and y<=row<y+h:
                    if key=='list':self.list.scroll(3 if button&1 else -3,max(1,h-1))
                    else:self.scroll=max(0,self.scroll+(1 if button&1 else -1))
                    return True
            return False
        if button!=0:return False
        for x,length,index in self._tab_hits:
            if row==0 and x<=column<x+length:self.tab=index;self._identity=None;self.scroll=0;self.update();return True
        for x,y,w,h,key in self._hits:
            if x<=column<x+w and y<=row<y+h:
                self.layout.select(key)
                if key=='list' and row>y:
                    if self.list.pointer_at(column-x,row-y-1,w,max(1,h-1)):self.select()
                return True
        if row==3 and self.layout.tabbed:
            x=0
            for panel in self.layout.panels:
                label='['+panel.title+']' if panel.key==self.layout.focus else panel.title
                if x<=column<x+len(label):self.layout.select(panel.key);return True
                x+=len(label)+2
        return False
    @property
    def pointer_captured(self):return self.layout.pointer_captured
    @property
    def resizing(self):return self.layout.resizing
    def cancel_pointer(self):self.layout.cancel_pointer()
    def bind_session(self,callback):self.layout.bind_session(callback)
    def session_state(self):return dict(panels=self.layout.session_state())
    def restore_session(self,state):
        if isinstance(state,dict):self.layout.restore_session(state.get('panels',{}))
    def lines(self):
        self.update();c=Canvas(self.width,self.height);self._spans=[(0,0,self.width,'toolbar')];self._hits=[];self._tab_hits=[]
        x=0
        for i,title in enumerate(self.tabs):
            label='['+title+']' if i==self.tab else ' '+title+' '
            c.put(x,0,label);c.role(x,0,len(label),'tab' if i==self.tab else 'muted');self._tab_hits.append((x,len(label),i));x+=len(label)+1
        c.put(0,1,status_text(connection_summary(self.metadata),str(self.metadata.get('source') or 'Receive source unknown')+' · '+str(self.metadata.get('freshness') or 'Freshness unknown'),self.width))
        c.role(0,1,self.width,'muted')
        c.role(0,2,self.width,'warning' if self.error or self.metadata.get('error') else 'muted')
        c.role(0,self.height-1,self.width,'muted')
        c.put(0,2,'Unavailable' if self.error else str(len(self.rows))+' received entries')
        rects=self.layout.layout(self.width,max(1,self.height-5))
        if self.layout.tabbed:c.put(0,3,'  '.join('['+p.title+']' if p.key==self.layout.focus else p.title for p in self.layout.panels))
        if not self.layout.tabbed:c.divider(rects['list'][2],3,max(1,self.height-5))
        for key,(x,y,w,h) in rects.items():
            y+=3;self._hits.append((x,y,w,h,key));c.pane(x,y,w,h,'Advertisement clues' if key=='list' and self.tab==0 else 'Received packets' if key=='list' else 'Selected packet',key==self.layout.focus,inset=key=='list')
            if key=='list':
                self.list.draw(c,x,y+1,w,max(1,h-1))
                if self.list.visible_selection is not None:self._spans.append((y+1+self.list.visible_selection,x,w,'selected'))
                if not self.rows:c.put(x,y+1,'No retained entries',w)
            elif self.rows:
                row=self.rows[self.list.index];body=DetailBlock(w)
                body.section(row.get('entity') or row['call'])
                fields=self.model.fields(row) if hasattr(self.model,'fields') else [('Summary',self.model.summary(row))]
                for label,value in fields:
                    if label=='Station' or not self.evidence and label in ('Path','AX.25 dest'):continue
                    if label=='Packet time':
                        original=self.metadata.get('packet_times',{}).get(row['raw'])
                        value=time_display.full(original) if original else str(value)+' · date/zone unknown'
                    kind='frequency' if label=='Frequency' else 'time' if label=='Packet time' else 'path' if label in ('Path','AX.25 dest') else 'text'
                    body.field(label,value,kind)
                if self.evidence:
                    body.section('Original packet');body.text(row['raw'],'muted')
                else:
                    body.text('');body.text('e  Original packet and route','control')
                if self.metadata.get('error'):body.section('Connection');body.text(self.metadata['error'],'warning')
                self._detail_length=len(body.lines);self.scroll=body.draw(c,x,y+1,w,max(1,h-1),self.scroll)
            else:c.put(x,y+1,'Select a received entry',w)
        c.put(0,self.height-1,'←/→ resize split · Enter done · Esc cancel' if self.layout.resizing else '←/→ category  Tab pane  ↑/↓ browse · e evidence · Ctrl-R split')
        self._spans=c.styled_spans(self._spans)
        return c.lines()
    def spans(self):return tuple(self._spans)
