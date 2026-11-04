"""Shared native presentation key policy. No transport, jobs, or domain rules."""
from collections import namedtuple
from app_widgets import AdaptivePanels,SelectList,TextInput,literal_spans

Target=namedtuple('Target','key,title,kind,action',defaults=(None,))


class Navigation:
    def __init__(self,form):
        self.form=form;self.target=None;self.inputs={};self.original=None;self.custom=None;self.scroll=0
    def page(self):
        f=self.form
        if type(f).__name__=='SceneryApp':return f.manager.pages[f.manager.category]
        return f.pages[f.category] if type(f).__name__=='SettingsManager' and f.category is not None else f
    def header(self):
        p=self.page()
        for labels,index in (('sections','section'),('tabs','tab'),('pages','page')):
            values=getattr(p,labels,None)
            if isinstance(values,(tuple,list)) and values and hasattr(p,index):
                return p,index,tuple(v[0] if labels=='sections' else v for v in values)
        if type(p).__name__=='RadioView':return p,'page',('On radio','Saved presets')
        if type(p).__name__=='DirectoryView':return p,'category',('All heard','Services','Relays')
        return None
    def layout(self):
        f=self.form
        declared=getattr(f,'navigation_layout',None)
        if callable(declared):return declared()
        p=f.memory_layout if type(f).__name__=='RadioManager' and f.page==1 else getattr(f,'layout',None)
        return p if isinstance(p,AdaptivePanels) else None
    def targets(self):
        f=self.form;name=type(f).__name__
        custom=getattr(f,'navigation_targets',None)
        if callable(custom):return custom()
        header=self.header();result=[Target('tabs','Tabs','tabs')] if header else []
        if name=='SettingsManager' and f.category is None:return [Target('filter','Category filter','input'),Target('categories','Settings categories','list')]
        if type(self.page()).__name__=='SettingsWindow':return result+[Target('item:'+str(i),row[0],'control') for i,row in enumerate(self.page().items)]+[Target('action:'+key,label,'action',key) for key,label in getattr(f,'actions',())]
        if name=='RadioManager':
            if f.page==0:return result+([Target('action:'+key,label,'action',key) for key,label in (('r','Read current status'),('c','Cancel read'),('k','Check read'))] if f.state.can_read else [])+[Target('content','Reported status','details')]
            if f.page==1:return result+[Target('pane:'+p.key,p.title,'details' if p.key=='details' else 'list') for p in f.memory_layout.panels]
            if f.page==2:return result+[Target('banks','Downloaded banks','list'),Target('action:p','Copy downloaded bank','action','p')]
            if f.page in (3,4):
                if not f.drafts:return result+[Target('content','Local drafts unavailable','details')]
                document=f.drafts.documents['banks' if f.page==3 else 'profiles']
                if document is None:return result+[Target('action:N','Create local draft','action','N')]
                result += [Target('bank','Local bank/profile','choice'),Target('memory','Local memories','list')]
                groups=f.draft_groups()
                if groups and groups[f.bank%len(groups)].get('channels'):result.append(Target('fields','Local fields','control'))
                labels={'S':'Save locally','D':'Discard local edits','e':'Edit fields','n':'New bank','r':'Rename bank','c':'Copy bank','a':'Add memory'}
                result += [Target('action:'+key,label,'action',key) for key,label in labels.items() if key not in ('n','r','c','a') or f.page==3]
                return result
        if name=='Stations':return [Target('stations','Stations','list'),Target('details','Station details','details'),Target('filter','Station filter','input')]
        if name=='RadioQuick':return [Target('groups','Downloaded groups','list'),Target('action:m','Open Radio Manager','action','m')]
        layout=self.layout()
        if layout:
            if name in ('CW','WorkbenchView'):
                fields=(('path','WAV path'),('tone','Tone Hz'),('wpm','Speed WPM'),(None,'Decode file')) if name=='CW' else (('path','File path'),(None,'Inspect file'),('tone','Tone Hz'),('wpm','Speed WPM'),(None,'Run CW replay'),(None,'Cancel job'),(None,'Refresh evidence'),(None,'Open retained result'))
                result += [Target(('input:'+key) if key else 'job:'+str(i),label,'input' if key else 'action',i) for i,(key,label) in enumerate(fields)]
                return result+[Target('pane:result','Results','list' if getattr(f,'mode',None)=='history' else 'details')]
            result += [Target('pane:'+p.key,p.title,'list' if p.key in ('items','threads','agenda','feed','events','sessions','probes','list','topics') else 'details') for p in layout.panels]
            actions=getattr(f,'actions',())
            if isinstance(actions,(tuple,list)):result += [Target('action:'+key,label,'action',key) for key,label in actions]
            return result
        if name=='Bluetooth':return [Target('action:'+key,label,'action',key) for key,label in (('1','Bluetooth on'),('0','Bluetooth off'),('r','Receive start'),('s','Receive stop'),('d','Disconnect radio'))]+[Target('content','Connected devices','details')]
        if name=='System':return result+[Target('content','System details','details')]+([Target('action:c','Connections','action','c')] if f.open_connections else [])+([Target('action:p','Review connection profiles','action','p')] if f.page==1 and f.links.current['profiles'] else [])
        if name=='LastHeard':return [Target('content','Station details','details'),Target('action:l','Last heard','action','l'),Target('action:s','Selected station','action','s')]
        if name=='RenderDebug':return [Target('content','Render measurements','details')]+[Target('action:'+key,label,'action',key) for key,label in (('s','Shadows'),('o','Opacity'),('n','Disable effects'),('r','Restore'))]
        if name=='AudioMonitor':return [Target('action:'+key,label,'action',key) for key,label in (('s','Source'),('r','Retry source'),('p','Playback'))]+[Target('content','Audio levels','details')]
        if name=='FontPreview':return [Target('family','Font family','choice'),Target('size','Font size','choice')]
        if name=='BirdView':return [Target('map','Terrain camera','map')]+[Target('action:'+key,label,'action',key) for label,key in f.actions()]
        if name=='StationMap':return [Target('map','Station map','map'),Target('action:F','Follow selected station','action','F'),Target('action:d','Stations','action','d')]
        if name=='DirectoryView':return result+[Target('content','Directory cards','list'),Target('filter','Directory filter','input')]
        if name=='NetsView':return [Target('month','Agenda month','choice'),Target('content','Agenda entries','list'),Target('details','Agenda details','details')]
        if name=='DetachedView':return [Target('content',f.name,'list' if f.name=='Packet Inspector' else 'details'),Target('action:\r','Reattach pane','action','\r')]
        if name=='CalendarView':return [Target('calendar','Calendar','choice')]
        if name=='SplitPane':return [Target('left','Navigation pane','details'),Target('divider','Pane divider','control')]+[Target('right:'+t.key,t.title,t.kind,t.action) for t in navigation(f.right).targets()]
        if name=='MapView':return [Target('map','Map','map'),Target('packets','Packets','list')]
        if name=='ChatView':return [Target('threads','Threads','list'),Target('history','Chat history','details'),Target('draft','Local draft','input')]
        return result+[Target('content',name.replace('View',''),'list' if hasattr(f,'selection') or hasattr(f,'table') else 'details')]
    def current(self):
        f=self.form;name=type(f).__name__;targets=self.targets();keys=[t.key for t in targets]
        layout=self.layout()
        if self.target and self.target.startswith('pane:') and layout and self.target!='pane:'+layout.focus:self.target='pane:'+layout.focus
        if self.target and self.target.startswith(('input:','job:')) and layout and layout.focus!='file':self.target='pane:'+layout.focus
        if self.target and self.target.startswith('item:') and type(self.page()).__name__=='SettingsWindow':self.target='item:'+str(self.page().index)
        if self.target in keys:return next(t for t in targets if t.key==self.target)
        if type(self.page()).__name__=='SettingsWindow':key='item:'+str(self.page().index)
        elif name=='SettingsManager':key='filter' if f.search_focus else 'categories'
        elif name=='Bluetooth':key='action:'+('1','0','r','s','d')[f.focus]
        elif name=='Stations':key='details' if f.focus else 'stations'
        elif name=='MapView':key='packets' if f.focus else 'map'
        elif name=='ChatView':key=('threads','history','draft')[f.focus]
        elif name=='SplitPane':key=('left','divider','right:'+navigation(f.right).current().key)[f.focus]
        elif self.layout():
            layout=self.layout();key='pane:'+layout.focus
            if name in ('CW','WorkbenchView') and layout.focus=='file':
                index=f.fields.index if name=='CW' else f.controls.index
                key=targets[index].key
        else:key=next((t.key for t in targets if t.key!='tabs'),targets[0].key)
        self.select(key if key in keys else keys[0]);return next(t for t in targets if t.key==self.target)
    def select(self,key):
        f=self.form;name=type(f).__name__;self.target=key
        if key.startswith('right:'):f.focus=2;navigation(f.right).select(key[6:])
        elif name=='SplitPane':f.focus=0 if key=='left' else 1
        elif key.startswith('pane:'):self.layout().select(key[5:])
        elif key.startswith('item:'):self.page().index=int(key[5:])
        elif name=='SettingsManager' and f.category is None:f.search_focus=key=='filter'
        elif name=='Stations' and key!='filter':f.focus=int(key=='details')
        elif name=='RadioManager' and f.page in (3,4) and key in ('memory','fields','bank'):f.fields=key=='fields'
        elif name=='Bluetooth' and key.startswith('action:'):f.focus=('1','0','r','s','d').index(key[7:])
        elif name=='MapView':f.focus=int(key=='packets')
        elif name=='ChatView':f.focus=('threads','history','draft').index(key)
        if name=='RadioManager' and f.page==0 and key.startswith('action:'):self.scroll=0
        if name in ('CW','WorkbenchView') and (key.startswith('input:') or key.startswith('job:')):
            self.layout().select('file');index=next(i for i,t in enumerate(self.targets()) if t.key==key)
            (f.fields if name=='CW' else f.controls).index=index
        editor=self.input()
        self.original=(editor,editor.text,editor.cursor) if editor is not None else None
        changed=getattr(f,'changed',None)
        if changed:changed()
    def cycle(self,direction):
        targets=self.targets();keys=[t.key for t in targets];current=self.current().key
        self.select(keys[(keys.index(current)+direction)%len(keys)])
    def input(self):
        f=self.form;key=self.target or ''
        if key.startswith('input:'):return getattr(f,key[6:])
        if type(f).__name__=='DirectoryView' and key=='filter':return f.query
        if type(f).__name__=='ChatView' and key=='draft':return f.draft
        if key=='filter' and type(f).__name__=='Stations':
            if 'filter' not in self.inputs or self.inputs['filter'].text!=f.query:self.inputs['filter']=TextInput(f.query,limit=32)
            return self.inputs['filter']
        return None
    def listing(self):
        f=self.form;name=type(f).__name__;key=self.current().key
        declared=getattr(f,'navigation_list',None)
        if callable(declared):return declared(key)
        if name=='RadioManager' and f.page==1:
            f.sync_memory()
            if key=='pane:groups':return f.memory_groups,lambda:self._radio_group()
            if key=='pane:channels':return f.memory_channels,lambda:setattr(f,'index',f.memory_channels.index)
        if name=='RadioQuick' and key=='groups':f.sync();return f.list,lambda:f.select(f.list.index)
        if name=='Stations' and key=='stations':f.sync();return f.list,f.choose
        entries={'Messages':('threads','list','choose'),'Services':('list','list','select'),'Nets':('agenda','list','select'),'RadioFeed':('feed','list','choose'),'Heard':('events','list','choose')}
        if name in entries:
            pane,attr,callback=entries[name]
            if key=='pane:'+pane:return getattr(f,attr),getattr(f,callback)
        if name=='Walk' and key in ('pane:sessions','pane:probes'):
            pane=key[5:];return getattr(f,pane),getattr(f,'choose_session' if pane=='sessions' else 'choose_probe')
        if key=='pane:items' and hasattr(f,'items'):return f.items,lambda:setattr(f,'scroll',0)
        if name=='WorkbenchView' and key=='pane:result' and f.mode=='history':return f.history,None
        if name=='MapView' and key=='packets':return f.selection,getattr(f,'changed',None)
        if name=='ChatView' and key=='threads':return f.threads,getattr(f,'changed',None)
        if name=='DetachedView' and f.name=='Packet Inspector' and key=='content':return f.owner.selection,f.owner.changed
        if name=='RadioManager' and f.page in (3,4) and key=='memory':
            groups=f.draft_groups();channels=groups[f.bank%len(groups)]['channels'] if groups else ()
            if self.custom is None:self.custom=SelectList(())
            self.custom.rows=tuple(str(c.get('name') or c.get('id') or 'Unnamed') for c in channels);self.custom.index=min(f.index,max(0,len(channels)-1))
            return self.custom,lambda:setattr(f,'index',self.custom.index)
        if (name=='RadioManager' and f.page==2 and key=='banks') or (name in ('DirectoryView','NetsView') and key=='content'):
            if self.custom is None:self.custom=SelectList(())
            if name=='RadioManager':rows=tuple(str(g.get('index',i))+' '+str(g.get('name') or 'Unnamed') for i,g in enumerate(f.state.result['model']['snapshot']['banks']));index=f.bank
            else:
                source=[f.app.items[i] for i in f.matches()] if name=='DirectoryView' else f.app.items
                rows=tuple(item.name+' '+item.summary for item in source);index=f.index
            self.custom.rows=rows;self.custom.index=min(index,max(0,len(rows)-1))
            return self.custom,lambda:self._custom_select()
        if key=='content':
            for attr in ('selection','table'):
                widget=getattr(f,attr,None)
                if isinstance(widget,SelectList):return widget,getattr(f,'changed',None)
        return None,None
    def _custom_select(self):
        f=self.form;setattr(f,'bank' if type(f).__name__=='RadioManager' else 'index',self.custom.index)
        changed=getattr(f,'changed',None)
        if changed:changed()
    def _radio_group(self):
        f=self.form
        if f.bank!=f.memory_groups.index:f.bank=f.memory_groups.index;f.index=0
    def modal(self):
        f=self.form;name=type(f).__name__
        modal=getattr(f,'modal',None)
        if callable(modal):return bool(modal())
        return bool(getattr(f,'search_edit',False)) or getattr(f,'self_editor',None) is not None or bool(getattr(f,'filter_open',False)) or bool(self.layout() and self.layout().resizing) or getattr(f,'entry',None) is not None or getattr(f,'review',None) is not None or bool(getattr(f,'editing',False)) or (name=='Messages' and f.composing) or (name=='System' and f.page==1 and (f.links.choosing or f.links.review))
    def key(self,key):
        f=self.form;name=type(f).__name__;target=self.current()
        if target.key.startswith('right:') and key not in ('\t','backtab'):
            if key=='\x1b':self.select('left');return True
            return native_key(f.right,key)
        if self.modal():
            if key in ('\t','backtab'):
                if name=='System':return True  # A profile review has no other focus target.
                end_input=getattr(f,'navigation_end_input',None)
                if callable(end_input) and end_input():self.cycle(-1 if key=='backtab' else 1);return True
                if name=='Messages':return True
                if name=='ConnectionsView':f.editing=False;self.cycle(-1 if key=='backtab' else 1);return True
                return bool(f.key(key))
            handled=f.key(key)
            if not self.modal():self.target=None
            return handled
        listing,choose=self.listing()
        if listing is not None:
            before=listing.index
            if listing.search_key(key):
                if choose is not None and listing.index!=before:choose()
                changed=getattr(f,'changed',None)
                if changed:changed()
                return True
        if key in ('\t','backtab'):self.cycle(-1 if key=='backtab' else 1);return True
        if key in ('[',']') and self.header() and self.input() is None:self.tab(-1 if key=='[' else 1);return True
        if target.kind=='tabs':
            if key in ('left','right'):self.tab(-1 if key=='left' else 1);return True
            if key in ('\r','\n','down','up'):self.cycle(-1 if key=='up' else 1);return True
            if key=='/':return True
        if key=='\x1b':return self.back()
        editor=self.input()
        if editor is not None:
            if key in ('\r','\n'):
                if name=='ChatView':return f.key(key)
                self.cycle(1)
                if name=='Stations':f.choose()
                return True
            editor.key(key)
            if name=='Stations':f.query=editor.text
            changed=getattr(f,'changed',None)
            if changed:changed()
            return True
        if key=='/' and listing is None and target.kind!='input' and not (name=='SettingsManager' and target.key=='categories'):return True
        if target.kind=='action' and key in ('up','down','left','right'):return True
        if name=='NetsView' and target.key=='details' and key in ('up','down','left','right'):return True
        if name=='NetsView' and target.key=='content' and key in ('\r','\n'):self.select('details');return True
        if key in ('\r','\n'):
            if target.action is not None:
                if target.key.startswith('job:'):
                    self.target=None
                    if name=='CW':return f.decode()
                    f.invoke(target.action);return True
                self.target=None
                return f.key('\r' if target.action=='Enter' else target.action)
            if name=='CalendarView':return f.key('home')
        if key in ('left','right') and self.header() and target.kind not in ('control','choice','map'):return True
        if type(self.page()).__name__=='SettingsWindow' and key in ('up','down'):
            page=self.page()
            if page.items:page.key(key);self.target='item:'+str(page.index)
            return True
        if name=='NetsView' and target.key=='month' and key in ('left','right','up','down'):return f.key('left' if key in ('left','up') else 'right')
        if name=='RadioManager' and target.key=='bank' and key in ('up','down'):return f.key('left' if key=='up' else 'right')
        if name=='RadioManager' and f.page==0 and target.key=='content' and key in ('up','down','home','end','pageup','pagedown'):
            self.scroll=0 if key=='home' else max(0,self.scroll+(-1 if key in ('up','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1))
            if key=='end':self.scroll=len(getattr(f,'_full_rows',()))
            return True
        if name=='FontPreview' and key in ('left','right','up','down'):
            return f.key(('up' if key in ('left','up') else 'down') if target.key=='family' else ('left' if key in ('left','up') else 'right'))
        if name=='SettingsManager' and f.category is None:
            if key=='/' and target.key=='categories':f.query='';f.search_focus=True;self.target='filter';return True
            return f.key(key)
        if name=='DirectoryView' and key=='F':f.editing=True;self.select('filter');return True
        if name=='NetsView' and target.key=='content' and key in ('left','right'):return True
        if name=='Stations' and target.key=='stations' and len(key)==1 and key.isprintable() and key not in ('v','u','U'):return True
        if name=='RadioManager' and target.key=='bank' and key in ('left','right'):return f.key(key)
        handled=f.key(key)
        if handled and key not in ('up','down','left','right','pageup','pagedown','home','end'):self.target=None
        return handled
    def tab(self,direction):
        p,field,labels=self.header()
        order=getattr(p,'tab_order',tuple(range(len(labels))))
        setattr(p,field,order[(order.index(getattr(p,field))+direction)%len(order)])
        for attr,value in (('index',0),('bank',0),('scroll',0),('_identity',None),('fields',False),('composing',False)):
            if hasattr(p,attr):setattr(p,attr,value)
        update=getattr(p,'update',None)
        if update and type(p).__name__ in ('Services','Nets'):update()
        changed=getattr(self.form,'changed',None)
        if changed:changed()
        self.target='tabs'
    def back(self):
        f=self.form;name=type(f).__name__;target=self.current()
        declared=getattr(f,'navigation_back',None)
        if callable(declared):self.target=None;return declared()
        if self.original and self.input() is self.original[0]:
            editor,text,cursor=self.original;editor.text=text;editor.cursor=cursor
            if name=='Stations':f.query=text;self.select('stations');return True
        if name=='SettingsManager':f.key('\x1b');self.target=None;return True
        if name=='StationMap':
            if f.pointer_captured:f.cancel_pointer();return True
            f.open_directory();return True
        if name in ('DetachedView','SceneryApp'):return f.key('\x1b')
        if name=='RadioManager':
            if f.review is not None:f.review=None
            elif f.fields:f.fields=False
            elif f.page:f.page=0
            self.target=None;return True
        layout=self.layout()
        if layout:
            if getattr(f,'resizing',False):return f.key('\x1b')
            if layout.expanded:layout.expanded=False
            elif name=='WorkbenchView' and f.mode=='history':f.mode='result'
            else:layout.select(layout.panels[0].key)
            self.target=None;return True
        if name=='Stations':self.select('stations');return True
        if name=='ChatView':self.select('threads');return True
        self.target=None;return True


def navigation(form):
    state=getattr(form,'_navigation',None)
    if state is None:state=Navigation(form);form._navigation=state
    return state


def native_key(form,key):
    target=getattr(form,'navigation_form',form)
    return form.key(key) if target is None else target.key(key) if getattr(target,'layer_only',False) else navigation(target).key(key)


def native_presentation(form,lines,spans,width,height):
    form=getattr(form,'navigation_form',form)
    if form is None or getattr(form,'layer_only',False):return lines,spans
    state=navigation(form);target=state.current();listing,_=state.listing();rows=list(lines[:height]);rows+=['']*max(0,height-len(rows));spans=list(spans)
    if state.modal():
        declared=getattr(form,'navigation_modal_hint',None)
        label,hint=declared() if callable(declared) else ('Review' if getattr(form,'review',None) is not None else 'Input','Enter accept · Esc back')
    elif listing is not None and listing.searching:label='Search: /'+listing.query+' · '+str(len(listing.matches()))+' matches';hint='Enter accept · Esc cancel · Tab focus'
    else:
        label=target.title+(' /'+listing.query if listing is not None and listing.query else '')
        hint={'tabs':'←/→ tab · Enter pane · Tab focus · Esc back','input':'type · Enter accept · Esc back · Tab focus','list':'↑↓ select · / search · Enter open · Tab focus','details':'↑↓ scroll · Tab focus · Esc back','action':'Enter activate · Tab focus · Esc back','map':'arrows pan · +/- zoom · Esc back','choice':'arrows adjust · Tab focus','control':'arrows adjust · Enter activate · Tab focus'}[target.kind]
    if type(form).__name__=='RadioManager' and form.page==0 and state.scroll:
        full=getattr(form,'_full_rows',lines);state.scroll=min(state.scroll,max(0,len(full)-height+1))
        rows=list(full[:3])+list(full[3+state.scroll:3+state.scroll+max(0,height-4)])
        rows+=['']*max(0,height-len(rows));spans=[s for s in spans if s[0]<3]
    if type(form).__name__=='DirectoryView':
        rows[1]=('Filter: '+(form.query.draw(max(1,width-8)) if form.editing or target.key=='filter' else form.query.text or 'F to edit'))[:width]
        if height>2:rows[-2]='F Filter · [] categories · / search list'[:width]
    if state.custom is not None and listing is state.custom and listing.query and listing.matches():
        name=type(form).__name__
        if name=='RadioManager' and form.page==2:visible={hit[1] for hit in form.hits if len(hit)==5 and hit[4][0]=='bank'}
        elif name=='DirectoryView':visible={4+i*2+j for i in range(len(form.matches())) for j in (0,1)}
        elif name=='NetsView':visible={9+i*2+j for i in range(len(form.app.items)) for j in (0,1)}
        else:visible=set(range(3,max(3,height-2)))
        for y in visible:
            if 0<=y<height-1:
                for start,size in literal_spans(rows[y][:width],listing.query):spans.append((y,start,size,'match'))
    if type(form).__name__=='Stations' and not (listing is not None and listing.searching):hint='↑↓ browse · U ULS · Enter/v map · / filter · Tab pane'
    if type(form).__name__=='SettingsManager' and form.category is None and target.key=='categories':hint='arrows browse · Enter open · / category filter · Tab focus'
    if type(form).__name__=='BirdView' and target.key=='map':hint='arrows orbit/tilt · +/- zoom · Tab focus · Esc back'
    if type(form).__name__=='DetachedView':hint='↑↓ browse · Enter reattach · Esc back'
    rows[-1]=(label+' · '+hint)[:width];spans.append((height-1,0,width,'control'))
    if target.kind=='tabs':
        if type(form).__name__=='SplitPane':
            left,right=form.sizes();spans.append((1,left+1,right,'input'))
        else:spans.append((getattr(form,'navigation_tab_row',2 if type(form).__name__=='SettingsManager' and form.category is not None else 0),0,width,'input'))
    if type(form).__name__=='SplitPane' and target.key.startswith('right:item:'):
        left,right=form.sizes();spans.append((3+int(target.key.rsplit(':',1)[1]),left+1,right,'input'))
    if target.key.startswith('action:'):
        action=target.action
        declared=getattr(form,'navigation_action_spans',None)
        if callable(declared):spans.extend(declared(action))
        semantic=getattr(form,'shortcuts',{}).get(action,action)
        for hit in getattr(form,'hits',()):
            if len(hit)==5 and hit[4]==('action',action):spans.append((hit[1],hit[0],hit[2],'input'))
        for hit in getattr(form,'_hits',()):
            if len(hit)==4 and hit[3]==semantic:spans.append((hit[1],hit[0],hit[2],'input'))
        for x,end,key in getattr(form,'_buttons',()):
            if key==action:spans.append((2,x,end-x,'input'))
    if target.key=='filter' and type(form).__name__=='Stations':
        rows[1]=('Filter: '+state.input().draw(max(1,width-8)))[:width];spans.append((1,0,width,'input'))
    return tuple(rows),tuple(spans)


def native_pointer(form,column,row,width,button=0,released=False,*,event=None):
    wrapper=form;form=getattr(form,'navigation_form',form)
    if form is None:
        from pointer_events import deliver_pointer
        return deliver_pointer(wrapper,event,column,row,width) if event is not None else False
    state=navigation(form)
    if button in (0,1,2) and not released:
        listing,_=state.listing()
        if listing is not None:listing.searching=False
    if type(form).__name__=='RadioManager' and form.page==1 and button&64 and not released:
        for pane,(x,y,w,h) in form.memory_layout.rects.items():
            if x<=column<x+w and y+3<=row<y+3+h:
                delta=3 if button&1 else -3
                if pane=='details':form.detail_scroll=max(0,form.detail_scroll+delta)
                else:
                    form.sync_memory()
                    widget=form.memory_groups if pane=='groups' else form.memory_channels
                    widget.scroll(delta,max(1,h-(3 if pane=='channels' else 2)))
                return True
    from pointer_events import deliver_pointer,prepare_gestures
    result=deliver_pointer(form,event if event is not None else ('mouse',button,column,row,released),column,row,width)
    if button in (0,1,2) and not released:
        state.target='tabs' if row==getattr(form,'navigation_tab_row',0) and state.header() else None
        if type(form).__name__=='Stations' and row==1:state.select('filter')
        if type(form).__name__=='SplitPane':navigation(form.right).target=None
    return result
