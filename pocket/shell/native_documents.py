"""Reader/article and Library/file presentations over immutable cached views."""
from app_widgets import AdaptivePanels,PanelSpec,Canvas,DetailBlock,SelectList,TextInput,toolbar_layout


def inline(value):return ''.join(char if char.isprintable() else ' ' for char in str(value))


def prose(body,text):
    for line in str(text).expandtabs(4).splitlines():body.text(inline(line))


class DocumentView:
    def __init__(self,command):
        self.command=command;self.width=94;self.height=28;self.snapshot=None;self.rows=();self.notice='';self.query=''
        self.layout=AdaptivePanels((PanelSpec('items','Items',24,32),PanelSpec('detail','Content',30,62)))
        self.items=SelectList(());self.entry=None;self.entry_action=None;self.scroll=0;self._spans=();self._rects={};self._hits=[];self._body_key=None;self._body=None

    def update(self,snapshot,rows):
        if snapshot is not self.snapshot:self._body_key=None
        self.snapshot=snapshot;self.rows=rows
        self.items.replace(tuple(self.row_label(row) for row in rows),tuple(row.id for row in rows))

    def selected(self):return self.rows[self.items.index] if self.rows else None

    def begin(self,action):
        self.entry_action=action;self.entry=TextInput(self.query if action=='search' else '',limit=256 if action=='search' else 1024)

    def activate(self,action):
        if action in ('search','import_local','refresh','add_root'):self.begin(action)
        else:self.action(action)

    def key(self,key):
        if self.entry is not None:
            if key in ('\x1b','escape'):self.entry=None;return True
            if key in ('\r','\n'):
                text=self.entry.text.strip();action=self.entry_action;self.entry=None
                if action=='search':self.query=text
                self.command(action,text);self.scroll=0;return True
            return self.entry.key(key)
        if self.layout.focus=='items' and self.items.search_key(key):self.scroll=0;return True
        if key in ('\t','backtab'):self.layout.cycle(-1 if key=='backtab' else 1);return True
        if key in self.shortcuts:self.activate(self.shortcuts[key]);return True
        if key in ('\r','\n'):self.action('open');return True
        if self.layout.focus=='items':
            before=self.items.index;handled=self.items.key(key)
            if self.items.index!=before:self.scroll=0
            return handled
        if key in ('up','down','pageup','pagedown','home'):
            self.scroll=0 if key=='home' else max(0,self.scroll+(-1 if key in ('up','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1));return True
        return False

    def pointer(self,column,row,width,button=0,released=False):
        if released or button&32:return False
        if button==0:
            for x,y,w,action in self._hits:
                if y==row and x<=column<x+w:
                    if action.startswith('pane:'):self.layout.select(action[5:])
                    else:self.activate(action)
                    return True
        for key,(x,y,w,h) in self._rects.items():
            if x<=column<x+w and y<=row<y+h:
                self.layout.select(key)
                if button&64:return self.key('down' if button&1 else 'up')
                if key=='items' and row>y and button==0:
                    before=self.items.index;handled=self.items.pointer_at(column-x,row-y-1,w,max(1,h-1))
                    if before!=self.items.index:self.scroll=0
                    return handled
                return button==0
        return False

    def lines(self):
        c=Canvas(self.width,self.height);self._hits=[];snapshot=self.snapshot
        labels,hits=toolbar_layout(self.actions,self.width)
        for y,label in enumerate(labels):c.put(0,y,label);c.role(0,y,self.width,'control')
        self._hits.extend((x,y,w,self.shortcuts.get(action,'open' if action=='Enter' else action)) for x,y,w,action in hits)
        top=len(labels)
        if self.entry is not None:
            label=self.entry_labels[self.entry_action]+': '
            c.put(0,top,label+self.entry.draw(max(1,self.width-len(label))));c.role(0,top,self.width,'selected');top+=1
        else:
            c.put(0,top,self.subtitle());c.role(0,top,self.width,'muted');top+=1
        raw=self.layout.layout(self.width,max(1,self.height-top-2));self._rects={key:(x,y+top,w,h) for key,(x,y,w,h) in raw.items()}
        if self.layout.tabbed:
            x=0
            for panel in self.layout.panels:
                label='['+panel.title+']' if self.layout.focus==panel.key else panel.title
                c.put(x,top,label);c.role(x,top,len(label),'control');self._hits.append((x,top,len(label),'pane:'+panel.key));x+=len(label)+2
        else:c.divider(raw['items'][2],top,max(1,self.height-top-2))
        for key,(x,y,w,h) in self._rects.items():
            c.pane(x,y,w,h,self.item_title if key=='items' else self.content_title,self.layout.focus==key,inset=key=='items')
            if key=='items':
                self.items.draw(c,x,y+1,w,max(1,h-1))
                if not self.rows:c.put(x,y+1,self.empty_message,w)
            else:
                selected=self.selected();cache_key=(getattr(snapshot,'revision',None),getattr(selected,'id',None),w,getattr(self,'show_collections',False))
                if self._body_key!=cache_key:self._body=self.body(w);self._body_key=cache_key
                self.scroll=self._body.draw(c,x,y+1,w,max(1,h-1),self.scroll)
        result=getattr(snapshot,'result',None);pending=getattr(snapshot,'pending',None)
        message=self.notice or ('Working: '+pending if pending else result.message if result else 'Ready')
        c.put(0,self.height-2,message);c.role(0,self.height-2,self.width,'warning' if result and result.code in ('error','blocked','invalid') else 'status')
        c.put(0,self.height-1,'Tab pane · ↑↓ select/scroll · Enter open · / search list · F filter');c.role(0,self.height-1,self.width,'control')
        self._spans=c.styled_spans();return c.lines()

    def spans(self):return self._spans


class ReaderView(DocumentView):
    title='Reader · feeds & saved articles';item_title='Articles';content_title='Article';empty_message='Import a feed or open the offline example'
    actions=(('o','Import'),('u','Fetch feed'),('f','Fetch page'),('r','Read'),('s','Save'),('b','Saved'),('F','Filter'),('e','Example'),('l','Reload cache'),('x','Cancel'))
    shortcuts={'o':'import_local','u':'refresh','f':'refresh_article','r':'set_read','s':'set_saved','b':'saved_only','F':'search','e':'example','l':'load','x':'cancel'}
    entry_labels={'search':'Filter cached articles','import_local':'RSS/Atom file','refresh':'Feed URL · explicit fetch'}
    def __init__(self,command):super().__init__(command);self.saved_only=False
    def row_label(self,row):return ('★ ' if row.saved else '  ')+('· ' if row.read else '● ')+inline(row.title)
    def subtitle(self):return ('Saved' if self.saved_only else 'All cached')+' · '+str(len(self.rows))+' articles'+(' · filter: '+self.query if self.query else '')
    def action(self,action):
        row=self.selected()
        if action=='open':self.layout.select('detail');self.scroll=0
        elif action in ('set_read','set_saved','refresh_article'):
            if row is None:self.notice='Select an article first';return
            self.command(action,row.id,*((not row.read,) if action=='set_read' else (not row.saved,) if action=='set_saved' else ()))
        elif action in ('example','cancel','saved_only','load'):self.command(action)
    def body(self,width):
        body=DetailBlock(width);row=self.selected()
        if row:
            body.section(inline(row.title))
            feed=next((feed for feed in self.snapshot.feeds if feed.id==row.feed_id),None)
            if feed:body.field('Feed',inline(feed.title))
            if row.author:body.field('Author',inline(row.author))
            if row.published:body.field('Published',inline(row.published))
            body.field('Content','Fetched article' if row.content_source=='article' else 'Cached feed text')
            body.field('State',('Read' if row.read else 'Unread')+(' · Saved' if row.saved else ''))
            body.text('');prose(body,row.content or row.summary)
            if row.url:body.section('Link');body.text(inline(row.url),'muted')
        else:
            body.section('Read offline');body.text('Import a local RSS/Atom file, or choose Example for an authored offline feed.')
            body.text('Fetching a feed or article requires an explicit action. Opening this window never fetches a URL.','muted')
        return body


class LibraryView(DocumentView):
    title='Library · local collections';item_title='Documents';content_title='Preview';empty_message='Configure a folder, then Scan'
    actions=(('c','Add folder'),('i','Scan'),('g','Folders'),('Enter','Open'),('F','Filter'),('x','Cancel'))
    shortcuts={'c':'add_root','i':'scan','g':'collections','F':'search','x':'cancel'}
    entry_labels={'search':'Filter indexed text','add_root':'Collection folder · this session'}
    def __init__(self,command):super().__init__(command);self.show_collections=False
    def row_label(self,row):return inline(row.relative_path)
    def subtitle(self):
        collections=self.snapshot.collections if self.snapshot else ()
        states=' · '.join(inline(row.title)+': '+row.state for row in collections)
        return states or 'No folders configured · c to add · --library-root to configure on launch'
    def action(self,action):
        if action in ('scan','cancel'):self.command(action)
        elif action=='collections':self.show_collections=not self.show_collections;self.layout.select('detail');self.scroll=0
        elif action=='open':
            row=self.selected()
            if row is None:self.notice='Select an indexed document first';return
            self.show_collections=False;self.command('open',row.id);self.layout.select('detail');self.scroll=0
    def body(self,width):
        body=DetailBlock(width);row=self.selected();snapshot=self.snapshot
        if row and not self.show_collections:
            body.section(inline(row.title));body.field('Path',inline(row.relative_path));body.field('Type',row.kind);body.field('Bytes',row.size)
            opened=snapshot.opened
            if opened and opened.id==row.id:
                body.field('Preview','Last successful open')
                if opened.external:body.text('External viewer required for this format. No viewer has been launched.','muted')
                else:body.text('');prose(body,opened.text or 'Empty text document')
                if opened.truncated:body.text('Preview truncated at the read limit','warning')
            else:body.text('Press Enter to open a bounded local preview.','muted')
        else:
            body.section('Configured collections')
            for collection in snapshot.collections if snapshot else ():
                body.section(inline(collection.title));body.field('Folder',inline(collection.root));body.field('State',collection.state);body.text(inline(collection.message))
            if not snapshot or not snapshot.collections:body.text('Add an explicit local folder, then choose Scan. No folders are discovered or scanned automatically.')
            body.text('Search covers bounded indexed text. PDF, ZIM and binary formats show metadata only.','muted')
        return body
