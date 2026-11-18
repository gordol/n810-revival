"""Select a MeshCore BLE companion through a paired Classic HTIT hub."""
import re
import subprocess
import threading
import time
from pathlib import Path

from vendor.apps.domains.meshcore.hub_transport import Link


def paired_ports():
    devices = subprocess.check_output(['bluetoothctl', 'devices', 'Paired'], text=True, timeout=10)
    for row in devices.splitlines():
        match = re.fullmatch(r'Device ([0-9A-Fa-f:]{17}) Pocket-HTIT-Hub', row)
        if match:
            address = match[1]
            services = subprocess.check_output(['sdptool', 'browse', address], text=True, timeout=18)
            for service in services.split('Service Name: ')[1:]:
                channel = re.search(r'Channel: (\d+)', service)
                if service.startswith('Pocket-HTIT-Hub\n') and channel:
                    yield address + '/' + channel[1]
                    break


class Picker:
    def __init__(self, wake, provider):
        self.wake, self.provider = wake, provider
        self.stage, self.message = 'scan', 'Looking for MeshCore companions…'
        self.rows, self.index = [], 0
        self.cancel = threading.Event()
        self.pin = self.answer = ''
        self.worker(self.scan)

    def worker(self, action):
        def run():
            try:
                action()
            except Exception as error:
                self.stage, self.message = 'error', str(error)
            finally:
                self.pin = self.answer = ''
                self.wake()
        threading.Thread(target=run, daemon=True).start()

    def use(self, port, action):
        link = Link('rfcomm://' + port)
        try:
            if link.hello()[:1] != b'\x01':
                raise ValueError('Unsupported hub protocol')
            link.request(7)
            try:
                action(link)
            finally:
                link.request(8)
        finally:
            link.close()

    def scan(self):
        found = {}
        ports = list(paired_ports())
        if not ports:
            raise ValueError('Pair a Pocket-HTIT-Hub with this tablet first.')
        problems = []
        for port in ports:
            if self.cancel.is_set():return
            def collect(link):
                link.request(3)
                until = time.monotonic() + 7
                while time.monotonic() < until and not self.cancel.is_set():
                    link.read(.2)
                    while link.inbox:
                        f = link.inbox.popleft()
                        if f.service or f.op != 0x90 or len(f.data) < 8:continue
                        name = ''.join(c for c in f.data[8:].decode('utf8','replace') if c.isprintable())
                        if 'meshcore' in name.lower():
                            addr = f.data[1:7].hex(':').upper()
                            found[port, addr, f.data[0]] = name
            try:self.use(port, collect)
            except (ValueError, RuntimeError, OSError) as error:problems.append(str(error))
        self.rows = sorted(((name, *address) for address,name in found.items()),key=lambda row:(row[0].casefold(),row[1:]))
        self.stage = 'choices' if self.rows else 'error'
        self.message = 'Choose a companion' if self.rows else '; '.join(problems) or 'No advertising MeshCore companions found. Try again.'

    def choose(self):
        name, port, addr, kind = self.rows[self.index]
        self.stage, self.message = 'pair', 'Connecting to ' + name
        def pair():
            def authenticate(link):
                link.request(4,bytes([kind])+bytes.fromhex(addr.replace(':','')))
                start = renewed = time.monotonic()
                while time.monotonic()-start < 75 and not self.cancel.is_set():
                    link.read(.15)
                    while link.inbox:
                        f=link.inbox.popleft()
                        if f.service:continue
                        if f.op==0x93:return
                        if f.op==0x92:raise ValueError('Companion disconnected before authentication.')
                        if f.op==0x94:
                            self.stage,self.message='pin','Enter the six-digit BLE PIN for '+name
                            self.wake()
                    if self.answer:
                        value,self.answer=self.answer,''
                        link.request(6,value.encode('ascii'))
                    if time.monotonic()-renewed>8:
                        link.request(7);renewed=time.monotonic()
                raise ValueError('Pairing cancelled or timed out.')
            self.use(port,authenticate)
            if self.cancel.is_set():return
            from peripheral_setup import save_endpoints,receive_profile
            from meshcore_service import saved_selection
            try:station=saved_selection(self.provider.state_directory)['station']
            except (FileNotFoundError,KeyError):
                try:station=receive_profile()['callsign']
                except FileNotFoundError:station='n810'
            save_endpoints(station,meshcore=f'htit://{port}/{addr}/{kind}')
            if not self.provider.connect('local'):raise ValueError('Saved companion. Local owner is busy; attach it in Connections.')
            self.stage,self.message='done',name+' is ready. Return to Messages and choose Connect.'
        self.worker(pair)

    def key(self,key):
        if key=='\x1b' or self.stage in ('done','error') and key in ('\r','\n'):
            self.cancel.set();return False
        if self.stage=='choices':
            if key in ('down','up','\t','backtab'):self.index=(self.index+(-1 if key in ('up','backtab') else 1))%len(self.rows)
            if key in ('\r','\n'):self.choose()
        elif self.stage=='pin':
            if key in ('\x7f','\b','backspace'):self.pin=self.pin[:-1]
            elif len(key)==1 and key in '0123456789':self.pin=(self.pin+key)[:6]
            elif key in ('\r','\n') and len(self.pin)==6:
                self.answer,self.pin=self.pin,''
                self.stage,self.message='pair','Authenticating…'
        return True

    def lines(self):
        rows=['MeshCore companions',self.message]
        if self.stage=='choices':
            rows += [('> ' if i==self.index else '  ')+r[0]+'  '+r[2] for i,r in enumerate(self.rows)]
        if self.stage=='pin':rows+=['PIN: '+'*'*len(self.pin)]
        return rows+['Enter selects · Esc back']
