"""Read-only saved walk sessions and probe evidence from the existing catalog."""
import textwrap
from app_widgets import AdaptivePanels, Canvas, PanelSpec, SelectList, status_text, connection_summary


class Walk:
    """Provider returns retained catalog walks, source, freshness and optional revision."""
    def __init__(self,provider):
        self.provider=provider;self.width=86;self.height=26
        self.layout=AdaptivePanels((PanelSpec('sessions','Sessions',22,26),PanelSpec('probes','Probes',23,28),PanelSpec('details','Evidence',28,38)))
        self.sessions=SelectList(());self.probes=SelectList(());self.walks=();self.probe_rows=()
        self.metadata={};self.error=None;self.scroll=0;self._token=None;self._payload=None;self._empty={}
        self._session_id=None;self._probe_id=None;self._hits=[];self._tabs=[];self._spans=[];self.positions=0
    @staticmethod
    def session_id(walk):return walk.get('file'),tuple(walk.get('files') or ())
    @staticmethod
    def probe_id(probe):return probe.get('number'),probe.get('time'),probe.get('payload')
    def update(self):
        try:
            data=self.provider()
            if data is None:data=self._empty
            token=(id(data),data.get('revision'))
            if token==self._token:return
            walks=tuple(data.get('walks') or ())
            ids=tuple(self.session_id(walk) for walk in walks)
            self.walks=walks;self.metadata=data;self.sessions.replace(tuple(str(w.get('file') or 'Unnamed session') for w in walks),ids)
            self.sessions.index=ids.index(self._session_id) if self._session_id in ids else min(self.sessions.index,max(0,len(walks)-1))
            self.choose_session();self.error=None;self._payload=data;self._token=token
        except (OSError,ValueError,TypeError,KeyError) as error:self.error=str(error)
    def choose_session(self):
        walk=self.walks[self.sessions.index] if self.walks else {}
        identity=self.session_id(walk)
        if identity!=self._session_id:self.scroll=0;self._probe_id=None;self.probes.index=0;self.probes.offset=0
        self._session_id=identity
        rows=walk.get('rows') or ()
        self.positions=sum(1 for row in rows if row.get('type')=='position')
        self.probe_rows=tuple(row['probe'] for row in rows if row.get('type')=='submission' and isinstance(row.get('probe'),dict))
        ids=tuple(self.probe_id(probe) for probe in self.probe_rows)
        self.probes.replace(tuple('#'+str(p.get('number','?'))+' · '+str(p.get('status') or 'Return evidence unknown') for p in self.probe_rows),ids)
        self.probes.index=ids.index(self._probe_id) if self._probe_id in ids else min(self.probes.index,max(0,len(ids)-1))
        self.choose_probe()
    def choose_probe(self):
        identity=self.probe_id(self.probe_rows[self.probes.index]) if self.probe_rows else None
        if identity!=self._probe_id:self.scroll=0
        self._probe_id=identity
    def key(self,key):
        self.update();focus=self.layout.focus
        listing=self.sessions if focus=='sessions' else self.probes if focus=='probes' else None
        if listing is not None and listing.search_key(key):
            (self.choose_session if focus=='sessions' else self.choose_probe)();return True
        if key in ('\t','backtab'):self.layout.cycle(-1 if key=='backtab' else 1)
        elif key in ('\r','\n'):self.layout.cycle()
        elif focus=='details' and key in ('up','down','pageup','pagedown','home'):
            self.scroll=0 if key=='home' else max(0,self.scroll+(-1 if key in ('up','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1))
        elif focus=='sessions' and self.sessions.key(key):self.choose_session()
        elif focus=='probes' and self.probes.key(key):self.choose_probe()
        elif key=='f5':self._token=None;self.update()
        else:return False
        return True
    def pointer(self,column,row,width,button=0,released=False):
        if released or button&32:return False
        if button&64:
            for x,y,w,h,key in self._hits:
                if x<=column<x+w and y<=row<y+h:
                    if key in ('sessions','probes'):(self.sessions if key=='sessions' else self.probes).scroll(3 if button&1 else -3,max(1,h-1))
                    else:self.scroll=max(0,self.scroll+(1 if button&1 else -1))
                    return True
            return False
        if button!=0:return False
        for x,length,key in self._tabs:
            if row==3 and x<=column<x+length:self.layout.select(key);return True
        for x,y,w,h,key in self._hits:
            if x<=column<x+w and y<=row<y+h:
                self.layout.select(key)
                if row>y and key=='sessions':
                    if self.sessions.pointer_at(column-x,row-y-1,w,max(1,h-1)):self.choose_session()
                elif row>y and key=='probes':
                    if self.probes.pointer_at(column-x,row-y-1,w,max(1,h-1)):self.choose_probe()
                return True
        return False
    def details(self):
        if not self.walks:return ['No saved session selected.']
        walk=self.walks[self.sessions.index];session=next((r for r in walk.get('rows',()) if r.get('type')=='session'),{})
        body=['Saved session: '+str(session.get('tag') or walk.get('file') or 'Unknown'),
              'Started: '+str(session.get('time') or 'Unknown'), 'Ended: '+str(walk.get('end') or 'Unknown'),
              'Position samples: '+str(self.positions), 'Recorded probes: '+str(len(self.probe_rows))]
        body+=['File: '+str(f) for f in (walk.get('files') or ([walk['file']] if walk.get('file') else []))]
        if not self.probe_rows:return body+['','No recorded probe evidence.','Saved history does not restore arming.']
        probe=self.probe_rows[self.probes.index]
        body+=['','Probe #'+str(probe.get('number','?')),'Recorded time: '+str(probe.get('time') or 'Unknown'),
               'Evidence: '+str(probe.get('status') or 'Return evidence unknown')]
        position=probe.get('position') or {}
        if 'lat' in position and 'lon' in position:
            body+=['Probe position: '+str(position['lat'])+', '+str(position['lon'])]
            if 'accuracy' in position:body+=['Recorded accuracy: '+str(position['accuracy'])]
        else:body+=['Probe position: Unknown']
        if probe.get('return_path'):body+=['Observed repeated-copy path: '+str(probe['return_path'])]
        for report in probe.get('internet_reports') or ():
            body+=['Internet report via: '+str(report.get('gate') or 'Unknown'),
                   'Report provenance: '+str(report.get('provenance') or 'Unknown'),
                   'Report time: '+str(report.get('time') or 'Unknown')]
        body+=['','Original probe payload',str(probe.get('payload') or 'Unknown'),'',
               'Repeated copies and Internet reports are distinct evidence.','No route, coverage or line-of-sight is inferred.']
        return body
    def lines(self):
        self.update();c=Canvas(self.width,self.height);self._hits=[];self._tabs=[];self._spans=[(0,0,self.width,'toolbar')]
        c.put(0,0,'Walk history · saved sessions')
        c.put(0,1,status_text(connection_summary(self.metadata),str(self.metadata.get('source') or 'History source unknown')+' · '+str(self.metadata.get('freshness') or 'Freshness unknown'),self.width))
        c.put(0,2,self.error or 'Read-only evidence · no live probe or transmit controls')
        rects=self.layout.layout(self.width,max(1,self.height-5))
        if self.layout.tabbed:
            x=0
            for panel in self.layout.panels:
                label='['+panel.title+']' if panel.key==self.layout.focus else panel.title
                c.put(x,3,label);self._tabs.append((x,len(label),panel.key));x+=len(label)+2
        for key,(x,y,w,h) in rects.items():
            y+=3;self._hits.append((x,y,w,h,key));title=next(p.title for p in self.layout.panels if p.key==key)
            c.pane(x,y,w,h,title,key==self.layout.focus,inset=key in ('sessions','probes'))
            if key in ('sessions','probes'):
                listing=self.sessions if key=='sessions' else self.probes
                listing.draw(c,x,y+1,w,max(1,h-1))
                if listing.visible_selection is not None:self._spans.append((y+1+listing.visible_selection,x,w,'selected'))
                if not listing.rows:c.put(x,y+1,'No saved sessions' if key=='sessions' else 'No recorded probes',w)
            else:
                body=[]
                for line in self.details():body.extend(textwrap.wrap(line,max(1,w)) or [''])
                self.scroll=min(self.scroll,max(0,len(body)-max(1,h-1)))
                for n,line in enumerate(body[self.scroll:self.scroll+max(1,h-1)],y+1):c.put(x,n,line,w)
        c.put(0,self.height-1,'Tab pane  ↑/↓ select/scroll  Enter next pane')
        c.role(0,1,self.width,'muted');c.role(0,2,self.width,'muted');c.role(0,self.height-1,self.width,'muted')
        self._spans=c.styled_spans(self._spans)
        return c.lines()
    def spans(self):return tuple(self._spans)
