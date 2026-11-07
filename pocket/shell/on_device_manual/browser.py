"""Read-only search and references over the existing HelpBrowser."""
from help_browser import HelpBrowser,normalized
from .content import ManualIndex,load_pages,page_lines


class ManualBrowser(HelpBrowser):
    # Ctrl-F opens search directly; Tab remains a two-pane focus cycle.
    actions=HelpBrowser.actions
    def navigation_modal_hint(self):
        if self.resizing:return ('Resize panes','Left/Right resize · Enter keep · Esc cancel')
        return ('Search: '+self.query,'Tab results · Enter results · Esc cancel')
    def __init__(self,pages=None,close=None,forms=None,global_pages=()):
        self.index=ManualIndex(load_pages() if pages is None else pages)
        groups={}
        self.topic_ids={}
        for page in self.index.pages:
            groups.setdefault(page['app'],[]).append((page['title'],page_lines(page,self.index.by_id)))
            self.topic_ids[(page['app'],page['title'])]=page['id']
        super().__init__(forms,global_pages,close)
        for name,content in groups.items():
            existing=self.catalog.get(name,())
            titles={title for title,_ in existing}
            self.catalog[name]=existing+normalized((title,lines) for title,lines in content if title not in titles)
        self._rows=();self.sync()
        self.search_edit=False;self.query='';self.results=();self.search_origin=None;self.history=[]

    def current_id(self):
        if not self.group or self.group=='Search results':return None
        return self.topic_ids.get((self.group,self.page()[0]))

    def open_topic(self,identifier,remember=False):
        page=self.index.by_id.get(identifier)
        if page is None:return False
        if remember and self.current_id():self.history.append((self.current_id(),self.scroll));self.history=self.history[-16:]
        return super().open_context(page['app'],page['title'])

    def search_all(self,query):
        self.query=str(query)[:256];self.results=self.index.search(self.query)
        self.catalog['Search results']=tuple((page['app']+': '+page['title'],('Enter opens '+page['id'],)) for page in self.results) or (
            ('No matches',('Try a term such as pairing, profile, identity or launch.',)),)
        self.group='Search results';self.topic=0;self.scroll=0;self._rows=();self.sync();self.layout.select('topics')

    def activate(self):
        if self.group=='Search results':
            if self.results:self.open_topic(self.results[self.items.index]['id'],remember=True)
        else:super().activate()

    def key(self,key):
        if key=='\x06':
            self.search_origin=(self.group,self.topic,self.scroll);self.search_edit=True;self.search_all('');return True
        if self.search_edit:
            if key=='\x1b':
                self.search_edit=False
                self.group,self.topic,self.scroll=self.search_origin
                self._rows=();self.sync();return True
            if key in ('\t','backtab','\r','\n'):
                self.search_edit=False;self.layout.select('reading' if key=='backtab' else 'topics');return True
            if key in ('\x7f','\b'):self.search_all(self.query[:-1]);return True
            if len(key)==1 and key.isprintable():self.search_all(self.query+key);return True
            return True
        if self.layout.focus=='reading':
            identifier=self.current_id()
            if identifier and key in '123456789' and len(key)==1:
                refs=self.index.by_id[identifier]['see_also'];position=int(key)-1
                if position<len(refs):self.open_topic(refs[position],remember=True)
                return True
            if key in ('\x7f','\b') and self.history:
                identifier,scroll=self.history.pop();self.open_topic(identifier);self.scroll=scroll;return True
        return super().key(key)

    def lines(self):
        lines=list(super().lines())
        lines[0]=('Offline manual'.ljust(max(0,self.width-8))+'[ Back ]')[:self.width]
        footer=('Search manual: '+self.query+' | Tab results | Enter results | Esc cancel') if self.search_edit else 'Ctrl-F manual text | / list | Tab pane | 1-9 See also | Backspace return'
        lines[-1]=footer[:self.width].ljust(self.width)
        return lines
