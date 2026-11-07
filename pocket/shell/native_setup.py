# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native host/tablet setup guide with explicit local file preparation."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading
import textwrap
from app_widgets import Canvas,TextInput


class N810Setup:
    def __init__(self):
        self.width=86;self.height=28
        self.manifest=TextInput('',limit=2048);self.destination=TextInput('',limit=2048)
        self.field='manifest';self.scroll=0;self._length=0;self._spans=();self._hits=[]
        self.result=None;self.error='';self.status='Choose installation files or read the first-install steps below.'
        self.pool=None;self.pending=None;self.wakeup=None;self.closed=False;self.cancelled=threading.Event();self._session_callback=None
    def bind_wakeup(self,callback):self.wakeup=callback
    def bind_session(self,callback):self._session_callback=callback
    def navigation_targets(self):
        from native_navigation import Target
        return [Target('manifest','Installation manifest','input'),Target('destination','New local kit folder','input'),
                Target('check','Check files','action','v'),Target('prepare','Prepare local kit','action','p'),
                Target('cancel','Cancel preparation','action','c'),Target('steps','Setup steps','details')]
    def navigation_focus(self):return self.field
    def navigation_input(self,key):return {'manifest':self.manifest,'destination':self.destination}.get(key)
    def navigation_accept_input(self):return self.start('check')
    def changed(self):
        nav=self.__dict__.get('_navigation')
        if nav:self.field=nav.target
        if self._session_callback:self._session_callback()
    def navigation_back(self):
        self.field='manifest'
        nav=self.__dict__.get('_navigation')
        if nav:nav.target=self.field
        return True
    def poll_interval(self):return .1 if self.pending else None
    def start(self,action):
        if self.pending:self.status='A check or preparation is already running';return True
        if not self.manifest.text.strip():self.error='Choose an INSTALLATION.json manifest first. The required files are listed below.';return True
        if action=='prepare' and not self.destination.text.strip():self.error='Choose a new local kit folder first';return True
        from n810_bootstrap import inspect,prepare
        self.error='';self.result=None;self.cancelled.clear()
        self.status='Checking installation files…' if action=='check' else 'Preparing local kit; tablet unchanged…'
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='n810-setup')
        manifest=self.manifest.text;destination=self.destination.text
        def progress(message):
            if self.closed:return
            self.status=message
            if self.wakeup:self.wakeup()
        self.pending=self.pool.submit(inspect,manifest,progress,self.cancelled) if action=='check' else self.pool.submit(prepare,manifest,destination,progress,self.cancelled)
        callback=self.wakeup
        if callback:self.pending.add_done_callback(lambda _:callback() if not self.closed else None)
        return True
    def poll(self):
        if not self.pending or not self.pending.done():return False
        pending=self.pending;self.pending=None
        try:
            self.result=pending.result()
            self.status='Local kit prepared. The tablet is not installed.' if self.result['state']=='kit_prepared' else 'Files verified. Review the matching installation guide before device actions.'
        except Exception as error:
            self.error=str(error)[:512];self.status='Cancelled; tablet unchanged.' if isinstance(error,InterruptedError) else 'Preparation unavailable; tablet unchanged.'
        return True
    def key(self,key):
        if key=='v':return self.start('check')
        if key=='p':return self.start('prepare')
        if key=='c':
            if self.pending:self.cancelled.set();self.status='Cancelling local preparation…'
            else:self.status='No preparation is running'
            return True
        if key in ('up','down','pageup','pagedown','home','end'):
            self.scroll=0 if key=='home' else self._length if key=='end' else max(0,self.scroll+(-1 if key in ('up','pageup') else 1)*(max(1,self.height//2) if key in ('pageup','pagedown') else 1));return True
        return False
    def body(self):
        result=self.result;rows=[]
        if result:
            rows += ['VERIFIED '+result['release'],'Kind: '+result['kind'],str(len(result['files']))+' files · '+str(result['total_bytes'])+' bytes']
            rows += [row['role']+': '+row['path'] for row in result['files']]
            if result.get('destination'):rows+=['Kit folder: '+result['destination']]
            rows += ['',self.status,'']
        rows += ['FIRST INSTALL — START ON THE HOST',
                 '1. Obtain a reviewed N810 system kit. Check its publisher and release; a matching hash only checks its local bytes.',
                 '2. Check INSTALLATION.json here. A system kit needs the prepared OS image, matching kernel, modules and boot guide. Source code alone is not a system image.',
                 '3. Prepare a local kit folder. This copies checked files and includes a setup receipt; it does not write the tablet.',
                 '4. Follow that kit’s boot guide. Selecting a disk, writing an OS partition, flashing or rebooting require a separate explicit action outside this preparation app.',
                 '', 'ALREADY RUNNING DEBIAN ON THE N810',
                 'Use a pocket-update kit with payload, installer and install guide. The existing Pocket release installer requires the console supervisor; it is not an OS installer.',
                 'After boot: complete the platform’s n810-setup menu if installed, then open Connections in Pocket. Configure the device’s own identity and touch calibration separately.',
                 '', 'WHAT THIS APP CAN VERIFY',
                 'Local file roles, sizes, SHA-256 checksums, matching kernel-release declaration and available space for a new kit folder.',
                 'Hardware boot compatibility, target disk identity and successful installation are not established by checking files.',
                 '', 'NO SYSTEM KIT YET?',
                 'The repository contains kernel and Pocket build tools. A redistributable Debian root filesystem, firmware policy, complete first-install image and reviewed boot procedure are still required for a distributable first-install kit.',
                 'make launches the portable desktop. make setup opens this app; neither installs Debian or silently downloads an image.']
        return rows
    def lines(self):
        self.poll();c=Canvas(self.width,self.height);self._hits=[];self._spans=[]
        c.put(0,0,'N810 Setup · host / tablet installation preparation');self._spans.append((0,0,self.width,'toolbar'))
        for y,key,label,field in ((2,'manifest','Installation manifest',self.manifest),(5,'destination','New local kit folder',self.destination)):
            c.put(0,y,label);c.put(0,y+1,field.draw(self.width));self._hits.append((y+1,key))
            self._spans.append((y+1,0,self.width,'input' if self.field==key else 'muted'))
        x=0
        for key,label in (('check','Check files'),('prepare','Prepare local kit'),('cancel','Cancel')):
            text='[ '+label+' ]';c.put(x,8,text);self._hits.append((8,key,x,len(text)))
            self._spans.append((8,x,len(text),'selected' if self.field==key else 'toolbar'));x+=len(text)+1
        body=[]
        for line in self.body():body.extend(textwrap.wrap(line,max(1,self.width-1)) or [''])
        self._length=len(body);room=max(1,self.height-13);offset=min(self.scroll,max(0,len(body)-room))
        for i,line in enumerate(body[offset:offset+room]):c.put(0,10+i,line)
        c.put(0,self.height-2,self.error or self.status)
        c.put(0,self.height-1,'Tab / Shift-Tab controls · arrows scroll steps · Enter activate · Esc back')
        return c.lines()
    def spans(self):return tuple(self._spans)
    def pointer(self,column,row,width,button=0,released=False):
        if released:return False
        if button&64:return self.key('down' if button&1 else 'up')
        if button!=0:return False
        for hit in self._hits:
            if row==hit[0] and (len(hit)==2 or hit[2]<=column<hit[2]+hit[3]):
                self.field=hit[1];nav=self.__dict__.get('_navigation')
                if nav:nav.target=self.field
                if len(hit)>2:return self.key({'check':'v','prepare':'p','cancel':'c'}[self.field])
                return True
        self.field='steps';nav=self.__dict__.get('_navigation')
        if nav:nav.target=self.field
        return True
    def session_state(self):return dict(manifest=self.manifest.text,destination=self.destination.text)
    def restore_session(self,state):
        for key in ('manifest','destination'):
            value=state.get(key)
            if isinstance(value,str) and len(value)<=2048:setattr(self,key,TextInput(value,limit=2048))
    def help_pages(self):
        return (('N810 Setup',('Enter the path to a reviewed INSTALLATION.json file. Tab moves between inputs, Check files, Prepare local kit, Cancel and Setup steps.',
                 'Check files reads local artifacts and verifies size and SHA-256. Prepare local kit copies them into a new ordinary folder; existing folders are refused.',
                 'No network fetch, device write, flashing, reboot, radio action or installer execution occurs in this app. A prepared kit is not a completed tablet installation.',
                 'System kits require system-image, kernel, modules and boot-guide roles. Update kits require payload, installer and install-guide roles.',
                 'Missing first-install images are shown as a required input, not fabricated or downloaded automatically.')),)
    def close(self):
        self.closed=True;self.wakeup=None;self.cancelled.set()
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
