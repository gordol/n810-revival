"""Retained, read-only radio presentation over operator-owned connector snapshots."""
import json

from radio_state import State,adapter


def value(v):
    if v is None:return 'Unknown'
    if v is True:return 'Yes'
    if v is False:return 'No'
    if isinstance(v,dict) and v.get('kind') in ('off','ctcss','dcs'):
        return 'Off' if v['kind']=='off' else 'CTCSS '+str(v.get('value'))+' Hz' if v['kind']=='ctcss' else 'DCS '+str(v.get('value'))
    if isinstance(v,(dict,list)):return json.dumps(v,ensure_ascii=True,separators=(',',':'))
    return str(v)


def frequency(hz):return 'Unknown' if hz is None else 'Empty' if hz==0 else f'{hz/1000000:.5f} MHz'


class RadioManager:
    def presentation_interval(self):return self.state.delay()
    pages=('Status','Memories','Banks','Drafts','Profiles','Settings')
    def __init__(self,state,draft_root=None):
        self.state=state;self.page=0;self.bank=0;self.index=0;self.width=78;self.height=24
        self.hits=[];self._spans=[]
        self.drafts=None;self.message='';self.editing=None;self.fields=False;self.field=0;self.review=None
        self._draft_root=draft_root;self._drafts_attempted=False;self._drafts_error=None
        from app_widgets import AdaptivePanels,PanelSpec,SelectList
        self.memory_layout=AdaptivePanels((PanelSpec('groups','Groups',18,22),PanelSpec('channels','Channels',25,34),PanelSpec('details','Selected',28,36)),focus='channels')
        self.memory_groups=SelectList(());self.memory_channels=SelectList(());self.detail_scroll=0
    def _ensure_drafts(self,retry=False):
        if self.drafts is None and self._draft_root and (retry or not self._drafts_attempted):
            self._drafts_attempted=True
            try:
                from radio_drafts import Drafts
                self.drafts=Drafts(self._draft_root)
                if self.message==self._drafts_error:self.message=''
                self._drafts_error=None
            except (OSError,ValueError,KeyError,TypeError,ImportError) as error:
                self._drafts_error=str(error) or type(error).__name__;self.message=self._drafts_error
        return self.drafts
    def draft_groups(self):
        self._ensure_drafts()
        if not self.drafts:return []
        document=self.drafts.documents['banks' if self.page==3 else 'profiles']
        if document is None:return []
        return document['banks'] if self.page==3 else [dict(id=k,name=k,channels=[v]) for k,v in document['profiles'].items()]
    def groups(self):
        model=self.state.result['model']
        if self.page in (3,4) and (self.drafts or self._draft_root):return self.draft_groups()
        return model['snapshot']['banks'] if self.page==1 else model['presets']['banks']
    def edit_key(self,key):
        if not self._ensure_drafts():return False
        from radio_drafts import library,profiles
        from app_widgets import TextInput
        kind='banks' if self.page==3 else 'profiles'
        try:
            if self.editing:
                operation,field,input=self.editing
                if key=='\x1b':self.editing=None
                elif key in ('\r','\n'):
                    groups=self.draft_groups();group=groups[self.bank%len(groups)] if groups else None
                    if operation=='new':self.drafts.edit_bank('add_bank',name=input.text)
                    elif operation=='rename':self.drafts.edit_bank('rename_bank',bank_id=group['id'],name=input.text)
                    elif self.page==4:
                        value=input.text
                        if field in ('digital','digital_mute','audio_rx','audio_tx'):
                            if value.lower() not in ('on','off','true','false'):raise ValueError('Use on/off')
                            value=value.lower() in ('on','true')
                        self.drafts.edit_profile(group['id'],{field:value})
                    else:self.drafts.edit_bank('update_channel',bank_id=group['id'],channel_id=group['channels'][self.index]['id'],changes={field:input.text})
                    self.editing=None;self.message='Local draft changed; Save to keep it.'
                else:input.key(key)
                return True
            if key=='N':self.drafts.initialize(kind);self.message='New local draft; not saved or applied to radio.';return True
            if key=='S':self.drafts.save(kind);self.message='Saved locally. Radio unchanged.';return True
            if key=='D':self.drafts.discard(kind);self.fields=False;self.message='Local changes discarded.';return True
            if key=='f5':
                if any(self.drafts.dirty(k) for k in ('banks','profiles')):raise ValueError('Discard or save local changes before reloading.')
                self.drafts.reload();self.message='Local drafts reloaded.';return True
            groups=self.draft_groups()
            if not groups:return False
            group=groups[self.bank%len(groups)];channels=group['channels'];self.index=min(self.index,max(0,len(channels)-1))
            fields=library.FIELDS if self.page==3 else profiles.FIELDS
            if key=='e' and channels:self.fields=not self.fields;self.field=0;return True
            if self.fields:
                if key in ('up','down'):self.field=(self.field+(-1 if key=='up' else 1))%len(fields);return True
                if key in ('\r','\n'):
                    field=fields[self.field][0];value=channels[self.index].get(field)
                    self.editing=('field',field,TextInput('off' if value is None or value is False else 'on' if value is True else str(value),limit=80));return True
            if self.page==3:
                if key in ('n','r'):self.editing=('new' if key=='n' else 'rename',None,TextInput('' if key=='n' else group['name'],limit=48));return True
                if key=='c':self.drafts.edit_bank('copy_bank',bank_id=group['id']);self.bank=len(self.draft_groups())-1;self.index=0;return True
                if key=='a':self.drafts.edit_bank('add_channel',bank_id=group['id']);self.index=len(self.draft_groups()[self.bank]['channels'])-1;return True
        except (ValueError,OSError,KeyError,TypeError) as error:
            self.message=str(error);return True
        return False
    def action(self,action):
        """Semantic read intents shared by buttons, shortcuts and app commands."""
        if action not in ('read','check','cancel'):raise ValueError('Unsupported radio action')
        accepted=self.state.read_action(action)
        self.message=self.state.read_message
        return accepted
    def key(self,key):
        if self.page in (2,3,4) or self.review is not None:
            unloaded=self.drafts is None
            self._ensure_drafts(retry=key=='f5')
            if key=='f5' and unloaded and self._draft_root and self.page in (3,4):return True
        if self.page==1:
            self.sync_memory()
            listing=self.memory_groups if self.memory_layout.focus=='groups' else self.memory_channels if self.memory_layout.focus=='channels' else None
            if listing is not None and listing.search_key(key):
                if self.memory_layout.focus=='groups':
                    if self.bank!=listing.index:self.bank=listing.index;self.index=0
                else:self.index=listing.index
                return True
        if self.page==0 and key in ('r','c','k'):
            self.action({'r':'read','c':'cancel','k':'check'}[key])
            return True
        if self.review is not None:
            if key=='\x1b':self.review=None
            elif key in ('\r','\n') and self.review['can_apply_locally'] and self.drafts:
                from radio_drafts import module
                transfer=module('n810-radio-transfer.py')
                self.drafts.initialize('banks')
                self.drafts.documents['banks']=transfer.apply_pull(self.drafts.documents['banks'],self.review)
                self.review=None;self.page=3;self.bank=len(self.draft_groups())-1;self.index=0
                self.message='Copied into an unsaved local draft. Save locally to keep it.'
            return True
        if self.page==1:
            if key in ('g','t','i'):
                self.memory_layout.select({'g':'groups','t':'channels','i':'details'}[key]);return True
            if key in ('up','down','home','end','pageup','pagedown'):
                focus=self.memory_layout.focus;groups=self.groups()
                if focus=='details':self.detail_scroll=max(0,self.detail_scroll+(-1 if key in ('up','home','pageup') else 1));return True
                if focus=='groups':
                    self.memory_groups.rows=tuple(group.get('name') or 'Unnamed' for group in groups)
                    self.memory_groups.index=self.bank;self.memory_groups.key(key)
                    self.bank=self.memory_groups.index;self.index=0;self.detail_scroll=0;return True
                self.memory_channels.rows=tuple(c.get('name') or c.get('state') or 'Unnamed' for c in groups[self.bank%len(groups)]['channels']) if groups else ()
                self.memory_channels.index=self.index;self.memory_channels.key(key);self.index=max(0,self.memory_channels.index);return True
        if self.page==2:
            groups=self.state.result['model']['snapshot']['banks']
            if key=='p' and groups:
                try:
                    from radio_drafts import module
                    transfer=module('n810-radio-transfer.py')
                    snapshot=adapter.data(self.state.payload.get('catalog')).get('radio_snapshot')
                    self.review=transfer.plan_pull(snapshot,groups[self.bank]['index'])
                except (OSError,ValueError,KeyError,TypeError,ImportError) as error:self.message=str(error)
                return True
            if key in ('up','down','home','end'):
                self.bank=max(0,min(len(groups)-1,0 if key=='home' else len(groups)-1 if key=='end' else self.bank+(-1 if key=='up' else 1)))
                return True
            if key in ('\r','\n'):
                self.page=1;self.index=0;return True
        if self.page in (3,4) and self.drafts and self.edit_key(key):return True
        if key in ('\t','backtab','[',']'):
            self.page=(self.page+(-1 if key in ('backtab','[') else 1))%len(self.pages);self.bank=self.index=0;self.fields=False
        elif key in ('left','right') and self.page in (1,3,4):
            groups=self.groups()
            if groups:self.bank=(self.bank+(-1 if key=='left' else 1))%len(groups);self.index=0
        elif key in ('up','down','j','k') and self.page in (1,3,4):
            groups=self.groups();rows=groups[self.bank%len(groups)]['channels'] if groups else []
            if rows:self.index=(self.index+(-1 if key in ('up','k') else 1))%len(rows)
        elif key=='home':self.index=0
        elif key=='f5':self.state.update(True)
        else:return False
        return True
    def pointer(self,column,row,width,button=0,released=False):
        if released:return False
        if button&64:return self.key('down' if button&1 else 'up')
        if button!=0:return False
        hit=next((action for x,y,w,h,action in self.hits if x<=column<x+w and y<=row<y+h),None)
        if hit:
            if hit[0]=='page':
                if self.editing:return True
                self.page=hit[1];self.bank=self.index=0;self.fields=False
            elif hit[0]=='bank':self.bank=hit[1];self.index=0
            elif hit[0]=='memory-group':self.memory_layout.select('groups');self.bank=hit[1];self.index=0;self.detail_scroll=0
            elif hit[0]=='panel':self.memory_layout.select(hit[1])
            elif hit[0]=='local-bank':self.page=3;self.bank=hit[1];self.index=0
            elif hit[0]=='read-action':self.action(hit[1]);return True
            elif hit[0]=='action':return self.key(hit[1])
            else:self.index=hit[1];self.memory_layout.select('channels')
        return True
    def lines(self):
        if self.page in (2,3,4) or self.review is not None:self._ensure_drafts()
        self.hits=[];self._spans=[];rows=[];cursor=0
        for i,name in enumerate(self.pages):
            label=('['+name+']') if i==self.page else ' '+name+' '
            self.hits.append((cursor,0,len(label),1,('page',i)));self._spans.append((0,cursor,len(label),'tab' if i==self.page else 'muted'));cursor+=len(label)+2
        rows=['  '.join(('['+p+']') if i==self.page else ' '+p+' ' for i,p in enumerate(self.pages)), 'Browsing and local drafts do not tune or program the radio','']
        data=self.state.result;s=data['statusbar'];r=s['radio'];model=data['model']
        if self.review is not None:
            plan=self.review;proposed=plan['proposed_bank']
            rows+=['COPY DOWNLOADED BANK → LOCAL DRAFT',proposed['name'],
                   'Downloaded at: '+value(plan['source']['captured_at']),
                   str(len(proposed['channels']))+' supported channels · '+str(len(plan['blocks']))+' blockers',
                   'Creates a new bank; existing saved banks remain intact.',
                   'Source slots and raw fields are retained as provenance.','']
            rows += [str(block.get('index'))+': '+str(block['reason']) for block in plan['blocks']]
            rows += ['Enter: copy to unsaved draft' if plan['can_apply_locally'] and self.drafts else 'Copy unavailable: resolve blockers / configure local drafts.',
                     'Esc: cancel · no file or radio changes until explicit action']
            if self._drafts_error:rows.append(self._drafts_error)
        elif self.page==0:
            if self.state.can_read:
                row=len(rows);actions=(('[ Read current status r ]','read'),('[ Cancel c ]','cancel'),('[ Check k ]','check'))
                cursor=0;labels=[]
                for label,key in actions:
                    self.hits.append((cursor,row,len(label),1,('read-action',key)));self._spans.append((row,cursor,len(label),'control'));labels.append(label);cursor+=len(label)+1
                rows.append(' '.join(labels))
                problem=getattr(self.state.read_client,'endpoint_error',None)
                if problem:rows.append('Owner endpoint unavailable: '+problem)
                job=self.state.read_job;progress=job.get('progress') or {}
                completed=progress.get('completed',0);pending=progress.get('pending_command')
                label='Read: '+str(job.get('state','idle'))+' '+str(completed)+'/3'
                if pending is not None:label+=' · command '+str(pending)
                stamps=[v['observed_at'] for v in progress.get('results',{}).values()]
                if stamps:
                    import time_display
                    try:observed=time_display.now_at(max(stamps)).strftime('%H:%M:%S %Z')
                    except (OverflowError,OSError,ValueError):observed='timestamp out of range'
                    label+=' · observed '+observed
                rows.append(label)
                if job.get('error'):rows.append(str(job['error']))
                rows.append('Status/settings/APRS only; saved memories unchanged.')
            else:rows.append('Read current status unavailable: no owner endpoint configured.')
            if self.message:rows.append(self.message)
            rows+=['CONNECTION',('Console receive sockets' if getattr(self.state.source,'remote',False) else 'Device-local snapshots (SSH not used)') if self.state.source else s['ssh']['label'],s['feed']['label'],r['link']['label'],r['label'],self.state.link_observation()]
            if r['state']=='paused':
                rows.append('Periodic status polling is off.')
                if self.state.can_read:rows.append('Read current status to request a fresh snapshot.')
            if self.state.catalog_sync():rows += ['Saved radio sync: '+self.state.catalog_sync()]
            if self.state.error:rows += [self.state.error]
            status_error=adapter.data(self.state.payload.get('live')).get('radio_transport_error')
            if status_error:rows += [str(status_error)]
            rows+=['','LAST REPORTED RADIO']
            active=r['active']
            signal=r.get('indicators',{}).get('signal',{})
            raw=signal.get('raw')
            signal_text=f'{raw}/15 relative' if type(raw) is int else 'Unknown ('+str(signal.get('state','unavailable'))+')'
            rows += ['Signal: '+signal_text]
            rows += [key.replace('_',' ').capitalize()+': '+value(v) for key,v in active.items() if key!='source']
            rows += ['Feed rates: Unknown (no owner counters)','', 'SOURCES', 'Backup: '+value(model['snapshot'].get('captured_at')),'Catalog: '+value(data['sources']['catalog_captured'])]
            rows += self.state.receive_observations()
            if not self.state.path and not self.state.source:rows += ['','No connector configured; use --radio-state FILE.']
        elif self.page==1:
            rows+=self.memory_lines()
        elif self.page==5:
            rows+=['LAST REPORTED SETTINGS','']
            for name in ('settings','beacon'):
                section=r['sections'].get(name,{})
                state_name={'owner_unavailable':'Observation unavailable','unavailable':'Not reported','stale':'Last report is stale','fresh':'Recently reported','paused':'Monitoring paused'}.get(section.get('state'),'Not reported')
                age=section.get('age_seconds')
                rows+=[name.capitalize()+': '+state_name+(' · '+str(round(age))+'s ago' if isinstance(age,(int,float)) else '')]
                values=section.get('values') or {}
                rows += [key.replace('_',' ')+': '+value(v) for key,v in values.items()] or ['No settings observation available.']
                rows+=['']
            rows+=['Reported settings stay separate from local desired values.','Edit desired values under Drafts or Profiles; Save is local only.']
        elif self.page==2:
            groups=model['snapshot']['banks']
            rows+=['DOWNLOADED RADIO BANKS · same source as Memories','Enter: memories   [p Copy downloaded → Local]','']
            self.hits.append((18,4,29,1,('action','p')))
            room=max(1,self.height-len(rows)-4)
            start=max(0,self.bank-room+1)
            for index,group in enumerate(groups[start:start+room],start):
                self.hits.append((0,len(rows),self.width,1,('bank',index)))
                if index==self.bank:self._spans.append((len(rows),0,self.width,'selected'))
                rows.append(('> ' if index==self.bank else '  ')+str(group.get('index',index))+'  '+str(group.get('name') or 'Unnamed')+'  · '+str(len(group['channels']))+' memories')
            if not groups:rows+=['No downloaded banks available.']
            rows+=['','Saved drafts: '+('No saved presets available.' if not model['presets']['banks'] else str(len(model['presets']['banks']))+' banks')]
            document=self.drafts.documents['banks'] if self.drafts else None
            if document:
                rows+=['CLIENT LOCAL BANKS'+(' · Unsaved changes' if self.drafts.dirty('banks') else '')]
                for index,group in enumerate(document['banks']):
                    self.hits.append((0,len(rows),self.width,1,('local-bank',index)))
                    rows.append('  Local · '+group['name']+' · '+str(len(group['channels']))+' memories')
            if self.message:rows.append(self.message)
            rows.append('Push: unavailable · no verified radio write/readback provider')
        elif self.page in (3,4) and self.drafts:
            rows+=self.draft_lines()
        elif self.page in (3,4) and self._drafts_error:
            rows+=['Local drafts unavailable.',self._drafts_error,'F5: retry loading local drafts.']
        else:
            groups=self.groups()
            if not groups:rows += ['No downloaded memories available.' if self.page==1 else 'No saved presets available.','Unknown data is not replaced with factory presets.']
            else:
                self.bank%=len(groups);group=groups[self.bank];channels=group['channels']
                self.index=min(self.index,max(0,len(channels)-1))
                rows += [f"Bank {group.get('index',self.bank)} · {group.get('name') or 'Unnamed'} · {len(channels)} memories",'']
                x=0;labels=[]
                for i,b in enumerate(groups):
                    label=('[' if i==self.bank else ' ')+str(b.get('index',i))+':'+str(b.get('name') or 'Bank')+(']' if i==self.bank else ' ')
                    if x+len(label)>self.width:break
                    self.hits.append((x,len(rows),len(label),1,('bank',i)));labels.append(label);x+=len(label)+1
                rows.append(' '.join(labels))
                selected=channels[self.index] if channels else {};split=min(37,max(20,self.width//2))
                details=[('Name',selected.get('name')),('State',selected.get('state')),('RX',frequency(selected.get('rx_hz'))),('TX',frequency(selected.get('tx_hz'))),('RX mode',selected.get('rx_mode')),('TX mode',selected.get('tx_mode')),('Power',selected.get('power')),('Bandwidth',selected.get('bandwidth')),('RX tone',selected.get('rx_tone')),('TX tone',selected.get('tx_tone')),('TX enabled',selected.get('tx_enabled')),('Scan',selected.get('scan'))]
                room=max(1,self.height-len(rows)-2);start=max(0,self.index-room+1)
                for offset in range(max(min(room,len(channels)),min(room,len(details)))):
                    index=start+offset;left=''
                    if index<len(channels):
                        channel=channels[index];ident=channel.get('index',index)
                        left=f"{ident:>3} {channel.get('name') or channel.get('state') or 'Unnamed':<14} {frequency(channel.get('rx_hz'))}"
                        self.hits.append((0,len(rows),split,1,('memory',index)))
                        if index==self.index:self._spans.append((len(rows),0,split,'selected'))
                    detail=details[offset] if offset<len(details) else None
                    rows.append(left[:split-1].ljust(split)+'│ '+(detail[0]+': '+value(detail[1]) if detail else ''))
        footer='g Groups · t Channels · i Detail · arrows select · Tab focus · [ ] page' if self.page==1 else 'Tab: focus · [ ] page  ←/→: bank/profile  ↑/↓: select  Enter: edit field' if self.page in (3,4) and self.drafts else 'F5: reload cached data · Tab: focus · [ ] page · arrows: select'
        self._full_rows=tuple(rows)
        rows=rows[:max(1,self.height-1)];rows+=['']*max(0,self.height-1-len(rows));rows.append(footer)
        return tuple(line[:self.width] for line in rows)
    def sync_memory(self):
        groups=self.groups()
        self.bank=min(self.bank,max(0,len(groups)-1));group=groups[self.bank] if groups else None
        channels=group['channels'] if group else []
        self.index=min(self.index,max(0,len(channels)-1))
        selected=channels[self.index] if channels else {}
        self.memory_groups.rows=tuple(str(g.get('index',i))+' '+str(g.get('name') or 'Unnamed') for i,g in enumerate(groups));self.memory_groups.index=self.bank
        self.memory_channels.rows=tuple(f"{channel.get('index',i):>3} {channel.get('name') or channel.get('state') or 'Unnamed':<12} {frequency(channel.get('rx_hz'))}" for i,channel in enumerate(channels));self.memory_channels.index=self.index
        return groups,group,channels,selected

    def memory_lines(self):
        from app_widgets import Canvas
        c=Canvas(self.width,max(1,self.height-4));rects=self.memory_layout.layout(c.width,c.height)
        groups,group,channels,selected=self.sync_memory()
        if self.memory_layout.tabbed:
            cursor=0
            for panel in self.memory_layout.panels:
                label=('['+panel.title+']') if panel.key==self.memory_layout.focus else ' '+panel.title+' '
                c.put(cursor,0,label)
                self.hits.append((cursor,3,len(label),1,('panel',panel.key)));cursor+=len(label)+1
        details=[('Memory',selected.get('index')),('Name',selected.get('name')),('State',selected.get('state')),('RX',frequency(selected.get('rx_hz'))),('TX',frequency(selected.get('tx_hz'))),('RX mode',selected.get('rx_mode')),('TX mode',selected.get('tx_mode')),('Power',selected.get('power')),('Bandwidth',selected.get('bandwidth')),('RX tone',selected.get('rx_tone')),('TX tone',selected.get('tx_tone')),('TX permitted',selected.get('tx_enabled')),('Scan',selected.get('scan'))]
        for key,(x,y,width,height) in rects.items():
            title={'groups':'RADIO BANKS','channels':('Bank '+str(group.get('index',self.bank))+' · '+str(group.get('name') or 'Unnamed')+' · '+str(len(channels))+' memories') if group else 'Memories','details':'SELECTED MEMORY'}[key]
            c.put(x,y,title,width)
            self._spans.append((3+y,x,width,'selected' if key==self.memory_layout.focus else 'toolbar'))
            if key!='groups':
                for row in range(y+1,y+height):self._spans.append((3+row,x,width,'panel' if key=='channels' else 'inset'))
            else:
                for row in range(y+1,y+height):self._spans.append((3+row,x,width,'rail'))
            if key in ('groups','channels'):
                widget=self.memory_groups if key=='groups' else self.memory_channels
                heading=1 if key=='channels' else 0
                if heading:c.put(x,y+1,'  # Name         RX frequency',width)
                widget.draw(c,x,y+1+heading,width,max(1,height-1-heading))
                for row in range(min(height-1-heading,len(widget.rows)-widget.offset)):
                    index=widget.offset+row;screenrow=3+y+1+heading+row
                    self.hits.append((x,screenrow,width,1,('memory-group' if key=='groups' else 'memory',index)))
                    if index==widget.index:self._spans.append((screenrow,x,width,'selected'))
            else:
                self.detail_scroll=min(self.detail_scroll,max(0,len(details)-height+1))
                for row,(label,v) in enumerate(details[self.detail_scroll:self.detail_scroll+height-1]):c.put(x+1,y+1+row,label+': '+value(v),width-1)
                self.hits.append((x,3+y,width,height,('panel','details')))
        if not groups:c.put(0,2,'No downloaded memories available.')
        self._spans.extend((row+3,start,size,role) for row,start,size,role in c.spans)
        return list(c.lines())
    def draft_lines(self):
        if not self._ensure_drafts():return ['Local drafts unavailable.',self._drafts_error or 'No local draft root configured.','F5: retry loading local drafts.']
        from radio_drafts import library,profiles
        from app_widgets import toolbar_layout
        kind='banks' if self.page==3 else 'profiles'
        rows=['LOCAL '+kind.upper()+(' · Unsaved changes' if self.drafts.dirty(kind) else ' · Saved / unchanged')]
        actions=[('N','Create'),('S','Save locally'),('D','Discard')]
        if self.drafts.documents[kind] is not None:
            actions=[('S','Save locally'),('D','Discard'),('e','Edit fields')]+([('n','New bank'),('r','Rename'),('c','Copy'),('a','Add memory')] if self.page==3 else [])
        labels,hits=toolbar_layout(actions,self.width)
        for x,y,length,key in hits:self.hits.append((x,3+len(rows)+y,length,1,('action',key)))
        rows+=labels
        groups=self.draft_groups()
        if not groups:return rows+['No saved presets available.','Create initializes an unsaved local draft.',self.message]
        self.bank%=len(groups);group=groups[self.bank];channels=group['channels'];self.index=min(self.index,max(0,len(channels)-1))
        rows+=[self.message,'← '+str(self.bank+1)+'/'+str(len(groups))+' '+group['name']+' →']
        if self.editing and self.editing[0] in ('new','rename'):
            rows[-1]=('New bank: ' if self.editing[0]=='new' else 'Rename bank: ')+self.editing[2].draw(max(4,self.width-14))
        if self.page==3:
            rows+=[' · '.join(('['+str(i)+'] ' if i==self.index else str(i)+' ')+c['name'] for i,c in enumerate(channels)) or 'Empty bank']
        if channels:
            fields=library.FIELDS if self.page==3 else profiles.FIELDS
            selected=channels[self.index]
            for i,(field,label) in enumerate(fields):
                displayed=self.editing[2].draw(max(4,self.width-len(label)-5)) if self.editing and self.editing[1]==field else value(selected.get(field))
                rows.append(('> ' if self.fields and i==self.field else '  ')+label+': '+displayed)
        if self.editing:
            rows+=['Enter: validate draft  Esc: cancel']
        return rows
    def spans(self):return tuple(self._spans)


class RadioQuick:
    """Compact observed status and group list over the management controller."""
    def presentation_interval(self):return self.state.delay()
    def __init__(self,state,manager,open_manager):
        self.state=state;self.manager=manager;self.open_manager=open_manager
        self.width=44;self.height=17;self.index=0;self.offset=0;self.hits=[]
        from app_widgets import SelectList
        self.list=SelectList(())
    def groups(self):return self.state.result['model']['snapshot']['banks']
    def sync(self):
        self.list.rows=tuple(str(group.get('index',i))+' '+str(group.get('name') or 'Unnamed')+' · '+str(len(group['channels']))+' memories' for i,group in enumerate(self.groups()))
        self.index=min(self.index,max(0,len(self.list.rows)-1));self.list.index=self.index
    def select(self,index):
        groups=self.groups()
        if groups:
            self.index=max(0,min(len(groups)-1,index));self.list.index=self.index;self.list.reveal()
            if not self.manager.editing:
                self.manager.page=1;self.manager.bank=self.index;self.manager.index=0
    def key(self,key):
        self.sync()
        if self.list.search_key(key):self.select(self.list.index);return True
        if key in ('up','down','home','end'):
            self.select(0 if key=='home' else len(self.groups())-1 if key=='end' else self.index+(-1 if key=='up' else 1))
        elif key in ('\r','\n'):self.select(self.index);self.open_manager()
        elif key=='m':self.open_manager()
        elif key=='f5':self.state.update(True)
        else:return False
        return True
    def pointer(self,column,row,width,button=0,released=False):
        if released:return False
        if button&64:self.sync();self.list.scroll(3 if button&1 else -3,max(1,self.height-7));return True
        if button!=0:return False
        for y,index in self.hits:
            if row==y:
                if index is None:self.open_manager()
                else:self.select(index)
                return True
        return False
    def lines(self):
        radio=self.state.result['statusbar']['radio']
        rows=[radio['label'],radio['link']['label'],self.state.link_observation(),'','Downloaded groups · browse only']
        self.hits=[];groups=self.groups();room=max(1,self.height-7)
        self.sync();self.list.viewport(room);self.offset=self.list.offset
        if self.list.searching or self.list.query:rows[3]='Search: /'+self.list.query+' · '+str(len(self.list.matches()))+' matches'
        for index,group in enumerate(groups[self.offset:self.offset+room],self.offset):
            self.hits.append((len(rows),index))
            rows.append(('> ' if index==self.index else '  ')+str(group.get('index',index))+' '+str(group.get('name') or 'Unnamed')+' · '+str(len(group['channels']))+' memories')
        if not groups:rows+=['Saved radio sync: '+self.state.catalog_sync() if self.state.catalog_sync() and self.state.catalog_sync()!='synced' else 'No saved radio backup available.']
        rows+=['']*max(0,self.height-2-len(rows))
        self.hits.append((len(rows),None));rows+=['[m Open Radio Manager]','↑/↓ select group · no tuning']
        return tuple(line[:self.width] for line in rows[:self.height])
    def spans(self):
        from app_widgets import literal_spans
        result=[(row,0,self.width,'selected') for row,index in self.hits if index==self.index]
        if self.list.query:
            for row,index in self.hits:
                if index is not None and index<len(self.list.rows):
                    result.extend((row,2+start,size,'match') for start,size in literal_spans(self.list.rows[index][:max(0,self.width-2)],self.list.query))
        if self.list.searching:result.append((3,0,self.width,'input'))
        return tuple(result)
