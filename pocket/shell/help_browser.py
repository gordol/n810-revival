"""Browsable local help over app-owned pages; no application actions execute here."""
import textwrap
from app_widgets import AdaptivePanels,PanelSpec,Canvas,SelectList


USING_HELP=(('Using Help',(
    'Help opened with ? starts in the Reading pane.',
    'In Reading, Up/Down or j/k scrolls the text. PageUp/PageDown scrolls a page; Home/End goes to the beginning/end.',
    'Tab or Shift-Tab moves focus between Topics and Reading. In Topics, Up/Down or j/k selects an entry and previews its text.',
    'Enter opens a selected application or topic. You can also press Tab to read the topic already shown in the preview.',
    'In Topics, / searches the list. Enter accepts search; Esc clears it.',
    'Ctrl-F opens manual search. Type your query, then press Tab to focus the results. Enter opens the selected result; Esc cancels search.',
    'Left or Esc returns to the list, then to all applications.',
    'Click an entry to select it; click it again to open it.',
    'The wheel scrolls the pane under the pointer.',
    'Drag the divider, or Ctrl-R then Left/Right to resize panes.',
    'Enter keeps the resized split; Esc restores its starting position.',
    'Narrow windows show one pane; Tab switches the visible pane.',
)),)


def clean(value):
    text=str(value)
    return text if text.isprintable() else ''.join(c if c.isprintable() else ' ' for c in text)


def normalized(pages):
    result=[]
    for title,lines in tuple(pages)[:32]:
        if isinstance(lines,str):lines=(lines,)
        result.append((clean(title)[:120],tuple(clean(line)[:500] for line in tuple(lines)[:128])))
    return tuple(result)


class HelpBrowser:
    # Esc and the clickable Back button handle history; Tab cycles the panes.
    actions=()
    def navigation_back(self):return self.back()
    def navigation_list(self,key):
        return (self.items,self.sync) if key=='pane:topics' else (None,None)
    def __init__(self,forms=None,global_pages=(),close=None):
        self.width=90;self.height=28;self.close=close;self.forms=forms or {}
        self.catalog={'Desktop':USING_HELP+normalized(global_pages)}
        if forms is None:
            from app_help_content import PAGES,pages
            self.catalog.update((name,normalized(pages(name))) for name in PAGES)
        else:
            for name,form in tuple(forms.items())[:64]:
                if hasattr(form,'help_pages'):
                    content=normalized(form.help_pages())
                    if content:self.catalog[clean(name)]=content
        self.layout=AdaptivePanels((PanelSpec('topics','Topics',22,30),PanelSpec('reading','Reading',30,60)))
        self.items=SelectList(());self.group=None;self.topic=0;self.scroll=0;self._rows=();self._rects={};self._spans=();self._body_key=None;self._body=()
        self.sync()

    def sync(self):
        rows=tuple(self.catalog) if self.group is None else tuple(title for title,_ in self.catalog[self.group])
        if rows!=self._rows:
            self._rows=rows;self.items=SelectList(rows);self.items.index=min(self.topic,len(rows)-1) if self.group else 0
        if self.group and self.items.index!=self.topic:self.topic=self.items.index;self.scroll=0

    def open_context(self,name=None,topic=None):
        form=self.forms.get(name)
        if form is not None and hasattr(form,'help_pages'):
            content=normalized(form.help_pages())
            if content:
                titles={title for title,_ in content}
                self.catalog[name]=content+tuple(page for page in self.catalog.get(name,()) if page[0] not in titles)
        self.group=name if name in self.catalog else 'Desktop';self.topic=0;self.scroll=0;self._rows=();self.sync()
        if topic is not None:
            titles=[title for title,_ in self.catalog[self.group]]
            if topic in titles:self.topic=titles.index(topic);self.items.index=self.topic;self.items.reveal()
        self.layout.select('reading');return name in self.catalog

    def activate(self):
        if self.group is None:
            self.group=self._rows[self.items.index];self.topic=0;self.scroll=0;self._rows=();self.sync()
        else:self.topic=self.items.index;self.layout.select('reading')

    def back(self):
        if self.layout.focus=='reading':self.layout.select('topics')
        elif self.group is not None:
            group=self.group;self.group=None;self.topic=0;self.scroll=0;self._rows=();self.sync();self.items.index=self._rows.index(group);self.items.reveal()
        elif self.close:self.close()
        return True

    def page(self):
        if self.group is None:return ('Help',('Choose Desktop or an application to browse its topics.','Only applications that provide help pages appear here.','Help describes controls; it never performs the documented action.'))
        return self.catalog[self.group][self.topic]

    def body(self,width):
        title,lines=self.page();key=(self.group,self.topic,width,title,lines)
        if key!=self._body_key:
            self._body_key=key;body=[]
            for line in lines:body.extend(textwrap.wrap(line,max(1,width),break_long_words=True,break_on_hyphens=False) or ['']);body.append('')
            self._body=tuple(body)
        return self._body

    @property
    def pointer_captured(self):return self.layout.pointer_captured
    @property
    def resizing(self):return self.layout.resizing
    def cancel_pointer(self):self.layout.cancel_pointer()
    def bind_session(self,callback):self.layout.bind_session(callback)
    def session_state(self):return dict(panels=self.layout.session_state())
    def restore_session(self,state):
        if isinstance(state,dict):self.layout.restore_session(state.get('panels',{}))

    def key(self,key):
        self.sync()
        if self.layout.resizing or key=='\x12' and not self.items.searching:
            if self.layout.split_key(key,self.width):return True
        if self.layout.focus=='topics' and self.items.search_key(key):self.sync();return True
        if key in ('\t','backtab'):self.layout.cycle(-1 if key=='backtab' else 1);return True
        if key in ('\x1b','left'):return self.back()
        if key in ('\r','\n','right'):
            if self.layout.focus=='topics':self.activate()
            return True
        if self.layout.focus=='topics':
            handled=self.items.key(key);self.sync();return handled
        if key in ('up','down','j','k','pageup','pagedown','home','end'):
            if key=='home':self.scroll=0
            elif key=='end':self.scroll=len(self._body)
            else:self.scroll=max(0,self.scroll+(-1 if key in ('up','k','pageup') else 1)*(max(1,self.height-7) if key in ('pageup','pagedown') else 1))
            return True
        return False

    def pointer(self,column,row,width,button=0,released=False):
        if self.layout.split_pointer(column,row,width,button,released,top=2,bottom=self.height-1):return True
        if released or button&32:return False
        if button==0 and row==0 and column>=width-8:return self.back()
        if button==0 and row==2 and self.layout.tabbed:
            self.layout.select('topics' if column<10 else 'reading');return True
        for key,(x,y,w,h) in self._rects.items():
            if not(x<=column<x+w and y<=row<y+h):continue
            if button&64:
                if key=='topics':self.items.scroll(3 if button&1 else -3,max(1,h-1))
                else:self.scroll=max(0,self.scroll+(3 if button&1 else -3))
                return True
            if button!=0:return False
            self.layout.select(key)
            if key=='topics' and row>y:
                before=self.items.index
                if self.items.pointer_at(column-x,row-y-1,w,max(1,h-1)):
                    self.sync()
                    if before==self.items.index:self.activate()
            return True
        return False

    def lines(self):
        self.sync();c=Canvas(self.width,self.height)
        c.put(0,0,'Browse help',max(0,self.width-9));c.put(max(0,self.width-8),0,'[ Back ]')
        c.put(0,1,'All applications'+(' / '+self.group if self.group else ''))
        raw=self.layout.layout(self.width,max(1,self.height-3));self._rects={key:(x,y+2,w,h) for key,(x,y,w,h) in raw.items()}
        if self.layout.tabbed:c.put(0,2,'[Topics]  Reading' if self.layout.focus=='topics' else 'Topics  [Reading]')
        else:c.divider(raw['topics'][2],2,max(1,self.height-3))
        for key,(x,y,w,h) in self._rects.items():
            c.pane(x,y,w,h,('Applications' if self.group is None else 'Topics') if key=='topics' else self.page()[0],key==self.layout.focus,inset=key=='topics')
            if key=='topics':
                self.items.draw(c,x,y+1,w,max(1,h-1))
                if self.items.visible_selection is not None:c.role(x,y+1+self.items.visible_selection,w,'selected')
            else:
                body=self.body(w);visible=max(1,h-2);self.scroll=min(self.scroll,max(0,len(body)-visible))
                for row,text in enumerate(body[self.scroll:self.scroll+visible],y+1):c.put(x,row,text,w)
                c.put(x,y+h-1,f'{self.scroll+1}–{min(len(body),self.scroll+visible)} / {len(body)} lines',w);c.role(x,y+h-1,w,'muted')
        c.put(0,self.height-1,'←/→ resize · Enter keep · Esc cancel' if self.resizing else 'Enter open · Esc back · Tab pane · / find · Ctrl-R split')
        c.role(0,0,self.width,'toolbar');c.role(0,1,self.width,'muted');c.role(0,self.height-1,self.width,'muted');self._spans=tuple(c.styled_spans());return c.lines()

    def spans(self):return self._spans
