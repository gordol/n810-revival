"""Bounded view of committed owner Directory events from the existing client writer."""
from app_widgets import AdaptivePanels,PanelSpec,Canvas,SelectList,DetailBlock,Column,Columns
import time_display


class Heard:
    def __init__(self,provider):
        self.provider=provider;self.width=92;self.height=28;self.metadata={};self.rows=();self.selected=None;self.scroll=0;self.token=None
        self.layout=AdaptivePanels((PanelSpec('events','Additions',28,48),PanelSpec('details','Observation',28,44)))
        self.list=SelectList(());self.list.column_layout=Columns((Column('Capture',8,'muted'),Column('Station',10,'heading'),Column('Observation',16,'body')))
        self._spans=();self._rects={};self._detail_length=0
    def update(self):
        data=self.provider() or {};self.metadata=data;events=data.get('events') or ();token=(data.get('revision'),time_display.ZONE)
        if token==self.token:return
        self.token=token
        if not isinstance(events,(list,tuple)):events=()
        self.rows=tuple(row for row in events[-200:] if isinstance(row,dict) and row.get('type')=='directory.observation_added' and isinstance(row.get('id'),str))[::-1]
        ids=tuple(row['id'] for row in self.rows);self.list.column_values=tuple((time_display.clock(row.get('captured_at')),str(row.get('call') or '?'),str(row.get('summary') or '')) for row in self.rows)
        self.list.replace(tuple(' '.join(values) for values in self.list.column_values),ids)
        if self.selected not in ids:self.selected=ids[0] if ids else None;self.scroll=0
        self.list.index=ids.index(self.selected) if self.selected in ids else 0
    def choose(self):
        selected=self.rows[self.list.index]['id'] if self.rows else None
        if selected!=self.selected:self.scroll=0
        self.selected=selected
    def record(self):return next((row for row in self.rows if row['id']==self.selected),None)
    def selected_entities(self):
        from entity_actions import EntityRef
        row=self.record();return (EntityRef('station',row['call']),) if row and row.get('call') else ()
    def entities_at(self,column,row):
        from entity_actions import EntityRef
        self.update();record=None
        for key,(x,y,w,h) in self._rects.items():
            if x<=column<x+w and y<row<y+h:
                if key=='events':
                    index=self.list.offset+row-y-1
                    if 0<=index<len(self.rows) and not (self.list.has_scrollbar(w) and column==x+w-1):record=self.rows[index]
                else:record=self.record()
        return (EntityRef('station',record['call']),) if record and record.get('call') else ()
    def key(self,key):
        self.update()
        if self.layout.focus=='events' and self.list.search_key(key):self.choose();return True
        if key in ('\t','backtab'):self.layout.cycle(-1 if key=='backtab' else 1)
        elif key in ('\r','\n'):self.layout.select('details')
        elif self.layout.focus=='events' and self.list.key({'j':'down','k':'up'}.get(key,key)):self.choose()
        elif self.layout.focus=='details' and key in ('up','down','pageup','pagedown','home','end'):
            self.scroll=0 if key=='home' else self._detail_length if key=='end' else max(0,self.scroll+(-1 if key in ('up','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1))
        else:return False
        return True
    def pointer(self,column,row,width,button=0,released=False):
        if released or button&32:return False
        if button==0 and self.layout.tabbed and row==3:
            x=0
            for panel in self.layout.panels:
                label=('['+panel.title+']') if panel.key==self.layout.focus else panel.title
                if x<=column<x+len(label):self.layout.select(panel.key);return True
                x+=len(label)+2
        for key,(x,y,w,h) in self._rects.items():
            if x<=column<x+w and y<=row<y+h:
                if button&64:
                    if key=='events':self.list.scroll(3 if button&1 else -3,max(1,h-1))
                    else:self.scroll=max(0,self.scroll+(1 if button&1 else -1))
                elif button==0:
                    self.layout.select(key)
                    if key=='events' and row>y and self.list.pointer_at(column-x,row-y-1,w,max(1,h-1)):self.choose()
                else:return False
                return True
        return False
    def lines(self):
        self.update();self._detail_length=0;c=Canvas(self.width,self.height);c.put(0,0,'Client Directory additions');c.role(0,0,self.width,'toolbar')
        c.put(0,1,'Since desktop attachment · capture times may be historical');c.role(0,1,self.width,'muted')
        message=self.metadata.get('error') or (self.metadata.get('unavailable_reason') or 'Activity source unavailable' if not self.metadata.get('attached') else 'Source connected' if self.metadata.get('connected') else 'Source offline')
        if self.metadata.get('gap_possible'):message+=' · gap possible; no guaranteed catch-up'
        c.put(0,2,message);c.role(0,2,self.width,'warning' if self.metadata.get('error') or self.metadata.get('gap_possible') else 'status' if self.metadata.get('connected') else 'muted')
        selected_spans=[]
        raw=self.layout.layout(self.width,max(1,self.height-5));self._rects={key:(x,y+3,w,h) for key,(x,y,w,h) in raw.items()}
        if self.layout.tabbed:c.put(0,3,'  '.join('['+panel.title+']' if panel.key==self.layout.focus else panel.title for panel in self.layout.panels))
        if not self.layout.tabbed:c.divider(raw['events'][2],3,max(1,self.height-5))
        for key,(x,y,w,h) in self._rects.items():
            c.pane(x,y,w,h,'Recent additions' if key=='events' else 'Committed observation',key==self.layout.focus,inset=key=='events')
            if key=='events':
                self.list.draw(c,x,y+1,w,max(1,h-1))
                if self.list.visible_selection is not None:selected_spans.append((y+1+self.list.visible_selection,x,w,'selected'))
                if not self.rows:c.put(x,y+2,'No committed additions since attachment',w)
            else:
                row=self.record()
                if row:
                    body=DetailBlock(w);body.section(str(row.get('call') or 'Unknown station'))
                    body.field('Captured',time_display.full(row.get('captured_at')),'time');body.text(row.get('summary') or '')
                    body.field('Destination',row.get('destination') or 'Unknown');body.field('Packet type',row.get('packet_type') or 'Unknown')
                    for fact in (row.get('facts') or ())[:8]:body.field(str(fact.get('kind') or 'Fact'),str(fact.get('detail') or ''))
                    body.section('Evidence source');source=row.get('source') or {}
                    for label,value in (('Scope','Client Directory ingest'),('Kind',source.get('kind')),('Direction',source.get('direction')),('Origin',source.get('origin')),('RF origin',source.get('rf_origin')),('Directory ID',row['id'])):body.field(label,value or 'Unknown')
                    if row.get('used_relays'):body.field('Used relays',', '.join(row['used_relays']),'path');body.text('Used-address evidence only; no physical route inferred.','muted')
                    self._detail_length=len(body.lines)
                    self.scroll=body.draw(c,x,y+1,w,max(1,h-1),self.scroll)
        c.put(0,self.height-2,str(len(self.rows))+' retained additions · no replay or RF freshness guarantee');c.role(0,self.height-2,self.width,'muted')
        c.put(0,self.height-1,'Tab pane · ↑↓ select/scroll · / find · Enter details');c.role(0,self.height-1,self.width,'control')
        self._spans=c.styled_spans(selected_spans);return c.lines()
    def help_pages(self):
        return (('Browse directory additions', (
            'This view lists committed directory observations received since desktop attachment.',
            'Tab and Shift-Tab move between Additions and Observation.',
            'In Additions, Up/Down selects a record. / starts list search; Enter accepts the search.',
            'After accepting a search, n and N select the next and previous matches. Esc clears the search.',
            'Enter from the list focuses Observation. Up/Down scrolls the focused observation.',
            'Capture times describe the stored observations. The source status reports the current attachment.',
        )),)
    def spans(self):return self._spans
