"""Reusable bounded character widgets for application layouts."""
from bisect import bisect_left,bisect_right
from functools import lru_cache
from collections import namedtuple


class ViewOptions:
    __slots__=('scrollbars','counts','status')
    scrollbars:str
    counts:str
    status:str
    def __init__(self,scrollbars='auto',counts='auto',status='compact'):
        self.scrollbars=scrollbars;self.counts=counts;self.status=status


VIEW_OPTIONS=ViewOptions()


def configure_views(scrollbars='auto',counts='auto',status='compact'):
    if scrollbars not in ('auto','on','off') or counts not in ('auto','on','off') or status not in ('compact','detailed'):raise ValueError('Invalid application presentation')
    VIEW_OPTIONS.scrollbars=scrollbars;VIEW_OPTIONS.counts=counts;VIEW_OPTIONS.status=status


def status_text(compact,detailed,width,options=None):
    options=options or VIEW_OPTIONS
    return str(detailed if options.status=='detailed' else compact)[:max(0,width)]


def connection_summary(metadata):
    """Brief operator status; detailed source/provenance stays an explicit choice."""
    label=str(metadata.get('connection') or ('Saved' if metadata.get('freshness') else 'Unknown'))
    stamp=metadata.get('last_record')
    if stamp:
        import time_display
        label+=' · last '+time_display.clock(stamp)
    elif not metadata.get('freshness'):label+=' · Freshness unknown'
    return label


class PanelSpec(namedtuple('PanelSpec','key title minimum preferred',defaults=())):
    __slots__=()
    key:str
    title:str
    minimum:int
    preferred:int


class AdaptivePanels:
    """Stable panel focus; columns when usable, one tabbed panel when narrow."""
    def bind_session(self,callback):self._session_callback=callback
    def _saved(self,name,value):
        old=self.__dict__.get('_'+name)
        self.__dict__['_'+name]=value
        callback=getattr(self,'_session_callback',None)
        if old!=value and callback:callback()
    @property
    def ratio(self):return self._ratio
    @ratio.setter
    def ratio(self,value):self._saved('ratio',value)
    @property
    def focus(self):return self._focus
    @focus.setter
    def focus(self,value):self._saved('focus',value)
    @property
    def expanded(self):return self._expanded
    @expanded.setter
    def expanded(self,value):self._saved('expanded',value)
    def set_expanded(self,value):self.expanded=bool(value)
    def __init__(self,panels,focus=None):
        self.panels=tuple(panels)
        if not self.panels or len({p.key for p in self.panels})!=len(self.panels):raise ValueError('Panel IDs must be nonempty and unique')
        self.focus=focus or self.panels[0].key
        self.select(self.focus)
        self.tabbed=False
        self.rects={};self.ratio=None;self.expanded=False
        self._split_drag=False;self._split_keyboard=False;self._split_before=None;self._layout_height=1
    @property
    def pointer_captured(self):return self._split_drag
    @property
    def resizing(self):return self._split_drag or self._split_keyboard
    def _finish_split(self,cancel=False):
        if cancel and self.resizing:self.ratio=self._split_before
        self._split_drag=self._split_keyboard=False;self._split_before=None
    def cancel_pointer(self):
        if self._split_drag:self._finish_split(True)
    def _split_ready(self,width):
        self.layout(width,self._layout_height)
        return len(self.panels)==2 and not self.tabbed
    def split_pointer(self,column,row,width,button=0,released=False,top=0,bottom=None):
        captured=self._split_drag
        if not self._split_ready(width):return captured
        if captured:
            if released or button in (0,32):self.resize_split(column,width)
            if released:self._finish_split()
            return True
        if released or button!=0 or row<top or bottom is not None and row>=bottom:return False
        if column!=self.rects[self.panels[0].key][2]:return False
        self._split_before=self.ratio;self._split_drag=True;return True
    def split_key(self,key,width):
        if not self.resizing and key!='\x12':return False
        active=self.resizing
        if not self._split_ready(width):return active or key=='\x12'
        if not self.resizing:
            self._split_before=self.ratio;self._split_keyboard=True
        elif key in ('\x1b','escape'):self._finish_split(True)
        elif key in ('\r','\n','enter'):self._finish_split()
        elif key in ('left','right'):
            self.resize_split(self.rects[self.panels[0].key][2]+(-1 if key=='left' else 1),width)
        return True
    def session_state(self):return dict(ratio=self.ratio,focus=self.focus,expanded=self.expanded)
    def restore_session(self,state):
        import math
        if not isinstance(state,dict):return
        self._finish_split(True)
        ratio=state.get('ratio')
        if ratio is None or type(ratio) in (int,float) and math.isfinite(ratio) and 0<=ratio<=1:self.ratio=ratio
        if state.get('focus') in {p.key for p in self.panels}:self.select(state['focus'])
        if type(state.get('expanded')) is bool:self.expanded=state['expanded']
    def select(self,key):
        if key not in {p.key for p in self.panels}:raise ValueError('Unknown panel: '+key)
        self.focus=key
    def cycle(self,direction=1):
        keys=[p.key for p in self.panels]
        self.select(keys[(keys.index(self.focus)+direction)%len(keys)])
    def resize_split(self,column,width):
        if len(self.panels)!=2 or width<sum(p.minimum for p in self.panels)+1:return False
        left=max(self.panels[0].minimum,min(width-1-self.panels[1].minimum,column))
        self.ratio=left/max(1,width-1);return True
    def layout(self,width,height):
        width=max(1,width);height=max(1,height)
        self._layout_height=height
        self.tabbed=self.expanded or sum(p.minimum for p in self.panels)+len(self.panels)-1>width
        if self.tabbed and self.resizing:self._finish_split(True)
        if self.tabbed:
            self.rects={self.focus:(0,1,width,max(1,height-1))}
        else:
            sizes=[p.minimum for p in self.panels]
            remaining=width-sum(sizes)-len(sizes)+1
            for index,panel in enumerate(self.panels):
                grow=min(remaining,max(0,panel.preferred-sizes[index]))
                sizes[index]+=grow;remaining-=grow
            sizes[-1]+=remaining
            if self.ratio is not None and len(sizes)==2:
                sizes[0]=max(self.panels[0].minimum,min(width-1-self.panels[1].minimum,round((width-1)*self.ratio)))
                sizes[1]=width-1-sizes[0]
            x=0;self.rects={}
            for panel,size in zip(self.panels,sizes):
                self.rects[panel.key]=(x,0,size,height);x+=size+1
        return self.rects


class Canvas:
    def __init__(self,width,height):
        self.width,self.height=max(1,width),max(1,height)
        self.rows=[[' ']*self.width for _ in range(self.height)];self.spans=[];self.pane_focus={}
    def put(self,x,y,text,width=None):
        if not 0<=y<self.height:return
        width=self.width-x if width is None else min(width,self.width-x)
        if width<=0:return
        for i,char in enumerate(str(text)[:width]):
            if x+i>=0:self.rows[y][x+i]=char
    def role(self,x,y,width,role):
        if 0<=y<self.height and width>0:self.spans.append((y,max(0,x),max(0,min(width,self.width-max(0,x))),role))
    def pane(self,x,y,width,height,title,focused=False,inset=False):
        self.pane_focus[(x,y,width)]=focused
        for row in range(y,y+height):self.role(x,row,width,'rail' if inset else 'panel')
        self.put(x,y,(('> ' if focused else '  ')+title)[:width].ljust(width),width)
        self.role(x,y,width,'control' if focused else 'toolbar')
        self.role(x+2,y,min(len(title),max(0,width-2)),'heading' if focused else 'muted')
    def divider(self,x,y,height):
        for row in range(y,y+height):self.put(x,row,'│',1);self.role(x,row,1,'muted')
    def styled_spans(self,base=()):
        base=tuple(base)
        return [s for s in base if s[3] not in ('selected','input','match')]+[s for s in self.spans if s[3]!='match']+[s for s in base if s[3] in ('selected','input')]+[s for s in (*base,*self.spans) if s[3]=='match']
    def right_label(self,x,y,width,label,gap=2):
        # Caller titles/column headings own their cells; optional metadata yields.
        if not 0<=y<self.height or width<len(label):return False
        right=min(self.width,x+width);left=right-len(label)
        if left<x or any(char!=' ' for char in self.rows[y][max(x,left-gap):right]):return False
        self.put(left,y,label,len(label));return True
    def rule(self,y,x=0,width=None):self.put(x,y,'-'*(self.width if width is None else width),width)
    def wrap(self,x,y,text,width):
        import textwrap
        lines=textwrap.wrap(text,max(1,width),replace_whitespace=False) or ['']
        for i,line in enumerate(lines):self.put(x,y+i,line,width)
        return y+len(lines)
    def lines(self):return tuple(''.join(row).rstrip() for row in self.rows)


class Column(namedtuple('Column','title width role',defaults=('body',))):
    __slots__=()
    title:str
    width:int
    role:str


class Columns:
    def __init__(self,columns):self.columns=tuple(columns)
    def parts(self,values,width):
        x=0
        for i,(column,value) in enumerate(zip(self.columns,values)):
            size=max(0,min(width-x,column.width if i<len(self.columns)-1 else width-x))
            if size:yield x,size,str(value)[:size],column.role
            x+=size+1
            if x>=width:break
    def text(self,values,width):
        parts=list(self.parts(values,width))
        if not parts:return ''
        line=[' ']*max(x+size for x,size,_,_ in parts)
        for x,size,value,role in parts:line[x:x+len(value)]=value
        return ''.join(line).rstrip()


class DetailBlock:
    """Wrapped typed fields and sections, with one shared semantic role path."""
    def __init__(self,width):self.width=max(1,width);self.lines=[];self.spans=[]
    def text(self,text,role='body'):
        import textwrap
        for line in textwrap.wrap(str(text),self.width,replace_whitespace=False) or ['']:
            row=len(self.lines);self.lines.append(line);self.spans.append((row,0,self.width,role))
    def section(self,title):
        if self.lines:self.text('')
        self.text(title,'heading')
    def field(self,label,value,kind='text'):
        import textwrap
        value_role={'identity':'heading','frequency':'control','time':'muted','path':'muted','text':'body'}.get(kind,'body')
        label_width=min(12,max(5,self.width//3));prefix=str(label)[:label_width].ljust(label_width)+'  '
        width=max(1,self.width-len(prefix))
        for index,part in enumerate(textwrap.wrap(str(value),width,replace_whitespace=False) or ['—']):
            row=len(self.lines);self.lines.append((prefix if index==0 else ' '*len(prefix))+part)
            self.spans.extend(((row,0,len(prefix),'muted'),(row,len(prefix),min(width,len(part)),value_role)))
    def draw(self,c,x,y,width,height,offset=0):
        offset=max(0,min(offset,max(0,len(self.lines)-height)))
        for row,line in enumerate(self.lines[offset:offset+height]):c.put(x,y+row,line,width)
        for row,start,size,role in self.spans:
            if offset<=row<offset+height:c.role(x+start,y+row-offset,min(size,width-start),role)
        return offset


@lru_cache(maxsize=128)
def literal_spans(text,query):
    """Visible literal matches, preserving character columns through casefold."""
    needle=query.casefold()
    if not needle:return ()
    folded=text.casefold();positions=[]
    for index,char in enumerate(text):positions.extend([index]*len(char.casefold()))
    result=[];start=0
    while True:
        at=folded.find(needle,start)
        if at<0:break
        left,right=positions[at],positions[at+len(needle)-1]+1
        if result and left<=result[-1][0]+result[-1][1]:
            previous=result.pop();left=min(left,previous[0]);right=max(right,previous[0]+previous[1])
        result.append((left,right-left));start=at+len(needle)
    return tuple(result)


class SelectList:
    """Selection and viewport are independent; only intentional selection reveals."""
    def __init__(self,rows,options=None):
        self.options=options or VIEW_OPTIONS;self.column_layout=None;self.column_values=()
        self.index=0;self.offset=0;self._height=1;self._reveal=True
        self._rows=();self._ids=();self.searching=False;self.query=''
        self.revision=0;self._match_key=None;self._matches=();self.search_scans=0
        self.replace(rows)
    @property
    def rows(self):return self._rows
    @rows.setter
    def rows(self,rows):self.replace(rows)
    def replace(self,rows,identities=None):
        rows=tuple(rows);ids=tuple(identities) if identities is not None else rows
        if len(rows)!=len(ids):raise ValueError('List identities must match rows')
        if rows==self._rows and ids==self._ids:return
        self.revision+=1;self._match_key=None
        selected=self._ids[self.index] if 0<=self.index<len(self._ids) else None
        anchor=self._ids[self.offset] if 0<=self.offset<len(self._ids) else None
        self._rows,self._ids=rows,ids
        if selected in ids:self.index=ids.index(selected)
        else:self.index=min(self.index,max(0,len(rows)-1))
        if self.offset>0 and anchor in ids:self.offset=ids.index(anchor)
        self._clamp()
    def _clamp(self):self.offset=max(0,min(self.offset,max(0,len(self.rows)-self._height)))
    def reveal(self):
        self._reveal=True
    def scroll(self,delta,height=None):
        if height is not None:self._height=max(1,height)
        self.offset+=delta;self._clamp();self._reveal=False
    def matches(self):
        key=(self.revision,self.query.casefold())
        if key!=self._match_key:
            self._matches=tuple(i for i,row in enumerate(self.rows) if key[1] in str(row).casefold()) if key[1] else ()
            self._match_key=key;self.search_scans+=bool(key[1])
        return self._matches
    def _search(self,direction=1,include=False):
        matches=self.matches()
        if not matches:return
        if direction<0:position=(bisect_right(matches,self.index) if include else bisect_left(matches,self.index))-1
        else:position=bisect_left(matches,self.index) if include else bisect_right(matches,self.index)
        self.index=matches[position%len(matches)];self.reveal()
    def search_key(self,key):
        """Query editing precedes app shortcuts; Tab accepts and yields focus."""
        if key in ('\t','backtab'):
            self.searching=False;return False
        if self.searching or key=='/' or self.query:return self.key(key)
        return False
    def key(self,key):
        if self.searching:
            if key=='\x1b':self.searching=False;self.query=''
            elif key in ('\r','\n'):self.searching=False
            elif key in ('\x7f','\b','backspace'):self.query=self.query[:-1];self._search(include=True)
            elif len(key)==1 and key.isprintable():self.query=(self.query+key)[:80];self._search(include=True)
            return True
        if key=='\x1b' and self.query:self.query='';return True
        if key=='/':self.searching=True;self.query='';return True
        if key in ('n','N') and self.query:self._search(-1 if key=='N' else 1);return True
        key={'j':'down','k':'up'}.get(key,key)
        if key not in ('up','down','home','end','pageup','pagedown'):return False
        delta={'up':-1,'down':1,'pageup':-5,'pagedown':5}.get(key,0)
        self.index=0 if key=='home' else max(0,len(self.rows)-1) if key=='end' else max(0,min(len(self.rows)-1,self.index+delta))
        self.reveal();return True
    @property
    def visible_selection(self):
        row=self.index-self.offset
        return row if self.rows and 0<=row<self._height else None
    def metrics(self):
        return dict(total=len(self.rows),selected=self.index+1 if self.rows else 0,first=self.offset+1 if self.rows else 0,last=min(len(self.rows),self.offset+self._height))
    def has_scrollbar(self,width):
        return width>=12 and self.options.scrollbars!='off' and (self.options.scrollbars=='on' or len(self.rows)>self._height)
    def position_label(self,width):
        if width<16 or self.options.counts=='off' or self.options.counts=='auto' and len(self.rows)<=self._height:return ''
        m=self.metrics();return f'{m["selected"]}/{m["total"]} · {m["first"]}–{m["last"]}'
    def viewport(self,height):
        self._height=max(1,height);self._clamp()
        if self._reveal:
            if self.index<self.offset:self.offset=self.index
            elif self.index>=self.offset+self._height:self.offset=max(0,self.index-self._height+1)
            self._clamp();self._reveal=False
    def draw(self,c,x,y,width,height):
        self.viewport(height)
        if self.column_layout is not None and not (self.searching or self.query):
            focused=c.pane_focus.get((x,max(0,y-1),width),False)
            c.put(x,max(0,y-1),('> ' if focused else '  ')+self.column_layout.text(tuple(col.title for col in self.column_layout.columns),max(1,width-2-int(self.has_scrollbar(width)))),width)
            c.role(x,max(0,y-1),width,'control' if focused else 'toolbar')
        if self.searching or self.query:
            matches=self.matches();at=bisect_left(matches,self.index);position=at+1 if at<len(matches) and matches[at]==self.index else 0
            c.put(x,max(0,y-1),'Search: /'+self.query+f'  {position}/{len(matches)}',width)
            c.role(x,max(0,y-1),width,'input' if self.searching else 'muted')
        else:
            count=self.position_label(width)
            if count:c.right_label(x,max(0,y-1),width,count)
        bar=self.has_scrollbar(width)
        for row,label in enumerate(self.rows[self.offset:self.offset+self._height]):
            index=self.offset+row
            label=self.column_layout.text(self.column_values[index],max(1,width-int(bar)-2)) if self.column_layout is not None and index<len(self.column_values) else label
            c.put(x,y+row,('> ' if index==self.index else '  ')+label,max(1,width-int(bar)))
            if self.column_layout is not None and index<len(self.column_values):
                for start,size,value,role in self.column_layout.parts(self.column_values[index],max(1,width-int(bar)-2)):c.role(x+2+start,y+row,size,role)
            if self.query:
                text=str(label)[:max(0,width-int(bar)-2)]
                for start,size in literal_spans(text,self.query):c.role(x+2+start,y+row,size,'match')
        if bar:
            thumb=min(self._height,max(1,round(self._height*self._height/max(1,len(self.rows)))))
            start=round(self.offset*max(0,self._height-thumb)/max(1,len(self.rows)-self._height))
            for row in range(self._height):c.put(x+width-1,y+row,'┃' if start<=row<start+thumb else '│',1)
    def pointer_at(self,column,row,width,height):
        if self.has_scrollbar(width) and column==width-1:
            target=round(max(0,min(height-1,row))*max(0,len(self.rows)-height)/max(1,height-1))
            self.scroll(target-self.offset,height);return False
        self.pointer(row,height);return True
    def pointer(self,row,height):
        self.index=max(0,min(len(self.rows)-1,self.offset+max(0,min(height-1,row))))
        self.reveal()


class TextInput:
    def __init__(self,text='',limit=160):self.text,self.cursor,self.limit=text,len(text),limit
    def key(self,key):
        if key=='left':self.cursor=max(0,self.cursor-1)
        elif key=='right':self.cursor=min(len(self.text),self.cursor+1)
        elif key=='home':self.cursor=0
        elif key=='end':self.cursor=len(self.text)
        elif key in ('\x7f','\b','backspace'):
            if self.cursor:self.text=self.text[:self.cursor-1]+self.text[self.cursor:];self.cursor-=1
        elif key=='delete':self.text=self.text[:self.cursor]+self.text[self.cursor+1:]
        elif len(key)==1 and ' '<=key<='~':
            if len(self.text)<self.limit:
                self.text=self.text[:self.cursor]+key+self.text[self.cursor:];self.cursor+=1
        else:return False
        return True
    def presentation(self,width,focused=True):
        """Text and semantic spans; the caret occupies a cell, never inserts text."""
        width=max(0,width)
        start=max(0,self.cursor-max(1,width-1)) if focused else 0
        text=self.text[start:start+width].ljust(width)
        spans=((0,width,"input" if focused else "body"),)
        if focused and width:spans+=((min(width-1,max(0,self.cursor-start)),1,"caret"),)
        return text,spans

    def paint(self,canvas,x,y,width,focused=True):
        text,spans=self.presentation(width,focused)
        canvas.put(x,y,text)
        for start,length,role in spans:canvas.role(x+start,y,length,role)

    def draw(self,width):
        start=max(0,self.cursor-max(1,width-1))
        return (self.text[:self.cursor]+'|'+self.text[self.cursor:])[start:start+width]


class Transcript:
    def __init__(self):self.scroll=0
    def key(self,key):
        if key not in ('up','down','pageup','pagedown'):return False
        self.scroll=max(0,self.scroll+(-3 if key in ('down','pagedown') else 3));return True
    def draw(self,c,x,y,width,height,messages):
        import textwrap
        lines=[]
        for sender,text in messages:
            lines.append(sender)
            lines.extend('  '+s for s in textwrap.wrap(text,max(1,width-2)))
            lines.append('')
        self.scroll=min(self.scroll,max(0,len(lines)-height))
        start=max(0,len(lines)-height-self.scroll)
        for i,line in enumerate(lines[start:start+height]):c.put(x,y+i,line,width)


class DataTable(SelectList):
    def __init__(self,columns,rows):
        self.columns,self.values=tuple(columns),tuple(rows)
        super().__init__(tuple('  '.join(str(v) for v in row) for row in rows))
    def draw(self,c,x,y,width,height):
        c.put(x,y,'  '+'  '.join(self.columns),width)
        super().draw(c,x,y+1,width,max(1,height-1))


def tabs(c,labels,selected,y=0,x=1,width=None):
    c.put(x,y,'  '.join('['+label+']' if i==selected else label for i,label in enumerate(labels)),width)


def toolbar_hit(actions,column):
    x=1
    for label,key in actions:
        if x<=column<x+len(label):return key
        x+=len(label)+1
    return None


def toolbar_layout(actions,width):
    """Wrap labeled actions and keep their hit regions aligned with the text."""
    lines=[''];hits=[]
    for key,title in actions:
        label='['+key+' '+title+']'
        if lines[-1] and len(lines[-1])+1+len(label)>width:lines.append('')
        x=len(lines[-1])+(1 if lines[-1] else 0)
        lines[-1]+=(' ' if lines[-1] else '')+label
        hits.append((x,len(lines)-1,len(label),key))
    return lines,hits
