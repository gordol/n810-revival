"""Explicit host-side regional map/terrain preparation using the shared CLI."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import hashlib
import os
import queue
import shutil
import signal
import subprocess
import threading
import textwrap
import sys
from app_widgets import Canvas, TextInput

POCKET = Path(__file__).resolve().parents[1]


def prepare(action, bbox, url, output, spacing, cancelled=None, process_changed=None, host=""):
    if action=='verify':
        tool=Path('/usr/local/bin/n810-install-reference-data')
        if not tool.is_file():tool=Path(__file__).resolve().parents[1]/'tools/install_reference_data.py'
        if not tool.is_file():raise ValueError('Reference-data verifier is not installed')
        result=subprocess.run([sys.executable,str(tool),'--verify',str(Path(output).expanduser())],capture_output=True,text=True)
        if result.returncode:raise ValueError((result.stderr or result.stdout)[-500:])
        return 'Reference data verified: '+result.stdout.strip()
    if action=='push':
        commands=[[sys.executable,str(POCKET/'tools/push_reference_data.py'),str(Path(output).expanduser()),host]]
    else:
        if action not in ('plan','build'):raise ValueError('Choose Plan or Download and build')
        coordinates=[float(value) for value in bbox.split()]
        from math import isfinite
        if len(coordinates)!=4 or not all(isfinite(v) for v in coordinates) or not -180<=coordinates[0]<coordinates[2]<=180 or not -90<coordinates[1]<coordinates[3]<90:
            raise ValueError('Enter west south east north bounds')
        spacing=float(spacing)
        if not isfinite(spacing) or spacing<1:raise ValueError('Elevation spacing must be at least one metre')
        suffix='.osm' if url.endswith('.osm') else '.osm.pbf'
        if not url.strip():
            west,south,east,north=coordinates
            if (east-west)*(north-south)>0.25:
                raise ValueError('For an area over 0.25 square degrees, enter a matching OSM PBF extract URL')
            url='https://api.openstreetmap.org/api/0.6/map?bbox='+','.join(map(str,coordinates))
            suffix='.osm'
        if not url.startswith('https://') or any(ord(c)<32 for c in url):raise ValueError('Enter an HTTPS URL for a matching OSM PBF extract')
        directory=Path(output).expanduser().resolve()
        if directory==Path('/') or directory.is_relative_to('/dev'):raise ValueError('Choose a local data folder')
        script=POCKET/'tools/maps.py'
        if not script.is_file():raise ValueError('Map preparation requires the Pocket source package with tools/maps.py')
        interpreter=[sys.executable]
        if action=='build' and os.environ.get('POCKET_TERMUX')=='1':
            if not shutil.which('proot-distro'):
                raise ValueError('Run make mobile-map-deps once in Termux to install the on-phone GIS tools')
            directory.mkdir(parents=True,exist_ok=True)
            # Keep file names identical on both sides so saved selections and receipts work in Termux.
            mounts=[POCKET] if directory.is_relative_to(POCKET) else [POCKET,directory]
            interpreter=['proot-distro','login','pocket-maps']
            for mount in mounts:
                interpreter.extend(['--bind',str(mount)])
            interpreter.extend(['--','/usr/bin/python3'])
        base=[*interpreter,str(script),'--bbox',*map(str,coordinates),'--url',url,
              '--source',str(directory/'downloads'/('region-'+hashlib.sha256(url.encode()).hexdigest()[:16]+suffix)),'--output',str(directory),
              '--spacing-m',str(spacing),'--workers','1' if os.environ.get('POCKET_TERMUX')=='1' else '2']
        commands=[[*base,step] for step in (('plan',) if action=='plan' else ('configure','download','build','elevation'))]
        if action=='build':
            commands.append([sys.executable,str(POCKET/'tools/install_reference_data.py'),'--source',str(directory),'--plan'])
    outputs=[]
    for command in commands:
        if cancelled is not None and cancelled.is_set():raise InterruptedError('Preparation cancelled; completed inputs remain reusable')
        process=subprocess.Popen(command,cwd=POCKET,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        if process_changed:process_changed(process)
        if cancelled is not None and cancelled.is_set():os.killpg(process.pid,signal.SIGTERM)
        stdout,stderr=process.communicate()
        if process_changed:process_changed(None)
        if process.returncode:raise RuntimeError((stderr or stdout)[-1500:] or 'Preparation cancelled')
        outputs.append(stdout[-2500:])
    if action=='build':return 'Built offline maps and terrain in '+str(directory)
    return '\n'.join(outputs)[-5000:]


class OfflineData:
    navigation_help_keys=('?','help')
    def __init__(self):
        self.device_only=not (POCKET/'tools/maps.py').is_file()
        self.width=86;self.height=28;self.field='output' if self.device_only else 'bbox'
        self.host=TextInput('',limit=253);self.bbox=TextInput('',limit=100);self.url=TextInput('',limit=500)
        self.output=TextInput(os.environ.get('POCKET_DATA_ROOT') or str(POCKET/'data'),limit=1000);self.spacing=TextInput('15',limit=8)
        if self.device_only:
            from data_paths import data_root
            self.output=TextInput(str(data_root()),limit=1000)
        self.status='Install prepared data from the laptop, then verify it here.' if self.device_only else 'Select your area. Plan makes no network requests.';self.result='';self.error=''
        self.picker=None;self.pending=None;self.pool=None;self.cancelled=threading.Event();self.process=None;self.wakeup=None;self._session_callback=None;self._hits=[];self._spans=[]
    def bind_wakeup(self,callback):self.wakeup=callback
    def bind_session(self,callback):self._session_callback=callback
    def changed(self):
        if self._session_callback:self._session_callback()
    def navigation_targets(self):
        from native_navigation import Target
        if self.picker:
            return [Target('retry','Open browser again','action','retry'),Target('back','Back to Offline Data','action','back')]
        if self.device_only:return [Target('output','Installed reference-data folder','input'),Target('verify','Verify installed maps and elevation','action','verify')]
        return [Target('pick','Choose area on world map','action','pick')]+[Target(k,v,'input') for k,v in [('bbox','Bounds: west south east north'),('url','OSM PBF URL (optional for small areas)'),('output','Local data folder'),('spacing','Elevation spacing, metres')]]+[
            Target('plan','Plan / reuse / estimated size','action','plan'),Target('build','Download and build this area','action','build'),
            Target('host','N810 SSH hostname or alias','input'),Target('push','Push prepared maps to N810','action','push')]
    def navigation_focus(self):return self.field
    def navigation_input(self,key):return getattr(self,key,None) if key in ('bbox','url','output','spacing','host') else None
    def navigation_changed(self):
        nav=self.__dict__.get('_navigation')
        if nav:self.field=nav.target
    def navigation_accept_input(self):return True
    def key(self,key):
        if self.picker and key=='back':
            self.picker.close();self.picker=None
            self.field='pick';self.error='';self.status='Choose an area or enter bounds.'
            return True
        if key in ('pick','retry') and not self.device_only and not self.pending:
            from area_picker import Picker
            try:
                if self.picker is None:
                    try:bounds=list(map(float,self.bbox.text.split()))
                    except ValueError:bounds=None
                    self.picker=Picker(bounds,self.wakeup)
                self.field='retry'
                self.error=''
                self.picker.launch()
            except (OSError,subprocess.SubprocessError) as error:
                self.error='Browser did not open.' if self.picker else str(error)
            return True
        if key not in ('plan','build','verify','push'):return False
        if self.pending:return True
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1)
        self.error=''
        self.status={'verify':'Verifying installed reference data…','push':'Sending maps to the N810…',
                     'plan':'Planning…','build':'Downloading and building. Keep this app open.'}[key]
        self.cancelled.clear()
        self.pending=self.pool.submit(prepare,key,self.bbox.text,self.url.text,self.output.text,self.spacing.text,self.cancelled,lambda process:setattr(self,'process',process),self.host.text)
        if self.wakeup:self.pending.add_done_callback(lambda _:self.wakeup() if self.wakeup else None)
        return True
    def poll(self):
        if self.picker:
            try:bounds=self.picker.result.get_nowait()
            except queue.Empty:pass
            else:
                self.bbox.text=' '.join(str(value) for value in bounds)
                self.bbox.cursor=len(self.bbox.text)
                self.picker.close();self.picker=None
                self.status='Area selected. Choose Plan or Download and build.';self.error=''
                self.field='bbox';self.changed();return True
        if not self.pending or not self.pending.done():return False
        try:self.result=self.pending.result();self.status=self.result[-350:] or 'Completed.'
        except Exception as error:self.error=str(error)[-500:]
        self.pending=None;return True
    def lines(self):
        c=Canvas(self.width,self.height);self._hits=[];self._spans=[]
        if self.picker:
            c.put(0,0,'World map · waiting for your selection')
            for row,target in enumerate(self.navigation_targets(),1):
                c.put(0,row,'[ '+target.title+' ]')
                self._hits.append((row,target.key))
            message=self.error or 'If your browser did not open:'
            c.put(0,4,message)
            hint='Open this address in your browser.'
            if os.environ.get('POCKET_TERMUX')=='1':
                hint='In Termux, long-press the printed map link, or enter this address in your browser.'
            rows=textwrap.wrap(hint,self.width)
            for row,line in enumerate(rows,5):c.put(0,row,line)
            for offset in range(0,len(self.picker.url),self.width):
                c.put(0,5+len(rows)+offset//self.width,self.picker.url[offset:offset+self.width])
            return c.lines()
        c.put(0,0,'Offline Data · installed maps and elevation' if self.device_only else 'Offline Data · prepare and transfer regional maps and terrain')
        compact=self.height<25
        row=1 if compact else 2
        for target in self.navigation_targets():
            value=self.navigation_input(target.key)
            if value is not None:
                c.put(0,row,target.title);row+=1
                text,roles=value.presentation(self.width,focused=self.field==target.key)
                c.put(0,row,text);self._hits.append((row,target.key))
                self._spans.extend((row,x,n,role) for x,n,role in roles);row+=1 if compact else 2
            else:
                c.put(0,row,'[ '+target.title+' ]');self._hits.append((row,target.key));row+=1
        c.put(0,self.height-(2 if compact else 5),self.error or self.status)
        if not compact:
            if self.device_only:hint='Restart Pocket after installing prepared data.'
            elif os.environ.get('POCKET_TERMUX')=='1':hint='make mobile prepares the on-phone builder.'
            else:hint='Build dependencies: make maps-deps. Map transfers use SSH.'
            c.put(0,self.height-3,hint)
            c.put(0,self.height-2,'FCC download is in ULS Lookup.')
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
    def session_state(self):return {key:getattr(self,key).text for key in ('bbox','url','output','spacing','host')}
    def restore_session(self,state):
        for key in ('bbox','url','output','spacing','host'):
            if isinstance(state.get(key),str):getattr(self,key).text=state[key][:1000]
    def help_pages(self):
        return (('Offline Data',('Select a bounding box and an OSM extract covering it. Plan reports reusable inputs and estimated elevation size without downloading. Download and build acquires the extract and USGS fine elevation and derives display levels locally.',
            'In Termux, make mobile prepares the map builder. On a laptop, use make maps-deps. For small areas leave the extract URL blank to download OSM data for the entered bounds. Large areas can exceed the N810 internal MMC. Keep raw downloads on the laptop; transfer selected runtime maps and elevation only. See pocket/docs/map-data.md.',
            'Push uses your SSH configuration to sign in as nokia. Enter the prepared folder and tablet hostname. The tablet verifies staged files before installation. Restart Pocket on the tablet after success.',
            'FCC data is an independent optional download in ULS Lookup. A base install remains usable without these datasets.')),)
    def close(self):
        if self.picker:self.picker.close();self.picker=None
        self.wakeup=None;self.cancelled.set()
        if self.process is not None:
            try:os.killpg(self.process.pid,signal.SIGTERM)
            except ProcessLookupError:pass
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
