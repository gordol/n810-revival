"""Offline FCC license lookup through Pocket's lazy application interface."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import textwrap
import os
import threading
from app_widgets import Canvas,TextInput
from uls_directory import default_database,user_database,lookup


class ULSLookup:
    def __init__(self,database=None,query=lookup,updater=None):
        self.width=86;self.height=28
        self.call=TextInput('',limit=16);self.path=TextInput(str(database or default_database()),limit=1024)
        self.settings=False;self.field=0;self.result=None;self.error='';self.status='Enter a callsign and press Enter'
        self.query=query;self.pool=None;self.pending=None;self.closed=False;self.wakeup=None
        self._spans=();self.scroll=0;self._session_callback=None;self.queued_call=None;self._saved_path=None
        self._detail_length=0
        self.updater=updater;self._pending_action='lookup';self._settings_action=0
        self._download_destination=None;self._previous_database=None
        self.cancelled=threading.Event()
    def bind_wakeup(self,callback):self.wakeup=callback
    def navigation_targets(self):
        from native_navigation import Target
        return ([Target('window','ULS window','window')] if self.field==4 else [])+[Target('call','Callsign','input'),Target('settings','Database settings','action','d'),
                Target('lookup','Lookup','action','\r'),Target('results','License results','details')]
    def navigation_focus(self):return ('call','settings','lookup','results','window')[self.field]
    def navigation_input(self,key):return self.call if key=='call' else None
    def navigation_accept_input(self):return self.search()
    def changed(self):
        state=self.__dict__.get('_navigation')
        if state is not None and state.target in ('call','settings','lookup','results','window'):
            self.field=('call','settings','lookup','results','window').index(state.target)
    def _focus(self,key):
        self.field=('call','settings','lookup','results','window').index(key)
        state=self.__dict__.get('_navigation')
        if state is not None:state.target=key
    def navigation_back(self):
        # Leave the controls, preserving the query and displayed result.
        self._focus('window')
        return True
    def modal(self):return self.settings
    def navigation_modal_hint(self):return ('Database settings','Tab path/update · Enter activates · Esc back')
    def bind_session(self,callback):self._session_callback=callback
    def session_state(self):return dict(database=self.path.text)
    def restore_session(self,state):
        if isinstance(state,dict) and isinstance(state.get('database'),str) and len(state['database'])<=1024:
            self.path=TextInput(state['database'],limit=1024)
    def poll_interval(self):return .05 if self.pending else None
    def select_callsign(self,value):
        if self.pending:self.queued_call=value;return True
        self.call=TextInput(value,limit=16);self._focus('call')
        return self.search()
    def search(self):
        if self.closed or self.pending:return False
        if not self.call.text.strip():self.error='Enter a callsign first';return True
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='uls-lookup')
        self.result=None;self.error='';self.scroll=0;self.status='Looking up '+self.call.text.strip().upper()
        self._pending_action='lookup'
        self.pending=self.pool.submit(self.query,self.path.text,self.call.text)
        callback=self.wakeup
        if callback:self.pending.add_done_callback(lambda future:callback() if not self.closed else None)
        if self._session_callback:self._session_callback()
        return True
    def download_database(self):
        """Explicit user intent; importing the app never fetches network data."""
        if self.closed:return False
        if self.pending:
            self.status='Wait for the current lookup before updating FCC data'
            return True
        from data_paths import data_root
        destination=Path(self.path.text).expanduser()
        writable=destination if destination.exists() else destination.parent
        while not writable.exists() and writable!=writable.parent:writable=writable.parent
        if destination.resolve()==(data_root()/'uls.sqlite').resolve() or not os.access(writable,os.W_OK):
            destination=user_database()
        self._previous_database=self._saved_path if self._saved_path is not None else self.path.text
        self._download_destination=destination
        self.cancelled.clear()
        self.error='';self.status='Downloading FCC amateur license data…';self._pending_action='update'
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='uls-lookup')
        def progress(*values,**fields):
            if self.closed or self.cancelled.is_set():return
            self.status='FCC update: '+(' '.join(map(str,values)) or str(fields))[:180]
            if self.wakeup and not self.closed:self.wakeup()
        def run():
            updater=self.updater
            if updater is None:
                from fcc_download import update
                updater=update
            cache=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'pocket'/'fcc'
            return updater(destination,cache,progress=progress,cancelled=self.cancelled)
        self.pending=self.pool.submit(run)
        callback=self.wakeup
        if callback:self.pending.add_done_callback(lambda future:callback() if not self.closed else None)
        return True
    def cancel_update(self):
        if self.pending is None or self._pending_action!='update':return False
        self.cancelled.set();self.status='Cancelling FCC update…';return True
    def poll(self):
        if not self.pending or not self.pending.done():return False
        future=self.pending;self.pending=None
        try:
            result=future.result()
            if self._pending_action=='update':
                self.path=TextInput(str(self._download_destination),limit=1024)
                self._saved_path=self.path.text if self.settings else None
                self.result=None;self.status='FCC data updated · Enter Lookup to view a license'
                if self._session_callback:self._session_callback()
            else:self.result=result;self.status='Offline FCC lookup complete'
        except Exception as error:
            self.error=str(error)[:512]
            self.status='FCC update unavailable; previous database kept' if self._pending_action=='update' else 'Lookup unavailable'
            if self._pending_action=='update' and self.cancelled.is_set():self.error='';self.status='FCC update cancelled; previous database kept'
            if self._pending_action=='update':self.path=TextInput(self._previous_database,limit=1024)
        if self.queued_call is not None:
            call=self.queued_call;self.queued_call=None;self.select_callsign(call)
        return True
    def key(self,key):
        if self.field==4 and not self.settings:
            if key in ('\r','\n'):self._focus('call')
            return True
        if self.settings:
            if key in ('\t','backtab'):
                self._settings_action=1-self._settings_action;return True
            if key in ('\r','\n') and self._settings_action==1:
                return self.cancel_update() if self.pending and self._pending_action=='update' else self.download_database()
            if key in ('escape','\x1b','\r','\n'):
                if key in ('escape','\x1b') and self._saved_path is not None:self.path=TextInput(self._saved_path,limit=1024)
                self._saved_path=None;self.settings=False;self._focus('call')
                if self._session_callback:self._session_callback()
                return True
            return self.path.key(key)
        if key in ('\t','backtab'):
            from native_navigation import navigation
            navigation(self).cycle(-1 if key=='backtab' else 1);return True
        if self.field==1 and key in ('d','D','\r','\n'):
            self._saved_path=self.path.text;self.settings=True;self._settings_action=0;return True
        if key in ('\r','\n') and self.field in (0,2):return self.search()
        if key in ('up','down','pageup','pagedown','home','end') and (self.field==3 or key in ('pageup','pagedown')):
            self.scroll=0 if key=='home' else self._detail_length if key=='end' else max(0,self.scroll+(-1 if key in ('up','pageup') else 1)*(5 if key in ('pageup','pagedown') else 1))
            return True
        return self.call.key(key) if self.field==0 else False
    def pointer(self,column,row,width,button=0,released=False):
        if released or button!=0:return False
        if self.settings:
            if row==4:self._settings_action=0
            elif row==5:
                self._settings_action=1
                return self.cancel_update() if self.pending and self._pending_action=='update' else self.download_database()
            return True
        if row==0 and column>=max(0,width-20):
            self._saved_path=self.path.text;self.settings=True;self._settings_action=0;self._focus('settings');return True
        if row==2:self._focus('call');return True
        if row==3:self._focus('lookup');return self.search()
        if row>=5:self._focus('results');return True
        return False
    def lines(self):
        c=Canvas(self.width,self.height)
        c.put(0,0,'ULS Lookup · offline FCC',max(0,self.width-20));c.role(0,0,self.width,'toolbar')
        c.put(max(0,self.width-20),0,'[ Database settings ]');c.role(max(0,self.width-20),0,20,'selected' if self.field==1 else 'control')
        c.put(0,1,'Callsign / station SSID');self.call.paint(c,0,2,self.width,self.field==0)
        if self.settings:
            c.put(0,3,'Database settings · Enter saves / Esc cancels');self.path.paint(c,0,4,self.width,self._settings_action==0)
            c.put(0,5,'[ Cancel FCC update ]' if self.pending and self._pending_action=='update' else '[ Download/update FCC data ]')
            c.role(0,5,self.width,'input' if self._settings_action==1 else 'control')
        else:
            c.put(0,3,'[ Looking up… ]' if self.pending and self._pending_action=='lookup' else '[ Lookup ]');c.role(0,3,self.width,'input' if self.field==2 else 'control')
        body=[]
        if self.error:body=[self.error]
        elif self.result:
            result=self.result;record=result['record']
            body=[f"Source date: {result['source_data_date'] or 'unknown'} · Age: {result['source_age_days'] if result['source_age_days'] is not None else '?'} days"]
            if result['source_age_days'] is not None and result['source_age_days']>14:body+=['Warning: FCC snapshot is more than 14 days old.']
            if record:
                body+=['','Callsign: '+str(record.get('callsign') or 'Not supplied'),
                       'Name: '+str(record.get('name') or 'Not supplied'),'','FCC mailing address']
                address_fields=(('Attention','attention_line'),('Street address','street_address'),('PO Box','po_box'))
                if 'street_address' not in record:
                    body+=['Address not included in this snapshot; update FCC data']
                else:
                    body += [label+': '+str(record.get(key) or 'Not supplied') for label,key in address_fields]
                labels=(('City','city'),('State / region','region'),('Postal code','postal_code'),('Country','country'),
                        ('Operator class','license_class'),('FCC status','status'),('Radio service','service'),('License ID (USID)','usid'),
                        ('Granted','granted'),('Expires','expires'),('Last action','action_date'))
                body += [label+': '+str(record.get(key) or 'Not supplied') for label,key in labels]
                for label,key in (('FCC registration number (FRN)','frn'),('Entity type','entity_type'),('Applicant type','applicant_type')):
                    if key in record:body.append(label+': '+str(record.get(key) or 'Not supplied'))
                if record.get('source'):body+=['Record source: '+str(record['source'])]
                if record.get('updated_at'):body+=['Record updated: '+str(record['updated_at'])]
                if result.get('imported_at'):body+=['Snapshot imported: '+str(result['imported_at'])]
                body+=['','License record only. Mailing locality is not current RF position.',
                       'A matching callsign does not authenticate a sender or confirm message delivery.']
            else:body+=['','No FCC license found for '+result['base_callsign'],
                        'US licenses only; an absent record does not establish an invalid station.']
        else:body=['Use Lookup ULS from a station context menu, or enter a callsign here.',
                   'No network request, radio operation or message transmission is performed.']
        wrapped=[]
        for line in body:wrapped.extend(textwrap.wrap(line,max(1,self.width)) or [''])
        start=7 if self.settings else 5
        c.put(0,start-1,'Results');c.role(0,start-1,self.width,'input' if self.field==3 else 'heading')
        self._detail_length=len(wrapped)
        room=max(1,self.height-start-2);self.scroll=min(self.scroll,max(0,len(wrapped)-room))
        for y,line in enumerate(wrapped[self.scroll:self.scroll+room],start):c.put(0,y,line)
        c.put(0,self.height-2,self.error or self.status);c.role(0,self.height-2,self.width,'warning' if self.error else 'status')
        c.put(0,self.height-1,'Enter lookup · Tab/Shift-Tab focus · ↑↓ results');c.role(0,self.height-1,self.width,'control')
        self._spans=c.styled_spans();return c.lines()
    def spans(self):return self._spans
    def close(self):
        self.closed=True;self.wakeup=None
        self.cancelled.set()
        if self.pending:self.pending.cancel()
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
