"""First-boot setup for the installed tablet; no disk writes or firmware flashing."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
from app_widgets import Canvas, TextInput
from setup_choices import SetupChoices

GUIDE = (
    'Base install is ready. Optional radio services default off.',
    '1. Join a Wi-Fi access point, or use USB networking.',
    '2. Pair the UV-Pro / HTIT with this tablet, using its own Bluetooth address.',
    '3. Enter your callsign and explicit endpoints on the Radio page, then Save.',
    '   Saving a callsign here does not program the radio or enable transmitting.',
    '4. Select optional services at boot on the Startup page; Save applies them.',
    '   APRS Start now is separate. Start Reticulum / MeshCore in Connections.',
    '5. HTIT firmware is a laptop task. Select hub or microReticulum firmware',
    '   for your intended role; see docs/how-to/build-htit.md in the checkout.',
    '6. Reticulum creates a private identity when its local session connects.',
    '   Restore an existing identity only with the owner stopped; keep a backup.',
    '7. Prepare regional maps/terrain in Offline Data on the laptop, then copy.',
    '   Use FCC / ULS Lookup Update for the optional callsign database.',
    '   Check free storage before downloading; the internal MMC is only 2 GB.',
    '8. In Connections verify the selected owner, radio and receive status.',
    '   A paired device or a running process does not prove a radio exchange.',
)


class DeviceSetup:
    navigation_help_keys = ('?', 'help')
    def __init__(self):
        from service_policy import load
        self.width=86;self.height=28;self.page='startup';self.field='toggle-receive'
        self.choices=SetupChoices();self.choices.startup=load()
        self.tx_min=TextInput('',limit=4);self.tx_max=TextInput('',limit=4)
        self.callsign=TextInput('',limit=9);self.receive=TextInput('',limit=17)
        self.identity=TextInput('',limit=1000)
        self.meshcore=TextInput('',limit=180);self.reticulum=TextInput('',limit=180)
        self.status='Services start only after explicit selection and endpoint setup.'
        self.error='';self._hits=[];self._spans=[];self.pending=None;self.pool=None
        self.wakeup=None;self._session_callback=None
        self._restore_endpoints()
    def _restore_endpoints(self):
        from peripheral_setup import receive_profile
        from app_registry import saved_reticulum_selection
        from meshcore_service import saved_selection
        try:
            value=receive_profile();self.callsign.text=value['callsign'];self.receive.text=value['address']
        except (OSError,ValueError):pass
        state=Path.home()/'.local/state/current-world'
        for name,reader in [('meshcore',saved_selection),('reticulum',saved_reticulum_selection)]:
            try:
                value=reader(state)
                if value and value.get('mode')=='local':
                    getattr(self,name).text=value['port'];self.callsign.text=value['station']
                    if name=='reticulum':
                        self.tx_min.text=str(value['minimum_txpower']);self.tx_max.text=str(value['maximum_txpower'])
            except (OSError,ValueError):pass
    def bind_wakeup(self,callback):self.wakeup=callback
    def bind_session(self,callback):self._session_callback=callback
    def navigation_targets(self):
        from native_navigation import Target
        tabs=[Target('page-'+p,label,'action','page-'+p) for p,label in [('startup','Startup'),('radio','Radio'),('wifi','Wi-Fi'),('identity','Identity'),('guide','Checklist')]]
        if self.page=='startup':
            fields=[t for t in self.choices.targets() if t.key.startswith('toggle-')]
            fields += [Target('save','Save startup choices','action','save'),Target('start-receive','Start APRS now','action','start-receive')]
        elif self.page=='radio':
            fields=[Target(n,label,'input') for n,label in [('callsign','Station callsign'),('receive','UV-Pro Bluetooth address'),('meshcore','MeshCore endpoint'),('reticulum','RNode endpoint'),('tx_min','RNode minimum allowed TX power, dBm'),('tx_max','RNode maximum allowed TX power, dBm')]]
            fields += [Target('save-radio','Save radio profiles','action','save-radio')]
        elif self.page=='wifi':
            fields=[t for t in self.choices.targets() if t.key.startswith('wifi_')]+[Target('wifi-apply','Save and join Wi-Fi','action','wifi-apply')]
        elif self.page=='identity':
            fields=[Target('identity','Absolute private identity import/export path','input'),
                Target('identity-import','Import identity (existing identities are preserved)','action','identity-import'),
                Target('identity-export','Export identity to a new private file','action','identity-export')]
        else:fields=[]
        return tabs+fields
    def navigation_focus(self):return self.field
    def navigation_input(self,key):return self.choices.input(key) or getattr(self,key,None) if key in ('callsign','receive','meshcore','reticulum','wifi_ssid','wifi_pass','wifi_country','identity','tx_min','tx_max') else None
    def navigation_changed(self):
        nav=self.__dict__.get('_navigation')
        if nav:self.field=nav.target
    def navigation_accept_input(self):return True
    def navigation_back(self):return False
    def key(self,key):
        if key.startswith('page-'):
            self.page=key[5:];self.field=key;return True
        if key.startswith('toggle-'):return self.choices.key(key)
        if key in ('identity-import','identity-export'):
            from peripheral_setup import identity_transfer
            try:self.status=identity_transfer(key[9:],self.identity.text);self.error=''
            except (OSError,ValueError) as error:self.error=str(error)
            return True
        if key=='save':
            from service_policy import save
            try:save(self.choices.startup);self.status='Startup choices saved for the next service start. Running services keep their current state.';self.error=''
            except (OSError,ValueError) as error:self.error=str(error)
            return True
        if key=='save-radio':
            from peripheral_setup import save_endpoints
            try:
                save_endpoints(self.callsign.text.upper(),self.receive.text,self.meshcore.text,self.reticulum.text,tx_min=self.tx_min.text or None,tx_max=self.tx_max.text or None)
                self.status='Profiles saved. Pair devices separately, then connect explicitly.';self.error=''
            except (OSError,ValueError) as error:self.error=str(error)
            return True
        if key in ('wifi-apply','start-receive'):
            if self.pending:return True
            try:
                if key=='wifi-apply':
                    profile=self.choices.profile().get('wifi')
                    if not profile:raise ValueError('Enter a Wi-Fi network and passphrase')
                    payload=json.dumps(profile)
                    def work():
                        result=subprocess.run(['sudo','-n','/usr/local/sbin/n810-setup-wifi','--stdin'],input=payload,text=True,capture_output=True,timeout=70)
                        if result.returncode:raise RuntimeError(result.stderr[-300:] or 'Wi-Fi setup failed')
                        return 'Wi-Fi profile saved and connection requested.'
                    self.choices.wifi_pass.text=''
                else:
                    def work():
                        from optional_services import start
                        return '; '.join(start(['receive']))
                if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1)
                self.pending=self.pool.submit(work);self.status='Applying requested setup…';self.error=''
                if self.wakeup:self.pending.add_done_callback(lambda _:self.wakeup() if self.wakeup else None)
            except (OSError,ValueError) as error:self.error=str(error)
            return True
        return False
    def poll(self):
        if not self.pending or not self.pending.done():return False
        try:self.status=self.pending.result()
        except Exception as error:self.error=str(error)[:400]
        self.pending=None;return True
    def lines(self):
        c=Canvas(self.width,self.height);self._hits=[];self._spans=[]
        c.put(0,0,'N810 Device Setup · '+self.page.title())
        row=2
        for target in self.navigation_targets():
            if target.key.startswith('page-'):continue
            value=self.navigation_input(target.key)
            if value is not None:
                c.put(0,row,target.title);row+=1
                text,roles=value.presentation(self.width,focused=self.field==target.key)
                c.put(0,row,text);self._hits.append((row,target.key))
                self._spans.extend((row,x,n,role) for x,n,role in roles);row+=2
            else:
                label=target.title
                if target.key.startswith('toggle-'):label=('[x] ' if self.choices.startup[target.key[7:]] else '[ ] ')+label
                c.put(0,row,('> ' if self.field==target.key else '  ')+label);self._hits.append((row,target.key));row+=2
        if self.page=='guide':
            for index,line in enumerate(GUIDE):c.put(0,index+2,line)
        elif self.page=='identity':c.put(0,row,'Local session identity only; external HTIT keys stay on the board.')
        elif self.page=='radio':c.put(0,row,'Endpoints: /dev/ttyUSB0, /dev/rfcomm0, htit://… or hub://…')
        c.put(0,self.height-4,self.error or self.status)
        c.put(0,self.height-2,'[Startup]  [Radio]  [Wi-Fi]  [Identity]  [Checklist]')
        self._tabs=[(0,9,'startup'),(11,18,'radio'),(20,27,'wifi'),(29,39,'identity'),(41,52,'guide')]
        c.put(0,self.height-1,'Tab fields · Enter action · ? setup help')
        return c.lines()
    def spans(self):return tuple(self._spans)
    def pointer(self,column,row,width,button=0,released=False):
        if button!=0 or released:return False
        x,y=column,row
        if y==self.height-2:
            for left,right,page in self._tabs:
                if left<=x<right:return self.key('page-'+page)
        for row,key in self._hits:
            if row==y:
                self.field=key
                nav=self.__dict__.get('_navigation')
                if nav:nav.target=key
                return True if self.navigation_input(key) is not None else self.key(key)
        return False
    def session_state(self):return dict(page=self.page)
    def restore_session(self,state):
        if state.get('page') in ('startup','radio','wifi','identity','guide'):self.page=state['page']
    def help_pages(self):return (('Device Setup',GUIDE),)
    def close(self):
        self.choices.wifi_pass.text='';self.wakeup=None
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
