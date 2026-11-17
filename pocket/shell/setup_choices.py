"""Private installation choices shared by native keyboard and pointer controls."""
from app_widgets import Canvas, TextInput
from service_policy import SERVICES, validate

class SecretInput(TextInput):
    def presentation(self, width, focused=True):
        original = self.text
        try:
            self.text = '*' * len(original)
            return super().presentation(width, focused)
        finally:
            self.text = original

class SetupChoices:
    def __init__(self):
        self.width=86; self.height=28; self.field='wifi_ssid'; self.error=''
        self.wifi_ssid=TextInput('', limit=32)
        self.wifi_pass=SecretInput('', limit=63)
        self.wifi_country=TextInput('US', limit=2)
        self.startup=validate({});self.storage_target='internal'
        self._hits=[]; self._spans=[]
    def targets(self):
        from native_navigation import Target
        return [Target('storage-target','Root storage: internal, SD, or SD A/B','action','toggle-storage'),Target('wifi_ssid','Wi-Fi network name','input'),
                Target('wifi_pass','Wi-Fi passphrase','input'),
                Target('wifi_country','Wi-Fi country','input')]+[
                Target('toggle-'+name, title+' at boot','action','toggle-'+name)
                for name,title in [('receive','UV-PRO APRS reception'),('meshcore','HTIT / MeshCore'),('reticulum','Reticulum')]]+[
                Target('options-done','Use these choices','action','options-done')]
    def input(self, key):
        return {'wifi_ssid':self.wifi_ssid,'wifi_pass':self.wifi_pass,'wifi_country':self.wifi_country}.get(key)
    def profile(self):
        value={'startup':dict(self.startup),'storage_target':self.storage_target}
        if self.wifi_ssid.text:
            if not self.wifi_pass.text:
                raise ValueError('Enter the Wi-Fi passphrase or leave Wi-Fi unconfigured')
            value['wifi']=dict(ssid=self.wifi_ssid.text,passphrase=self.wifi_pass.text,country=self.wifi_country.text.upper())
        return value
    def public_state(self):
        return dict(storage_target=self.storage_target,startup=dict(self.startup),ssid=self.wifi_ssid.text,country=self.wifi_country.text)
    def restore(self,value):
        if not isinstance(value,dict):return
        self.storage_target=value.get('storage_target') if value.get('storage_target') in ('internal','sd','sd-ab') else 'internal'
        self.startup=validate(value.get('startup',{}))
        self.wifi_ssid.text=str(value.get('ssid',''))[:32]
        self.wifi_country.text=str(value.get('country','US'))[:2]
    def key(self,key):
        if key=='toggle-storage':
            self.storage_target={'internal':'sd','sd':'sd-ab','sd-ab':'internal'}[self.storage_target];return True
        if key.startswith('toggle-') and key[7:] in SERVICES:
            name=key[7:];self.startup[name]=not self.startup[name];return True
        return False
    def lines(self):
        c=Canvas(self.width,self.height);self._hits=[];self._spans=[]
        c.put(0,0,'Install options · optional Wi-Fi and service startup')
        c.put(0,2,'[Root storage: '+({'internal':'internal MMC','sd':'SD card (single root)','sd-ab':'SD A/B + internal recovery'}[self.storage_target])+']');self._hits.append((2,'storage-target'))
        row=4
        for key,label in [('wifi_ssid','Wi-Fi network (blank = configure later)'),('wifi_pass','Wi-Fi passphrase (hidden)'),('wifi_country','Two-letter Wi-Fi country')]:
            c.put(0,row,label);row+=1
            text,roles=self.input(key).presentation(self.width,focused=self.field==key)
            c.put(0,row,text);self._hits.append((row,key))
            self._spans.extend((row,x,n,role) for x,n,role in roles);row+=2
        for name,label in [('receive','UV-PRO APRS reception'),('meshcore','HTIT / MeshCore'),('reticulum','Reticulum')]:
            key='toggle-'+name;c.put(0,row,('> ' if self.field==key else '  ')+('[x] ' if self.startup[name] else '[ ] ')+label+' at boot')
            self._hits.append((row,key));row+=1
        c.put(0,row+1,'[Use these choices]');self._hits.append((row+1,'options-done'))
        c.put(0,self.height-3,'Radio startup waits for pairing, identity and endpoint setup.')
        c.put(0,self.height-2,self.error or 'Peripheral firmware is a separate explicit setup step.')
        c.put(0,self.height-1,'Tab fields · Enter toggle/use · Esc back')
        return c.lines()
