"""Read-only native agenda using the existing recurrence and observation model."""
import datetime as dt
import time_display
import importlib.util
from pathlib import Path
import textwrap
from app_widgets import AdaptivePanels, Canvas, PanelSpec, SelectList, status_text, connection_summary


def load_model():
    root=Path(__file__).resolve().parent
    path=root/'vendor/packet-console/n810-nets-model.py'
    spec=importlib.util.spec_from_file_location('native_nets_model',path)
    model=importlib.util.module_from_spec(spec);spec.loader.exec_module(model)
    return model


class Nets:
    """Provider supplies actual schedule data, existing settings and source metadata."""
    tabs=('Week','Today','Heard')
    def __init__(self,provider,clock=None,model=None):
        self.provider=provider;self.model=model or load_model();self.clock=clock or (lambda:dt.datetime.now(dt.timezone.utc))
        self.width=76;self.height=25;self.tab=0;self.rows=();self.list=SelectList(());self.scroll=0;self._identity=None
        self.layout=AdaptivePanels((PanelSpec('agenda','Agenda',28,34),PanelSpec('details','Selected net',30,42)))
        self._empty_payload={};self._update_token=None;self._source_token=None;self._source_payload=None;self.metadata={};self.error=None;self._spans=[];self._hits=[];self._tab_hits=[];self.lead=0;self.available=False
    @staticmethod
    def identity(row):return row.get('occurrence') or row['id']
    @staticmethod
    def label(row):
        local=row.get('local')
        when=(time_display.displayed(local) or local).strftime('%a %H:%M %Z') if local else 'Unverified'
        return when+' · '+str(row.get('name') or row.get('call') or 'Unknown net')
    def update(self):
        try:
            data=self.provider()
            if data is None:data=self._empty_payload
            now=self.clock();source_token=(id(data),data.get('revision'))
            token=(source_token,self.tab,int(now.timestamp()//60),time_display.ZONE)
            if token==self._update_token:return
            self.metadata=data;self._source_payload=data;self.available=isinstance(data.get('data'),dict)
            self.lead,enabled,confirmed,sent,heard=self.model.restore(data.get('settings') or {})
            for line in data.get('lines',()):
                observation=self.model.cal.announcement(line)
                if observation:self.model.observe(heard,observation)
            _,rows=self.model.agenda(data.get('data') or {'nets':[]},confirmed,heard,enabled,now,heard=self.tab==2,today=self.tab==1)
            ids=tuple(self.identity(row) for row in rows);selected=self._identity
            self.rows=tuple(rows);self.list.replace(tuple(self.label(row) for row in rows),ids)
            self.list.index=ids.index(selected) if selected in ids else min(self.list.index,max(0,len(rows)-1))
            self._identity=ids[self.list.index] if ids else None;self.error=None;self._update_token=token
        except (OSError,ValueError,TypeError,KeyError) as error:self.error=str(error)
    def select(self):
        identity=self.identity(self.rows[self.list.index]) if self.rows else None
        if identity!=self._identity:self.scroll=0
        self._identity=identity
    def key(self,key):
        self.update()
        if self.layout.focus=='agenda' and self.list.search_key(key):
            self.select();return True
        if key in ('\t','backtab'):self.layout.cycle(-1 if key=='backtab' else 1)
        elif key in ('left','right'):
            self.tab=(self.tab+(-1 if key=='left' else 1))%len(self.tabs);self._identity=None;self.scroll=0;self.update()
        elif key in ('\r','\n'):self.layout.select('details')
        elif self.layout.focus=='details' and key in ('up','down','pageup','pagedown','home'):
            self.scroll=0 if key=='home' else max(0,self.scroll+(-1 if key in ('up','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1))
        elif self.layout.focus=='agenda' and self.list.key(key):self.select()
        elif key=='f5':pass
        else:return False
        return True
    def pointer(self,column,row,width,button=0,released=False):
        if released or button&32:return False
        if button&64:
            for x,y,w,h,key in self._hits:
                if x<=column<x+w and y<=row<y+h:
                    if key=='agenda':self.list.scroll(3 if button&1 else -3,max(1,h-1))
                    else:self.scroll=max(0,self.scroll+(1 if button&1 else -1))
                    return True
            return False
        if button!=0:return False
        for x,length,index in self._tab_hits:
            if row==0 and x<=column<x+length:self.tab=index;self._identity=None;self.scroll=0;self.update();return True
        for x,y,w,h,key in self._hits:
            if x<=column<x+w and y<=row<y+h:
                self.layout.select(key)
                if key=='agenda' and row>y:
                    if self.list.pointer_at(column-x,row-y-1,w,max(1,h-1)):self.select()
                return True
        if row==3 and self.layout.tabbed:
            x=0
            for panel in self.layout.panels:
                label='['+panel.title+']' if panel.key==self.layout.focus else panel.title
                if x<=column<x+len(label):self.layout.select(panel.key);return True
                x+=len(label)+2
        return False
    def details(self,row):
        result=[str(row.get('name') or row.get('call') or 'Unknown net')]
        if row.get('local'):
            result += [(time_display.displayed(row['local']) or row['local']).strftime('%A %d %b %Y · %H:%M %Z'),'Schedule time: '+row['local'].strftime('%H:%M %Z'),str(row.get('frequency_mhz','Unknown'))+' MHz · '+str(row.get('mode') or 'Mode unknown'),
                       'Reminder: '+('subscribed in existing owner' if row.get('reminders') else 'off')]
        else:result += ['Time unverified · may be replayed',str(row.get('text') or 'No announcement text')]
        result += ['','Source: '+str(row.get('source') or row.get('call') or 'Unknown'),str(row.get('source_url') or ''),
                   'Checked: '+str(row.get('checked') or 'Unknown'),str(row.get('notes') or '')]
        if row.get('raw'):result += ['','Original announcement',row['raw']]
        return result
    def lines(self):
        self.update();c=Canvas(self.width,self.height);self._spans=[(0,0,self.width,'toolbar')];self._hits=[];self._tab_hits=[]
        x=0
        for i,title in enumerate(self.tabs):
            label='['+title+']' if i==self.tab else ' '+title+' '
            c.put(x,0,label);c.role(x,0,len(label),'tab' if i==self.tab else 'muted');self._tab_hits.append((x,len(label),i));x+=len(label)+1
        c.put(0,1,status_text(connection_summary(self.metadata),str(self.metadata.get('source') or 'Schedule source unknown')+' · '+str(self.metadata.get('freshness') or 'Freshness unknown'),self.width))
        c.put(0,2,self.error or self.metadata.get('status') or ('Read-only agenda · reminder delivery remains with existing Nets app' if self.available else 'Schedule unavailable · retained announcements only'))
        rects=self.layout.layout(self.width,max(1,self.height-5))
        if self.layout.tabbed:c.put(0,3,'  '.join('['+p.title+']' if p.key==self.layout.focus else p.title for p in self.layout.panels))
        c.role(0,1,self.width,'muted');c.role(0,2,self.width,'warning' if self.error or self.metadata.get('error') else 'muted');c.role(0,self.height-1,self.width,'muted')
        if not self.layout.tabbed:c.divider(rects['agenda'][2],3,max(1,self.height-5))
        for key,(x,y,w,h) in rects.items():
            y+=3;self._hits.append((x,y,w,h,key));c.pane(x,y,w,h,'Agenda' if key=='agenda' else 'Selected net',key==self.layout.focus,inset=key=='agenda')
            if key=='agenda':
                self.list.draw(c,x,y+1,w,max(1,h-1))
                if self.list.visible_selection is not None:self._spans.append((y+1+self.list.visible_selection,x,w,'selected'))
                if not self.rows:c.put(x,y+1,'No retained nets in this view',w)
            elif self.rows:
                body=[]
                for line in self.details(self.rows[self.list.index]):body.extend(textwrap.wrap(line,max(1,w)) or [''])
                self.scroll=min(self.scroll,max(0,len(body)-max(1,h-1)))
                for n,line in enumerate(body[self.scroll:self.scroll+max(1,h-1)],y+1):c.put(x,n,line,w)
            else:c.put(x,y+1,'Select a scheduled net or announcement',w)
        c.put(0,self.height-1,'←/→ view  Tab pane  ↑/↓ select/scroll  Enter details')
        self._spans=c.styled_spans(self._spans)
        return c.lines()
    def spans(self):return tuple(self._spans)
