"""Small docked panel: layout and hit targets in terminal coordinates."""
from console_icons import APP_ICONS, app_glyph, profile_from_environment
DOCKS=('bottom','top','left','right')
MODES=('bar','auto','dock','sidebar')


class Panel:
    def __init__(self,dock='bottom'):
        if dock not in DOCKS:raise ValueError('unknown dock')
        self.dock=dock
        self.presentation='bar'
        self.cache=None
        self.hits=[]

    def layout(self,columns,rows):
        if self.dock in ('top','bottom'):
            self.rect=(0,0 if self.dock=='top' else rows-2,columns,2)
            return (0,2 if self.dock=='top' else 0,columns,rows-2)
        width=min(20,max(10,columns//4))
        self.rect=(0 if self.dock=='left' else columns-width,0,width,rows)
        return (width if self.dock=='left' else 0,0,columns-width,rows)

    def contains(self,x,y):
        px,py,w,h=self.rect
        return px<=x<px+w and py<=y<py+h

    def hit(self,x,y):
        return next((action for xx,yy,w,action in self.hits if yy==y and xx<=x<xx+w),None)

    def render(self,tabs,controls):
        signature=(self.dock,self.rect,tuple(tabs),tuple(controls))
        if signature==self.cache:return ''
        self.cache=signature
        self.hits=[]
        px,py,width,height=self.rect
        lines=[' '*width for _ in range(height)]
        def put(x,y,label,action):
            if y>=height or x>=width:return
            label=label[:width-x]
            lines[y]=lines[y][:x]+label+lines[y][x+len(label):]
            self.hits.append((px+x,py+y,len(label),action))
        if self.dock in ('top','bottom'):
            for row,entries in enumerate((tabs,controls)):
                x=0
                for action,label in entries:
                    put(x,row,label,action);x+=len(label)
        else:
            put(0,0,' DESKTOPS',None)
            row=1
            for action,label in tabs+controls:
                put(0,row,label,action);row+=1
        return ''.join(f'\x1b[{py+y+1};{px+1}H\x1b[0;37;48;5;235m{line}' for y,line in enumerate(lines))


class Panels:
    """Four possible docks; widgets have one owner and share model references."""
    def _saved_signature(self):
        return (self.mode,self.locked,tuple((p.dock,tuple(p.widgets)) for p in self.panels),self.panels.index(self.selected))

    def bind_session(self,callback):
        self.session_callback=callback;self._session_last=self._saved_signature()

    def _session_changed(self):
        callback=getattr(self,'session_callback',None)
        if callback:
            signature=self._saved_signature()
            if signature!=self._session_last:self._session_last=signature;callback()

    def __init__(self,dock='bottom',mode='bar'):
        self.icon_profile=profile_from_environment()
        first=Panel(dock);first.widgets=['desktops','windows','appearance','weather','spacer','connectivity','clock']
        self.panels=[first]
        self.selected=first
        self.drag=None
        self.pending_drag=None
        self.locked=True
        self.target=None
        self.mode='bar';self._resolved=None;self.launcher_count=2;self.overlay_bottom=0;self.set_mode(mode)

    def set_mode(self,mode):
        if mode not in MODES:raise ValueError('unknown panel presentation')
        launcher=next((p for p in self.panels if p.widgets==['apps']),None)
        if mode!='bar':
            for p in self.panels:
                if p is not launcher and 'apps' in p.widgets:p.widgets.remove('apps')
            if launcher is None:
                preferred=('left','right','bottom','top') if mode=='sidebar' else DOCKS
                edge=next((d for d in preferred if all(p.dock!=d for p in self.panels)),None)
                if edge is None:raise ValueError('No free edge for application launcher')
                launcher=Panel(edge);launcher.widgets=['apps'];self.panels.append(launcher)
        elif launcher is not None:
            self.panels.remove(launcher)
            if self.selected is launcher:self.selected=self.panels[0]
        if launcher is not None and mode in ('dock','sidebar') and mode!=self.mode:
            preferred=('bottom','top') if mode=='dock' else ('left','right')
            launcher.dock=next((d for d in preferred if all(p is launcher or p.dock!=d for p in self.panels)),launcher.dock)
        self.mode=mode;self.cancel();self._session_changed()

    def resolved_mode(self,columns):
        return ('dock' if columns>=160 else 'sidebar') if self.mode=='auto' else self.mode

    def add(self):
        free=next((d for d in DOCKS if all(p.dock!=d for p in self.panels)),None)
        if free is None:return False
        p=Panel(free);p.widgets=[];self.panels.append(p);self.selected=p
        self._session_changed()
        return True

    def remove(self,prefer_bottom=False):
        """Remove an explicit panel choice, moving its widgets instead of losing them.

        The layout edit lock protects dragging, not an explicit Settings action.
        Count reduction from the primary top panel prefers a bottom companion.
        """
        if len(self.panels)==1:return False
        removed=self.selected
        if prefer_bottom and removed is self.panels[0] and removed.dock=='top':
            companions=[p for p in self.panels if p is not removed]
            removed=next((p for p in companions if p.dock=='bottom'),companions[-1])
        remaining=[p for p in self.panels if p is not removed]
        recipient=next((p for p in remaining if p.widgets!=['apps']),remaining[0])
        recipient.widgets.extend(widget for widget in removed.widgets if widget not in recipient.widgets)
        self.panels=remaining;self.selected=recipient
        # Auto/dock/sidebar modes require a dedicated launcher. A count action
        # that merged it into the surviving bar must not recreate it on layout.
        if self.mode!='bar' and not any(p.widgets==['apps'] for p in remaining):
            self.mode='bar';self.overlay_bottom=0
        self.cancel()
        self._session_changed()
        return True

    def remove_empty(self):
        """Compatibility for older callers; removal now preserves populated panels."""
        return self.remove()

    def rotate(self):
        p=self.selected
        dock=DOCKS[(DOCKS.index(p.dock)+1)%len(DOCKS)]
        other=next((q for q in self.panels if q is not p and q.dock==dock),None)
        if other:other.dock=p.dock
        p.dock=dock
        self._session_changed()

    def layout(self,columns,rows):
        kind=self.resolved_mode(columns)
        launcher=next((p for p in self.panels if p.widgets==['apps']),None)
        if self.mode!='bar' and launcher is None:
            self.set_mode(self.mode);launcher=next(p for p in self.panels if p.widgets==['apps'])
        if launcher is not None:
            if self.mode=='auto':
                preferred=('bottom','top') if kind=='dock' else ('left','right')
                edge=next((edge for edge in preferred if all(p is launcher or p.dock!=edge for p in self.panels)),launcher.dock)
                if launcher.dock!=edge:
                    launcher.dock=edge;self._session_changed()
            # User-selected edges take precedence over presentation defaults.
            # Responsive launchers never displace the menu/status panel.
            kind='dock' if launcher.dock in ('top','bottom') else 'sidebar'
        self._resolved=kind
        for p in self.panels:p.presentation=kind if p is launcher else 'bar'
        # Reserve window space, while the scene continues beneath the floating dock.
        self.overlay_bottom=3 if launcher is not None and kind=='dock' and launcher.dock=='bottom' else 0
        top=(3 if launcher is not None and kind=='dock' and launcher.dock=='top' else 1) if any(p.dock=='top' for p in self.panels) else 0
        bottom=3 if self.overlay_bottom else (1 if any(p.dock=='bottom' for p in self.panels) else 0)
        left=4 if any(p.dock=='left' for p in self.panels) else 0
        right=4 if any(p.dock=='right' for p in self.panels) else 0
        for p in self.panels:
            if p is launcher and kind=='dock':
                width=min(columns,2+14*self.launcher_count);p.rect=((columns-width)//2,0 if p.dock=='top' else rows-3,width,3)
            elif p.dock=='top':p.rect=(0,0,columns,top)
            elif p.dock=='bottom':p.rect=(0,rows-bottom,columns,bottom)
            elif p.dock=='left':p.rect=(0,top,left,rows-top-bottom)
            else:p.rect=(columns-right,top,right,rows-top-bottom)
            p.cache=None
        return left,top,columns-left-right,rows-top-bottom

    def at(self,x,y):
        return next((p for p in self.panels if p.contains(x,y)),None)

    def pointer(self,button,x,y,released=False):
        p=self.at(x,y)
        if self.pending_drag:
            widget,source,sx,sy=self.pending_drag
            if released:self.pending_drag=None;return None
            if not self.locked and button&32 and max(abs(x-sx),abs(y-sy))>=2:
                self.drag=(widget,source);self.pending_drag=None
            else:return None
        if released and self.drag:
            widget,source=self.drag
            if p and p.widgets==['apps']:p=None
            if p:
                source.widgets.remove(widget)
                action=p.hit(x,y)
                target=action[7:] if action and action.startswith('widget:') else None
                index=p.widgets.index(target) if target in p.widgets else len(p.widgets)
                p.widgets.insert(index,widget)
                self.selected=p
                self._session_changed()
            self.drag=self.target=None
            for q in self.panels:q.cache=None
            return 'layout' if p else None
        if self.drag:
            self.target=p
            for q in self.panels:q.cache=None
            return None
        if p and button==0 and not released:
            self.selected=p
            self._session_changed()
            action=p.hit(x,y)
            if action and action.startswith('widget:') and not self.locked:
                self.pending_drag=(action[7:],p,x,y)
                return None
            return action
        return None

    def minimize_targets(self,names,origin):
        names=tuple(names)
        signature=(names,origin,tuple(tuple(p.hits) for p in self.panels),self.selected.rect)
        previous=getattr(self,'_minimize_cache',None)
        if previous is not None and previous[0]==signature:
            # Host clears its targets on resize; never lend out the cache itself.
            return previous[1].copy()
        ox,oy=origin
        hits=[hit for p in self.panels for hit in p.hits]
        by_action={}
        for hit in hits:by_action.setdefault(hit[3],hit)
        fallback=by_action.get('key:,')
        if fallback is None:
            px,py,_,_=self.selected.rect
            fallback=(px,py,12,None)
        targets={}
        for name in names:
            x,y,width,_=by_action.get(name,fallback)
            targets[name]=(x-ox,y-oy,max(12,width),1)
        self._minimize_cache=(signature,targets.copy())
        return targets

    def cancel(self):
        self.drag=self.target=self.pending_drag=None
        for p in self.panels:p.cache=None

    def set_locked(self,locked):
        self.locked=bool(locked);self.cancel();self._session_changed()

    def render(self,widgets,states=None,icons=None,sink=None):
        states=dict(states or {});icons=icons or {}
        for action,_ in widgets.get('apps',()):
            if action.startswith('launch:window:'):states[action]=states.get(action[14:],'minimized')
        output=''
        for p in self.panels:
            signature=(self.locked,self.icon_profile,p.presentation,tuple(sorted(icons.items())),tuple(sorted(states.items())),p.rect,tuple(p.widgets),tuple((name,tuple(widgets.get(name,()))) for name in p.widgets),self.drag[0] if self.drag else None,self.target is p)
            if p.cache==signature:continue
            p.cache=signature;p.hits=[]
            px,py,width,height=p.rect
            lines=[' '*width for _ in range(height)]
            styles=[['open']*width for _ in range(height)]
            def put(x,y,label,action):
                if y>=height or x>=width:return
                label=label[:width-x]
                lines[y]=lines[y][:x]+label+lines[y][x+len(label):]
                styles[y][x:x+len(label)]=[states.get(action,'open')]*len(label)
                p.hits.append((px+x,py+y,len(label),action))
            if p.widgets==['apps'] and p.presentation in ('dock','sidebar'):
                # One Unicode symbol plus a name; no multi-cell icon artwork.
                symbols={'APRS':'◆','Messages':'≡','Nets':'■','Directory':'≡','Services':'┼','Terminal':'>','Settings':'☼'}
                for i,(action,label) in enumerate(widgets.get('apps',())):
                    title=label.replace('>_ ','').replace('[i] ','')
                    x,y=(1+i*14,1) if p.presentation=='dock' else (0,i*4+1)
                    badge='●' if states.get(action)=='focused' else '·' if states.get(action)=='open' else ' '
                    symbol=app_glyph(title,self.icon_profile,symbols.get(title,'·'))
                    if p.presentation=='dock':put(x,y,(badge+symbol+' '+title[:9]).ljust(14),action)
                    else:
                        put(x,y,symbol.center(4),action)
                        put(x,y+1,{'Messages':'Msgs','Directory':'Dir','Services':'Svc','Terminal':'Term','Settings':'Set'}.get(title,title)[:4],action)
                color=235
                for y,line in enumerate(lines):
                    x=0
                    while x<width:
                        end=x+1
                        while end<width and styles[y][end]==styles[y][x]:end+=1
                        focused=styles[y][x]=='focused'
                        if sink:sink(px+x,py+y,line[x:end],str(97 if focused else 37),238 if focused else color)
                        else:output+=f'\x1b[{py+y+1};{px+x+1}H\x1b[0;{97 if focused else 37};48;5;{238 if focused else color}m{line[x:end]}'
                        x=end
                continue
            if not p.widgets:put(0,0,' · ',None)
            row=0
            cursor=0
            if not self.locked and p is self.panels[0]:
                label=' Edit panels [Done] '
                put(0,0,label,'panel:done')
                if p.dock in ('top','bottom'):cursor=len(label)
                else:row=1
            for position,name in enumerate(p.widgets):
                entries=widgets.get(name,())
                if name=='apps' and self.icon_profile:
                    entries=tuple((action,app_glyph(label,self.icon_profile)+' '+label if label in APP_ICONS else label) for action,label in entries)
                icon_entries={}
                if name in ('windows','apps') and p.presentation=='dock':
                    converted=[]
                    for action,label in entries:
                        if action.startswith(('key:','wm:')):continue
                        title=label.strip(' ●○▔·') if name=='windows' else label.strip()
                        icon=icons.get(action) or ('>_' if 'Terminal' in title else '[i]' if 'Settings' in title else title[:3])
                        badge={'focused':'*','open':'o','rolled':'^','minimized':'-'}[states.get(action,'open')] if name=='windows' else '+'
                        text=f' {badge} {icon} '.center(14)
                        icon_entries[action]=(title[:13],14)
                        converted.append((action,text))
                    entries=converted
                after=p.widgets[position+1:]
                if name=='spacer':
                    if p.dock in ('top','bottom'):
                        trailing=sum((2 if self.locked else 4)+sum(len(label) for _,label in widgets.get(n,())) for n in after if widgets.get(n,()))
                        end=max(cursor,width-trailing+2)
                        if end>cursor and not self.locked:put(cursor,row,'⋮ '[:end-cursor],'widget:spacer')
                        cursor=end
                    else:
                        trailing=sum(1+len(widgets.get(n,())) for n in after if widgets.get(n,()))
                        row=max(row,height-trailing)
                    continue
                reserve=0
                if 'spacer' in after:
                    tail=after[after.index('spacer')+1:]
                    reserve=sum(2+sum(len(label) for _,label in widgets.get(n,())) for n in tail if widgets.get(n,()))
                available=width-reserve
                if not entries:continue
                if name=='windows' and p.dock in ('top','bottom') and entries:
                    per=max(0,(available-cursor-(0 if self.locked else 2))//len(entries))
                    if per>=5:entries=[(action,label if len(label)<=per else label[:per-2]+'… ') for action,label in entries]
                if p.dock in ('top','bottom') and cursor+(0 if self.locked else 2)+sum(len(label) for _,label in entries)>available:
                    continue
                handle='' if self.locked else '⋮ '
                if handle:put(cursor if p.dock in ('top','bottom') else 0,row,handle,'widget:'+name)
                if p.dock in ('top','bottom'):
                    x=cursor+len(handle)
                    for action,label in entries:
                        put(x,row,label,action)
                        if action in icon_entries:put(x,row+1,icon_entries[action][0][:len(label)].center(len(label)),action)
                        x+=len(label)
                    cursor=x+2
                else:
                    row+=1
                    for action,label in entries:
                        if not (name in ('apps','windows') and p.presentation=='sidebar'):put(0,row,label,action)
                        if name in ('apps','windows') and p.presentation=='sidebar':
                            title=label.strip(' ●○▔·')
                            icon=icons.get(action) or ('>_' if 'Terminal' in title else '[i]' if 'Settings' in title else title[:3])
                            badge={'focused':'*','open':'o','rolled':'^','minimized':'-'}[states.get(action,'open')] if name=='windows' else '+'
                            put(0,row,(badge+icon.center(max(1,width-1)))[:width],action)
                            put(0,row+1,title[:width].center(width),action);row+=1
                        row+=1
            color=238 if self.drag and self.target is p else 235
            palette={'focused':('97',238),'open':('37',color),'rolled':('33',color),'minimized':('90',color),'good':('92',color),'bluetooth':('94',color),'warning':('93',color),'unknown':('90',color),'bad':('91',color)}
            for y,line in enumerate(lines):
                x=0
                while x<width:
                    end=x+1
                    while end<width and styles[y][end]==styles[y][x]:end+=1
                    foreground,background=palette[styles[y][x]]
                    if sink:sink(px+x,py+y,line[x:end],foreground,background)
                    else:output+=f'\x1b[{py+y+1};{px+x+1}H\x1b[0;{foreground};48;5;{background}m{line[x:end]}'
                    x=end
        return output
