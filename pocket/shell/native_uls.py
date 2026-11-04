"""Offline FCC license lookup through Pocket's lazy application interface."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import textwrap
from app_widgets import Canvas,TextInput
from uls_directory import default_database,lookup


class ULSLookup:
    def __init__(self,database=None,query=lookup):
        self.width=86;self.height=28
        self.call=TextInput('',limit=16);self.path=TextInput(str(database or default_database()),limit=1024)
        self.settings=False;self.field=0;self.result=None;self.error='';self.status='Enter a callsign and press Enter'
        self.query=query;self.pool=None;self.pending=None;self.closed=False;self.wakeup=None
        self._spans=();self.scroll=0;self._session_callback=None;self.queued_call=None;self._saved_path=None
    def bind_wakeup(self,callback):self.wakeup=callback
    def modal(self):return True
    def navigation_modal_hint(self):return ('ULS input','Enter lookup · Tab settings · PgUp/PgDn results')
    def bind_session(self,callback):self._session_callback=callback
    def session_state(self):return dict(database=self.path.text)
    def restore_session(self,state):
        if isinstance(state,dict) and isinstance(state.get('database'),str) and len(state['database'])<=1024:
            self.path=TextInput(state['database'],limit=1024)
    def poll_interval(self):return .05 if self.pending else None
    def select_callsign(self,value):
        if self.pending:self.queued_call=value;return True
        self.call=TextInput(value,limit=16);self.field=0
        return self.search()
    def search(self):
        if self.closed or self.pending:return False
        if not self.call.text.strip():self.error='Enter a callsign first';return True
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='uls-lookup')
        self.result=None;self.error='';self.scroll=0;self.status='Looking up '+self.call.text.strip().upper()
        self.pending=self.pool.submit(self.query,self.path.text,self.call.text)
        callback=self.wakeup
        if callback:self.pending.add_done_callback(lambda future:callback() if not self.closed else None)
        if self._session_callback:self._session_callback()
        return True
    def poll(self):
        if not self.pending or not self.pending.done():return False
        future=self.pending;self.pending=None
        try:
            self.result=future.result();self.status='Offline FCC lookup complete'
        except Exception as error:self.error=str(error)[:512];self.status='Lookup unavailable'
        if self.queued_call is not None:
            call=self.queued_call;self.queued_call=None;self.select_callsign(call)
        return True
    def key(self,key):
        if self.settings:
            if key in ('escape','\x1b','\r','\n'):
                if key in ('escape','\x1b') and self._saved_path is not None:self.path=TextInput(self._saved_path,limit=1024)
                self._saved_path=None;self.settings=False;self.field=0
                if self._session_callback:self._session_callback()
                return True
            return self.path.key(key)
        if key in ('\t','backtab'):self.field=1-self.field;return True
        if self.field==1 and key in ('d','D','\r','\n'):
            self._saved_path=self.path.text;self.settings=True;return True
        if key in ('\r','\n'):return self.search()
        if key in ('pageup','pagedown'):
            self.scroll=max(0,self.scroll+(-5 if key=='pageup' else 5));return True
        return self.call.key(key) if self.field==0 else False
    def pointer(self,column,row,width,button=0,released=False):
        if released or button!=0:return False
        if row==0 and column>=max(0,width-20):self._saved_path=self.path.text;self.settings=True;self.field=1;return True
        if row==2:self.field=0;return True
        if row==4 and self.settings:self.field=1;return True
        if row==(5 if self.settings else 3):return self.search()
        return False
    def lines(self):
        c=Canvas(self.width,self.height)
        c.put(0,0,'ULS Lookup · offline FCC',max(0,self.width-20));c.role(0,0,self.width,'toolbar')
        c.put(max(0,self.width-20),0,'[ Database settings ]');c.role(max(0,self.width-20),0,20,'selected' if self.field==1 else 'control')
        c.put(0,1,'Callsign / station SSID');c.put(0,2,self.call.draw(self.width))
        c.role(0,2,self.width,'input' if self.field==0 else 'body')
        if self.settings:
            c.put(0,3,'Database settings · Enter saves / Esc closes');c.put(0,4,self.path.draw(self.width));c.role(0,4,self.width,'input')
        c.put(0,5 if self.settings else 3,'[ Looking up… ]' if self.pending else '[ Lookup ]');c.role(0,5 if self.settings else 3,self.width,'control')
        body=[]
        if self.error:body=[self.error]
        elif self.result:
            result=self.result;record=result['record']
            body=[f"Source date: {result['source_data_date'] or 'unknown'} · Age: {result['source_age_days'] if result['source_age_days'] is not None else '?'} days"]
            if result['source_age_days'] is not None and result['source_age_days']>14:body+=['Warning: FCC snapshot is more than 14 days old.']
            if record:
                labels=(('Callsign','callsign'),('Name','name'),('City','city'),('State / region','region'),('Postal code','postal_code'),
                        ('Operator class','license_class'),('FCC status','status'),('Granted','granted'),('Expires','expires'),('Last action','action_date'))
                body+=['']+[label+': '+str(record.get(key) or 'Not supplied') for label,key in labels]
                body+=['','License record only. Mailing locality is not current RF position.',
                       'A matching callsign does not authenticate a sender or confirm message delivery.']
            else:body+=['','No FCC license found for '+result['base_callsign'],
                        'US licenses only; an absent record does not establish an invalid station.']
        else:body=['Use Lookup ULS from a station context menu, or enter a callsign here.',
                   'No network request, radio operation or message transmission is performed.']
        wrapped=[]
        for line in body:wrapped.extend(textwrap.wrap(line,max(1,self.width)) or [''])
        start=7 if self.settings else 5
        room=max(1,self.height-start-2);self.scroll=min(self.scroll,max(0,len(wrapped)-room))
        for y,line in enumerate(wrapped[self.scroll:self.scroll+room],start):c.put(0,y,line)
        c.put(0,self.height-2,self.error or self.status);c.role(0,self.height-2,self.width,'warning' if self.error else 'status')
        c.put(0,self.height-1,'Enter lookup · PgUp/PgDn results · Tab settings');c.role(0,self.height-1,self.width,'control')
        self._spans=c.styled_spans();return c.lines()
    def spans(self):return self._spans
    def close(self):
        self.closed=True;self.wakeup=None
        if self.pending:self.pending.cancel()
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
