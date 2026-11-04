"""Small modal settings menu with shared live values."""
class Settings:
    def __init__(self,items):
        self.items=items
        self.index=0
        self.active=False

    def key(self,key):
        if key in ('\x1b',','):self.active=False
        elif key in ('up','k'):self.index=(self.index-1)%len(self.items)
        elif key in ('down','j','\t'):self.index=(self.index+1)%len(self.items)
        elif key in ('left','h','right','l','\r','\n'):
            self.items[self.index][2](-1 if key in ('left','h') else 1)

    def lines(self):
        if not self.active:return ()
        return ('Settings',)+tuple(f'{">" if i==self.index else " "} {name:<18} {read()}' for i,(name,read,change) in enumerate(self.items))+('', 'Up/Down select · Left/Right adjust · Esc close')


def slider(milliseconds):
    fill=max(0,min(8,round(milliseconds/40)))
    return '['+'='*fill+'-'*(8-fill)+f'] {milliseconds} ms'


class SettingsWindow:
    """Sectioned settings presentation, hosted as an ordinary window."""
    def __init__(self,sections,width=54):
        self.width=width
        self.sections=sections
        self.section=0
        self.index=0

    @property
    def items(self):return self.sections[self.section][1]

    def key(self,key):
        if key in ('[',']','\t','backtab'):
            self.section=(self.section+(-1 if key in ('[','backtab') else 1))%len(self.sections)
            self.index=0
        elif key in ('up','k'):self.index=(self.index-1)%len(self.items)
        elif key in ('down','j'):self.index=(self.index+1)%len(self.items)
        elif key in ('left','h','right','l','\r','\n'):
            self.items[self.index][2](-1 if key in ('left','h') else 1)
        else:return False
        return True

    def tabs(self):
        labels=[('['+name+']') if i==self.section else name for i,(name,_) in enumerate(self.sections)]
        start=0 if len('  '.join(labels))<=self.width else max(0,self.section-1)
        text='< ' if start else '';ranges=[]
        for i in range(start,len(labels)):
            label=labels[i]
            if len(text)+len(label)+2>self.width and ranges:break
            offset=len(text);text+=label;ranges.append((offset,len(text),i));text+='  '
        if ranges and ranges[-1][2]<len(labels)-1:text=text.rstrip()+' >'
        return text.rstrip(),ranges

    def section_at(self,column):
        text,ranges=self.tabs()
        if text.startswith('< ') and column<2:return max(0,ranges[0][2]-1)
        if text.endswith('>') and column>=len(text)-1:return min(len(self.sections)-1,ranges[-1][2]+1)
        return next((i for start,end,i in ranges if start<=column<end),self.section)

    def pointer(self,column,row,width,button=0,released=False):
        if released:return False
        if button&64:return self.key('down' if button&1 else 'up')
        if button!=0:return False
        if row==0:self.section=self.section_at(column);self.index=0
        elif 2<=row<2+len(self.items):
            self.index=row-2;self.items[self.index][2](-1 if column<width//2 else 1)
        return True

    def value(self,read):
        value=read()
        if value in ('on','off'):return ('[x] ' if value=='on' else '[ ] ')+value.capitalize()
        return value if value.startswith(('[','<','(')) else '< '+value+' >'

    def lines(self):
        tabs=self.tabs()[0]
        return (tabs,'')+tuple(f'{">" if i==self.index else " "} {name:<17} {self.value(read)}' for i,(name,read,_) in enumerate(self.items))+('', 'Tab focus | [ ] section | arrows adjust | F6 other window')


    def spans(self):
        text,ranges=self.tabs()
        spans=[(0,0,self.width,'rail')]+[(0,start,end-start,'tab' if index==self.section else 'muted') for start,end,index in ranges]
        for i,(name,read,_) in enumerate(self.items):
            row=i+2
            spans.append((row,0,self.width,'selected' if i==self.index else 'body'))
            spans.append((row,20,min(max(0,self.width-20),len(self.value(read))),'control'))
        return tuple(spans)


class SettingsManager:
    """Searchable category tiles with embedded, focused settings pages."""
    def __init__(self,categories,width=64,height=18,close=lambda:None):
        self.categories=tuple(categories);self.width=width;self.height=height;self.close=close
        self.pages={name:SettingsWindow(pages,width) for name,icon,description,pages in categories}
        self.category=None;self.query='';self.index=0;self.offset=0;self.search_focus=True
        self.hits=[];self._spans=[]

    def matches(self):
        query=self.query.casefold()
        matches=[entry for entry in self.categories if query in ' '.join([entry[0],entry[2]]+[label for _,rows in entry[3] for label,_,_ in rows]).casefold()]
        if query:matches.sort(key=lambda entry:0 if entry[0].casefold()==query else 1 if entry[0].casefold().startswith(query) else 2 if query in entry[0].casefold() else 3)
        return matches

    def overview(self):
        self.category=None;self.query='';self.index=0;self.offset=0;self.search_focus=True

    def key(self,key):
        if self.category is not None:
            page=self.pages[self.category]
            if key=='\x1b':self.overview()
            elif key in ('\t','backtab'):page.index=(page.index+(-1 if key=='backtab' else 1))%max(1,len(page.items))
            elif key in ('[',']','desktop-left','desktop-right'):
                page.key('[' if key in ('[','desktop-left') else ']')
            else:return page.key(key)
            return True
        entries=self.matches();columns=max(1,self.width//21)
        if key=='\x1b':
            if self.query:self.overview()
            else:self.close()
        elif key in ('\r','\n'):
            if entries:self.category=entries[self.index][0]
        elif key in ('up','down','left','right','\t','backtab'):
            delta={'up':-columns,'down':columns,'left':-1,'right':1,'\t':1,'backtab':-1}[key]
            if self.search_focus:self.search_focus=False
            elif entries:self.index=(self.index+delta)%len(entries)
        elif key in ('\x7f','\b','backspace'):self.query=self.query[:-1];self.index=0;self.search_focus=True
        elif len(key)==1 and key.isprintable():
            self.query=(self.query+key)[:64];self.index=0;self.search_focus=True
        else:return False
        return True

    def pointer(self,column,row,width,button=0,released=False):
        self.width=width
        if released:return False
        if button&64:return self.key('down' if button&1 else 'up')
        if button!=0:return False
        self.lines() # Hit geometry follows the same current width/height as drawing.
        action=next((action for x,y,w,h,action in reversed(self.hits) if x<=column<x+w and y<=row<y+h),None)
        if action=='back':self.overview()
        elif action=='close':self.close()
        elif action=='search':self.search_focus=True
        elif isinstance(action,int):self.index=action;self.category=self.matches()[action][0]
        elif isinstance(action,tuple) and action[0]=='item':
            page=self.pages[self.category];page.index=action[1]
            page.key('left' if column<width//2 else 'right')
        elif self.category is not None:
            page=self.pages[self.category]
            return page.pointer(column,row-2,width,button,released)
        return True

    def lines(self):
        self.hits=[];self._spans=[]
        footer=max(4,self.height-1)
        if self.category is not None:
            page=self.pages[self.category];page.width=self.width
            content=page.lines()
            # Keep the selected control visible in short windows.
            room=max(1,footer-6);start=max(0,page.index-room+1)
            rows=[('[< All Settings]  '+self.category)[:self.width],'',content[0],'']
            self._spans=[(0,0,16,'control'),(2,0,self.width,'rail')]
            self.hits.append((0,0,16,1,'back'))
            for left,right,index in page.tabs()[1]:self._spans.append((2,left,right-left,'tab' if index==page.section else 'muted'))
            for index in range(start,min(len(page.items),start+room)):
                label,read,_=page.items[index];value=page.value(read)
                label_width=max(19,min(30,max(len(item[0]) for item in page.items)));value_start=label_width+3
                y=len(rows);rows.append((('> ' if index==page.index else '  ')+label.ljust(label_width)+' '+value)[:self.width])
                self._spans.extend([(y,0,self.width,'selected' if index==page.index else 'body'),(y,value_start,max(0,min(self.width-value_start,len(value))),'control')])
                self.hits.append((0,y,self.width,1,('item',index)))
            from settings_help import help_lines
            label=page.items[page.index][0] if page.items else ''
            help_room=max(0,min(2,footer-len(rows)))
            explanation=help_lines(label,self.width,limit=help_room) if help_room else ()
            rows+=['']*max(0,footer-len(explanation)-len(rows))
            for line in explanation:
                self._spans.append((len(rows),0,self.width,'muted'));rows.append(line)
            rows+=['']*max(0,footer-len(rows))
            rows.append('Tab control | [ ] page | Esc back | F6 window'[:self.width])
        else:
            entries=self.matches();columns=max(1,self.width//21);tile=max(1,self.width//columns)
            visible=max(1,(footer-3)//5);selected_row=self.index//columns
            self.offset=max(0,min(self.offset,selected_row))
            if selected_row>=self.offset+visible:self.offset=selected_row-visible+1
            rows=[('[ Find: '+self.query+' ]')[:self.width],'','']
            self._spans=[(0,0,self.width,'input' if self.search_focus else 'rail')]
            self.hits.append((0,0,self.width,1,'search'))
            for row in range(self.offset,self.offset+visible):
                y=len(rows);lines=[' '*self.width for _ in range(5)]
                for column in range(columns):
                    index=row*columns+column
                    if index>=len(entries):continue
                    name,icon,description,_=entries[index];x=column*tile
                    art=icon if isinstance(icon,tuple) else ('',icon,'')
                    texts=tuple(line.center(tile-2) for line in art)+(name.center(tile-2),)
                    for dy,text in enumerate(texts):
                        text=text[:max(1,tile-2)];lines[dy]=lines[dy][:x]+text.ljust(tile)+lines[dy][x+tile:]
                    for dy in range(4):self._spans.append((y+dy,x,tile,'selected' if index==self.index and not self.search_focus else 'control' if dy<3 else 'body'))
                    self.hits.append((x,y,tile,4,index))
                rows.extend(lines)
            if not entries:rows[2]='No matching settings'
            rows=rows[:footer]+['']*max(0,footer-len(rows))
            if entries:rows[footer-1]=entries[self.index][2][:self.width];self._spans.append((footer-1,0,self.width,'muted'))
            rows.append('Type to find | arrows select | Enter opens'[:self.width])
        self.hits.append((max(0,self.width-9),footer,9,1,'close'))
        rows[footer]=rows[footer][:max(0,self.width-10)].ljust(max(0,self.width-9))+'[ Close ]'
        self._spans.append((footer,max(0,self.width-9),9,'control'))
        return tuple(rows)

    def spans(self):return tuple(self._spans)
