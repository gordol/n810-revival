"""Small hierarchical application menu; entries hold actions, never shell strings."""
# Built-in windows have no registration descriptor. These labels only classify
# entries supplied by the running desktop; they never add applications.
BUILTIN_CATEGORIES={
    'Calendar':'Utilities', 'Library':'Utilities', 'Reader':'Utilities',
    'Workbench':'Utilities', 'Terminal':'System', 'Settings':'System',
    'Bluetooth':'System', 'Connections':'System', 'System':'System',
    'Font Preview':'Experiments', 'Radio Manager':'Radio', 'Radio':'Radio',
    'Audio Monitor':'Radio', 'CW':'Radio', 'Radio Feed':'Radio',
    'Messages':'Radio', 'Nets':'Radio', 'Services':'Radio', 'Heard':'Stations & Maps',
    'Stations':'Stations & Maps', 'Station Map':'Stations & Maps',
    'Walk':'Stations & Maps', 'Last heard':'Stations & Maps',
    'Render Debug':'Experiments', 'Kitchen Sink':'Experiments',
    'Pane Lab':'Experiments',
}


MENU_MODES=('Alphabetical','Categories')


def application_menu(entries,registrations=(),legacy=(),mode='Alphabetical'):
    """Group only actual launchable entries, retaining their original actions."""
    categories={entry.title:entry.category for entry in registrations}
    groups={};direct=[];seen=set()
    for name,action in entries:
        # Shell windows belong in the window switcher, not the app catalog.
        if name=='Terminal' or (name.startswith('Terminal ') and name[9:].isdigit()):
            name,action='Terminal','terminal:new'
        if (name,action) in seen:continue
        seen.add((name,action))
        if name=='Help':
            direct.append((name,action));continue
        category=categories.get(name,'Applications')
        if category=='Applications':category=BUILTIN_CATEGORIES.get(name,category)
        groups.setdefault(category,[]).append((name,action))
    if legacy:groups.setdefault('Legacy',[]).extend(legacy)
    return Launcher(direct,groups,mode=mode)


class Launcher:
    def __init__(self,entries,groups=None,mode='Categories'):
        self.entries=entries;self.groups=dict(groups or {});self.group=None;self.context_entries=None;self.context_title=None
        self.active=False;self.index=0;self.query='';self.set_mode(mode)
    def set_mode(self,mode):
        if mode not in MENU_MODES:raise ValueError('unknown application menu mode')
        self.mode=mode;self.group=None;self.query='';self.index=0

    def open(self):self.active=True;self.query='';self.index=0;self.group=None;self.context_entries=None;self.context_title=None
    def open_context(self,title,entries):
        self.open();self.context_title=title;self.context_entries=tuple(entries)
    def matches(self):
        if self.context_entries is not None:return [(name,action) for name,action in self.context_entries if self.query.casefold() in name.casefold()]
        if self.mode=='Alphabetical':
            rows=list(self.entries)+[row for entries in self.groups.values() for row in entries]
        else:rows=self.groups[self.group] if self.group else list(self.entries)+[(name+' ›','group:'+name) for name in self.groups]
        if self.mode=='Categories' and self.query and self.group is None:
            rows=list(rows)+[(group+' / '+name,action) for group,entries in self.groups.items() for name,action in entries]
        matches=sorted(((name,action) for name,action in rows if self.query.casefold() in name.casefold()),key=lambda row:(row[0].casefold(),row[0]))
        return [('‹ Back to Applications','menu:back')]+matches if self.group is not None else matches
    def key(self,key):
        rows=self.matches()
        if key in ('\x1b','left') and self.group is not None:self.group=None;self.query='';self.index=0
        elif key in ('\x1b',','):self.active=False
        elif key in ('up','down','\t') and rows:self.index=(self.index+(-1 if key=='up' else 1))%len(rows)
        elif key in ('\r','\n','right') and rows:
            action=rows[self.index][1]
            if action=='menu:back':self.group=None;self.query='';self.index=0
            elif action.startswith('group:'):self.group=action[6:];self.query='';self.index=1 if self.groups[self.group] else 0
            elif key!='right':self.active=False;return action
        elif key in ('\x7f','\b'):self.query=self.query[:-1];self.index=0
        elif len(key)==1 and ' '<=key<='~':self.query+=key;self.index=0
        return None
    def display_rows(self,height=None):
        rows=self.matches()
        if height is None or len(rows)+4<=height:return rows
        count=max(1,height-6);start=(self.index//count)*count
        return ([('‹ Previous','menu:previous')] if start else [])+rows[start:start+count]+([('Next ›','menu:next')] if start+count<len(rows) else [])

    def pointer(self,row,height):
        rows=self.display_rows(height)
        if not 0<=row<len(rows):self.active=False;return None
        name,action=rows[row];count=max(1,height-6)
        if action=='menu:previous':self.index=max(0,(self.index//count-1)*count)
        elif action=='menu:next':self.index=(self.index//count+1)*count
        else:
            self.index=self.matches().index((name,action))
            return self.key('\r')
        return None

    def lines(self,height=None):
        if not self.active:return ()
        selected=self.matches()[self.index] if self.matches() else None
        return (self.context_title or self.group or 'Applications','Find: '+self.query)+tuple(('> ' if row==selected else '  ')+row[0] for row in self.display_rows(height))+('','Enter opens / Esc back' if self.group else 'Enter opens / Esc closes')
