"""Explicit host-side regional map/terrain preparation using the shared CLI."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import os
import signal
import subprocess
import threading
import sys
from app_widgets import Canvas, TextInput

REPOSITORY = Path(__file__).resolve().parents[2]


def prepare(action, bbox, url, output, spacing, cancelled=None, process_changed=None):
    if action=='verify':
        tool=Path('/usr/local/bin/n810-install-reference-data')
        if not tool.is_file():tool=Path(__file__).resolve().parents[1]/'tools/install_reference_data.py'
        if not tool.is_file():raise ValueError('Reference-data verifier is not installed')
        result=subprocess.run([sys.executable,str(tool),'--verify',str(Path(output).expanduser())],capture_output=True,text=True)
        if result.returncode:raise ValueError((result.stderr or result.stdout)[-500:])
        return 'Reference data verified: '+result.stdout.strip()
    if action not in ('plan','build'):raise ValueError('Choose Plan or Download and build')
    coordinates=[float(value) for value in bbox.split()]
    from math import isfinite
    if len(coordinates)!=4 or not all(isfinite(v) for v in coordinates) or not -180<=coordinates[0]<coordinates[2]<=180 or not -90<coordinates[1]<coordinates[3]<90:
        raise ValueError('Enter west south east north bounds')
    spacing=float(spacing)
    if not isfinite(spacing) or spacing<1:raise ValueError('Elevation spacing must be at least one metre')
    if not url.startswith('https://') or any(ord(c)<32 for c in url):raise ValueError('Enter an HTTPS URL for a matching OSM PBF extract')
    directory=Path(output).expanduser().absolute()
    if directory==Path('/') or directory.is_relative_to('/dev'):raise ValueError('Choose a local data folder')
    script=REPOSITORY/'pocket/tools/maps.py'
    if not script.is_file():raise ValueError('Build regional data on the laptop checkout, then transfer prepared outputs')
    base=[sys.executable,str(script),'--bbox',*map(str,coordinates),'--url',url,
          '--source',str(directory/'downloads'/('region-'+hashlib.sha256(url.encode()).hexdigest()[:16]+'.osm.pbf')),'--output',str(directory),
          '--spacing-m',str(spacing)]
    # Argument vectors bypass Make/shell interpolation of user-provided URLs.
    outputs=[]
    for command in (('plan',) if action=='plan' else ('configure','download','build','elevation')):
        if cancelled is not None and cancelled.is_set():raise InterruptedError('Preparation cancelled; completed inputs remain reusable')
        process=subprocess.Popen([*base,command],cwd=REPOSITORY/'pocket',stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        if process_changed:process_changed(process)
        if cancelled is not None and cancelled.is_set():os.killpg(process.pid,signal.SIGTERM)
        stdout,stderr=process.communicate()
        if process_changed:process_changed(None)
        if process.returncode:raise RuntimeError((stderr or stdout)[-1500:] or 'Preparation cancelled')
        outputs.append(stdout[-2500:])
    return '\n'.join(outputs)[-5000:]


class OfflineData:
    navigation_help_keys=('?','help')
    def __init__(self):
        self.device_only=not (REPOSITORY/'pocket/tools/maps.py').is_file()
        self.width=86;self.height=28;self.field='output' if self.device_only else 'bbox'
        self.bbox=TextInput('',limit=100);self.url=TextInput('',limit=500)
        self.output=TextInput(str(REPOSITORY/'pocket/data'),limit=1000);self.spacing=TextInput('15',limit=8)
        if self.device_only:
            from data_paths import data_root
            self.output=TextInput(str(data_root()),limit=1000)
        self.status='Install prepared data from the laptop, then verify it here.' if self.device_only else 'Select your area. Plan makes no network requests.';self.result='';self.error=''
        self.pending=None;self.pool=None;self.cancelled=threading.Event();self.process=None;self.wakeup=None;self._session_callback=None;self._hits=[];self._spans=[]
    def bind_wakeup(self,callback):self.wakeup=callback
    def bind_session(self,callback):self._session_callback=callback
    def changed(self):
        if self._session_callback:self._session_callback()
    def navigation_targets(self):
        from native_navigation import Target
        if self.device_only:return [Target('output','Installed reference-data folder','input'),Target('verify','Verify installed maps and elevation','action','verify')]
        return [Target(k,v,'input') for k,v in [('bbox','Bounds: west south east north'),('url','OSM PBF extract HTTPS URL'),('output','Local data folder'),('spacing','Elevation spacing, metres')]]+[
            Target('plan','Plan / reuse / estimated size','action','plan'),Target('build','Download and build this area','action','build')]
    def navigation_focus(self):return self.field
    def navigation_input(self,key):return getattr(self,key,None) if key in ('bbox','url','output','spacing') else None
    def navigation_changed(self):
        nav=self.__dict__.get('_navigation')
        if nav:self.field=nav.target
    def navigation_accept_input(self):return True
    def key(self,key):
        if key not in ('plan','build','verify'):return False
        if self.pending:return True
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1)
        self.error='';self.status='Verifying installed reference data…' if key=='verify' else 'Planning…' if key=='plan' else 'Downloading and building; this can take time. Keep this app open.'
        self.cancelled.clear()
        self.pending=self.pool.submit(prepare,key,self.bbox.text,self.url.text,self.output.text,self.spacing.text,self.cancelled,lambda process:setattr(self,'process',process))
        if self.wakeup:self.pending.add_done_callback(lambda _:self.wakeup() if self.wakeup else None)
        return True
    def poll(self):
        if not self.pending or not self.pending.done():return False
        try:self.result=self.pending.result();self.status=self.result[-350:] or 'Completed.'
        except Exception as error:self.error=str(error)[-500:]
        self.pending=None;return True
    def lines(self):
        c=Canvas(self.width,self.height);self._hits=[];self._spans=[]
        c.put(0,0,'Offline Data · installed maps and elevation' if self.device_only else 'Offline Data · prepare regional maps and terrain on your laptop')
        row=2
        for target in self.navigation_targets():
            value=self.navigation_input(target.key)
            if value is not None:
                c.put(0,row,target.title);row+=1
                text,roles=value.presentation(self.width,focused=self.field==target.key)
                c.put(0,row,text);self._hits.append((row,target.key))
                self._spans.extend((row,x,n,role) for x,n,role in roles);row+=2
            else:
                c.put(0,row,'[ '+target.title+' ]');self._hits.append((row,target.key));row+=1
        c.put(0,self.height-5,self.error or self.status)
        c.put(0,self.height-3,'Use n810-install-reference-data on prepared data; restart Pocket after installing.' if self.device_only else 'Prerequisite: make maps-deps in the laptop pocket checkout.')
        c.put(0,self.height-2,'Transfer prepared data separately; FCC download is in ULS Lookup.')
        c.put(0,self.height-1,'Tab fields · Enter action · ? help')
        return c.lines()
    def spans(self):return tuple(self._spans)
    def pointer(self,column,row,width,button=0,released=False):
        if button!=0 or released:return False
        selected_row=row
        for row,key in self._hits:
            if row==selected_row:
                self.field=key
                nav=self.__dict__.get('_navigation')
                if nav:nav.target=key
                return True if self.navigation_input(key) is not None else self.key(key)
        return False
    def session_state(self):return {key:getattr(self,key).text for key in ('bbox','url','output','spacing')}
    def restore_session(self,state):
        for key in ('bbox','url','output','spacing'):
            if isinstance(state.get(key),str):getattr(self,key).text=state[key][:1000]
    def help_pages(self):
        return (('Offline Data',('Select a bounding box and an OSM extract covering it. Plan reports reusable inputs and estimated elevation size without downloading. Download and build acquires the extract and USGS fine elevation and derives display levels locally.',
            'Prepare dependencies once with make maps-deps in the laptop pocket checkout. Large areas can exceed the N810 internal MMC. Keep raw downloads on the laptop; transfer selected runtime maps and elevation only. See pocket/docs/map-data.md.',
            'FCC data is an independent optional download in ULS Lookup. A base install remains usable without these datasets.')),)
    def close(self):
        self.wakeup=None;self.cancelled.set()
        if self.process is not None:
            try:os.killpg(self.process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
