"""System presentation from the existing connector snapshot, without collection."""
import copy
import importlib.util
from pathlib import Path
import time

root = Path(__file__).resolve().parent
path = root/'vendor/packet-console/web-console/system-read-model.py'
spec = importlib.util.spec_from_file_location('desktop_system_model', path)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


def text(value):
    return 'Unknown' if value is None else str(value)


def size(value):
    return 'Unknown' if value is None else f'{value/1048576:.1f} MiB'


class State:
    def __init__(self, connector, clock=time.time):
        self.connector = connector
        self.clock = clock
        self.current = {}
        self.previous = None
        self.observation = None
        self.raw = None
        self.tick = None
        self.attachment = {}
        self.result = model.project({}, now=clock())

    def update(self):
        self.attachment = (self.connector.payload.get('connector') or {}).get('attachment') or {}
        live = self.connector.payload.get('live') or {}
        raw = live.get('data', live)
        if not isinstance(raw, dict):
            raw = {}
        now = self.clock()
        if raw is self.raw and self.tick == int(now):
            return
        self.tick = int(now)
        system = raw.get('system') or {}
        observation = (system.get('boot_id'), system.get('observed_at'))
        # Cache reads and catalog changes must not erase the previous sample.
        if observation != self.observation:
            self.previous = self.current
            self.observation = observation
        if raw is not self.raw:
            self.current = copy.deepcopy({key: raw.get(key) for key in ('system','wifi','power','network','network_stats','connectivity')})
            self.raw = raw
        self.result = model.project(self.current, self.previous, now)

    def panel(self, width, ascii=False):
        self.update()
        result = self.result
        if result['source'] is None:
            return [('system:open', 'Bat ?  ')], {'system:open': 'unknown'}
        fresh = result['freshness'] == 'fresh'
        batteries = result['batteries']
        capacity = batteries[0].get('capacity_percent') if batteries else None
        wifi = (self.current.get('wifi') or {}).get('wlan0') or {}
        network = self.current.get('network') or {}
        parts = [('Battery', None if capacity is None else str(capacity)+'%'),
                 ('WiFi', wifi.get('state') or network.get('wlan0')),
                 ('USB', network.get('usb0'))]
        if width<120:parts=parts[:2] if width>=80 else parts[:1]
        entries, styles = [], {}
        for name, value in parts:
            role = 'unknown' if value is None else 'warning' if not fresh else 'good'
            if fresh and value in ('down', 'disconnected', 'not connected'):
                role = 'bad'
            label = name
            if name=='Battery':
                charging=batteries and batteries[0].get('status')=='Charging'
                label='Bat '+('?' if value is None else str(value))+('+' if charging else '')
            action = 'system:'+name
            entries.append((action, label+'  ')); styles[action] = role
        return entries, styles


class System:
    pages = ('System', 'Links', 'Session')

    def __init__(self, state, open_connections=None):
        self.state = state
        self.open_connections = open_connections
        self.page = 0
        self.scroll = 0
        self.width = 76
        self.height = 25
        self.hits = []
        self.connection_hit = None
        from connection_view import Links
        self.links=Links();self.link_offset=0

    def key(self, key):
        if key=='c' and self.open_connections:
            self.open_connections();return True
        if self.page==1 and self.links.key(key):self.scroll=0;return True
        if key in ('\t', 'backtab', 'left', 'right'):
            self.page = (self.page+(-1 if key in ('backtab', 'left') else 1)) % len(self.pages)
            self.scroll = 0
        elif key in ('up', 'down'):
            self.scroll = max(0, self.scroll+(-1 if key == 'up' else 1))
        elif key == 'f5':
            self.state.connector.update(True); self.state.update()
        else:
            return False
        return True

    def pointer(self, column, row, width, button=0, released=False):
        if released:
            return False
        if button & 64:
            return self.key('down' if button & 1 else 'up')
        if button != 0:
            return False
        if self.connection_hit is not None:
            y,x=self.connection_hit
            if row==y and x<=column<x+15:return self.key('c')
        for x, length, index in self.hits:
            if row == 0 and x <= column < x+length:
                self.page = index; self.scroll = 0
                return True
        if self.page==1 and self.links.pointer(row-4+self.scroll-self.link_offset):self.scroll=0;return True
        return False

    def presentation_interval(self):
        return 1. if self.state.result.get('sample_age_seconds') is not None else None

    def lines(self):
        self.state.update()
        result = self.state.result
        raw = self.state.current
        self.hits = []; cursor = 0; tabs = []
        for index, name in enumerate(self.pages):
            label = '['+name+']' if index == self.page else ' '+name+' '
            tabs.append(label); self.hits.append((cursor, len(label), index)); cursor += len(label)+2
        age = result['sample_age_seconds']
        header = ['  '.join(tabs),
                  'Observed host: '+text(result['source'])+' · '+result['freshness'],
                  'Sample age: '+('Unknown' if age is None else f'{age:.0f}s'), '']
        attachment=self.state.attachment
        binding=[]
        if attachment.get('attached'):
            device=attachment.get('service')=='device'
            binding=[('Device: ' if device else 'Receive owner: ')+str(attachment.get('owner')),
                     'Transport: '+str(attachment.get('transport') or 'local').upper()+' · '+(('device connected' if device else 'feed connected') if attachment.get('connected') else ('device disconnected' if device else 'feed disconnected')),
                     '[C Connections]  Select services and owners','']
        else:binding=['No receive service attached. [C Connections]','']
        if self.page in (0,1) and result['source'] is None:
            header=['  '.join(tabs),'System telemetry: not attached','', '']
            rows=binding+['The receive connection supplies radio traffic and owner controls.',
                          'CPU, battery and network-interface telemetry are separate.',
                          'A connected feed does not identify its Wi-Fi or USB route.']
        elif self.page == 0:
            cpu = result['cpu_busy_percent']
            rows = ['CPU busy: '+('Unknown (needs two distinct observations)' if cpu is None else f'{cpu:.1f}%'),
                    'Load (1/5/15 min): '+text(result['load_average']),
                    'RAM used / total: '+size(result['memory_used_bytes'])+' / '+size(result['memory_total_bytes']),
                    'RAM available: '+size(result['memory_available_bytes']),
                    'Swap used / total: '+size(result['swap_used_bytes'])+' / '+size(result['swap_total_bytes']), '']
            for battery in result['batteries']:
                rows += ['Battery '+text(battery['name'])+': '+text(battery['capacity_percent'])+'% · '+text(battery['status'])]
            if not result['batteries']:
                rows.append('Battery: Unknown')
            rows += ['', 'Values belong to the observed host, not this display client.']
        elif self.page == 1:
            wifi = (raw.get('wifi') or {}).get('wlan0') or {}
            rows = binding+['WiFi wlan0: '+text(wifi.get('state')),
                    'WiFi signal: '+('Unknown' if wifi.get('signal_dbm') is None else str(wifi['signal_dbm'])+' dBm'),
                    'USB network usb0: '+text((raw.get('network') or {}).get('usb0')),
                    'USB gadget / mode: Unknown (no provider)', 'Routes: Unknown (no provider)', '']
            for name, rates in result['network_interfaces'].items():
                rate = lambda value: 'Unknown' if value is None else f'{value:.1f} B/s'
                rows.append(name+' RX '+rate(rates['rx_bytes_per_second'])+' · TX '+rate(rates['tx_bytes_per_second']))
            rows += ['', 'Interface traffic includes SSH; these are not radio rates.']
            self.links.update(raw.get('connectivity'))
            self.link_offset=len(rows)+1
            rows+=['']+self.links.rows()
            if self.links.review:rows=self.links.rows();self.link_offset=0
        else:
            rows = ['SESSION CAPABILITIES',
                    'Close desktop: use the existing window-manager quit command.',
                    'Lock: Unavailable (no authentication provider)',
                    'Suspend: Unavailable (no power provider)',
                    'Shutdown: Unavailable (no power provider)', '',
                    'Closing this desktop is not an operating-system logout.',
                    'Existing login and boot configuration remain in control.']
        room = max(1, self.height-len(header)-1)
        self.scroll = min(self.scroll, max(0, len(rows)-room))
        lines = header+rows[self.scroll:self.scroll+room]
        lines += ['']*max(0, self.height-1-len(lines))
        lines += ['Tab: focus · [ ] section  C: connections  F5: reread snapshot']
        self.connection_hit=next(((y,line.index('[C Connections]')) for y,line in enumerate(lines) if '[C Connections]' in line[:self.width]),None)
        return tuple(line[:self.width] for line in lines)

    def spans(self):
        return tuple((0, x, length, 'tab' if index == self.page else 'muted') for x, length, index in self.hits)
