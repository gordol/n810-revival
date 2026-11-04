"""RNode USB preparation and BLE connection controls over the selected owner."""
from app_widgets import toolbar_layout


class RNodeBluetooth:
    def __init__(self, host=None, *, app_context):
        self.service = app_context.services.get('reticulum')
        self.registry = getattr(app_context, 'registry', None)
        self.width, self.height = 72, 22
        self.state, self.notice, self.editing = {}, '', None
        self.value = ''
        self.hits, self._spans = [], []
        self.choosing_hub = False
        self.hub_index = 0

    def poll_interval(self): return None
    def open(self): self.poll()
    def poll(self):
        if self.service is not None: self.state = self.service.snapshot()
    def readiness_sources(self):
        if self.service is None: return ()
        if hasattr(self.service, 'readiness_sources'): return self.service.readiness_sources(self.poll_ready)
        return ((self.service.readable, self.poll_ready),)
    def poll_ready(self):
        self.service.drain(); self.poll()
    def modal(self): return self.editing is not None or self.choosing_hub

    def hub_choices(self):
        hubs = self.state.get('hubs', ())
        self.hub_index = min(self.hub_index, max(0, len(hubs)-1))
        start = max(0, self.hub_index-5)
        return [(str(index+1), hub) for index, hub in enumerate(hubs[start:start+7], start)]

    def choose_hub(self, hub):
        if self.request('select_connection', dict(connection='hub', port=hub['port'])):
            self.choosing_hub = False
        return True

    def request(self, action, payload=None):
        self.poll()
        if self.service is None or action not in self.state.get('capabilities', ()):
            self.notice = 'This owner cannot perform that action. Select the local RNode owner and disconnect its radio first.'
            return False
        try:
            self.service.request(action, payload or {})
            self.notice = 'Request sent; waiting for owner events.'
            return True
        except (OSError, ValueError, RuntimeError) as error:
            self.notice = str(error)
            return False

    def key(self, key):
        if self.choosing_hub:
            self.poll()
            hubs = self.state.get('hubs', ())
            if key in ('\x1b', 'escape'): self.choosing_hub = False
            elif key in ('up', 'down'):
                self.hub_index = max(0, min(len(hubs)-1, self.hub_index + (1 if key=='down' else -1)))
            elif key in ('\r', '\n', 'enter') and hubs: return self.choose_hub(hubs[self.hub_index])
            else:
                for number, hub in self.hub_choices():
                    if key == number: return self.choose_hub(hub)
            return True
        radio = next(iter(self.state.get('radios', ())), {})
        if self.editing is not None:
            if key in ('\x1b', 'escape'): self.editing = None
            elif key in ('\r', '\n', 'enter'):
                self.request('select_connection', dict(connection=self.editing, port=self.value))
                self.editing = None
            elif key in ('backspace', '\x7f', '\b'): self.value = self.value[:-1]
            elif len(key) == 1 and key.isprintable() and len(self.value) < 126: self.value += key
            return True
        if key == 'h':
            if self.request('list_hubs'):
                self.choosing_hub = True
                self.hub_index = 0
        elif key in ('e', 'u'):
            self.editing = 'ble' if key == 'e' else 'usb'
            current = radio.get('port', '')
            self.value = current if radio.get('connection') == self.editing else 'ble://' if key == 'e' else '/dev/'
        elif key == 'r' and self.registry is not None:
            self.registry.open('reticulum')
        elif key in ('1', '2', 's', 'p', 'x'):
            self.request({'1':'rnode_bluetooth_on', '2':'rnode_pairing_mode', 's':'ble_scan', 'p':'ble_pair', 'x':'ble_stop'}[key])
        elif key in ('c', 'd'):
            self.request('connect' if key == 'c' else 'disconnect', dict(station=radio.get('station_id'), radio=radio.get('radio_id')))
        else: return False
        return True

    def navigation_targets(self):
        from native_navigation import Target
        if self.choosing_hub:
            return [Target('hub:'+hub['id'], hub['label'], 'action', key) for key, hub in self.hub_choices()]
        if self.editing is not None: return [Target('content', 'Device name or port', 'details')]
        return [Target('action:' + key, label, 'action', key) for key, label in self.actions()]

    def actions(self):
        caps = self.state.get('capabilities', ())
        result = []
        if 'select_connection' in caps: result += [('u','USB port'),('e','BLE device')]
        if 'list_hubs' in caps: result.append(('h','Shared hub'))
        for key, label, action in (('1','Enable Bluetooth','rnode_bluetooth_on'),('2','Pairing mode','rnode_pairing_mode'),
                                  ('s','Discover','ble_scan'),('p','Pair','ble_pair'),('x','Stop setup','ble_stop'),
                                  ('c','Connect radio','connect'),('d','Disconnect radio','disconnect')):
            if action in caps: result.append((key,label))
        return result + [('r','Reticulum')]

    def pointer(self, column, row, width=None, button=0, released=False):
        if released or button != 0: return False
        for x, y, length, key in self.hits:
            if row == y and x <= column < x + length: return self.key(key)
        return False

    def lines(self):
        import textwrap
        self.poll()
        radio = next(iter(self.state.get('radios', ())), {})
        bluetooth = self.state.get('bluetooth') or {}
        clean = lambda value: ''.join(c for c in str(value or '') if c.isprintable())
        rows = ['RNode connections',
                'Radio: ' + clean(radio.get('radio_id')) + ' · ' + clean(self.state.get('radio_state')),
                'Connection: ' + clean(radio.get('connection')) + ' · ' + clean(radio.get('port')),
                '']
        if radio.get('connection') in ('usb', 'ble'):
            rows += ['Bluetooth setup: ' + clean(bluetooth.get('phase', 'unavailable'))]
        if radio.get('connection') == 'ble':
            rows += ['Authenticated RNode: ' + ('verified' if bluetooth.get('authenticated') is True else 'not verified')]
        self.hits = []
        if self.choosing_hub:
            rows += ['Select a shared hub LoRa service:']
            for number, hub in self.hub_choices():
                index = len(rows)
                rows.append('['+number+'] '+clean(hub['label']))
                self.hits.append((0,index,self.width,number))
            if not self.state.get('hubs'):
                rows += ['No configured hubs. Configure an HTIT connection first.']
            rows += ['Enter selects; Escape cancels.']
        elif self.editing is not None:
            rows += ['BLE: enter ble:// followed by the exact advertised name or identifier.' if self.editing == 'ble' else 'Enter the USB serial port on the owning computer.',
                     self.value + '▏', 'Enter saves the selection; Escape cancels.']
        else:
            labels, hits = toolbar_layout(self.actions(), self.width)
            top = len(rows)
            rows += labels
            self.hits = [(x, top + y, length, key) for x, y, length, key in hits]
            if radio.get('connection') == 'hub':
                rows += ['', 'LoRa uses the hub’s shared connection.', 'Disconnect radio releases LoRa only.']
            else:
                rows += ['', 'USB: enable Bluetooth, then start pairing mode.',
                         'BLE: select its name, Pair, then Connect radio.',
                         'macOS handles the pairing-code prompt. Discovery is not proof of pairing.', '']
            if bluetooth.get('phase') == 'authenticating':
                rows += textwrap.wrap('Waiting for OS authentication. Enter the current RNode code in the macOS prompt. '
                                      'No prompt? Stop setup, choose USB port, then Connect radio.', self.width)
            for device in bluetooth.get('devices', ())[:8]:
                rows.append(clean(device.get('name')) + ' · ' + clean(device.get('rssi')) + ' dBm')
        message = bluetooth.get('error') or self.state.get('error') or self.notice
        if message:
            detail = textwrap.wrap(clean(message), max(1, self.width))[:max(1, self.height - 5)]
            rows = rows[:max(0, self.height - len(detail))] + detail
        return [row[:self.width] for row in rows[:self.height]]

    def close(self): pass


def descriptor():
    return dict(id='rnode-bluetooth', title='RNode connections', category='Radio',
                preferred_size=(76, 24), minimum_size=(40, 14), factory=RNodeBluetooth,
                description='Select a direct RNode or a shared hub LoRa service',
                uses=(dict(id='reticulum', required=False),))
