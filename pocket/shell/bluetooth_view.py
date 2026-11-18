"""Bluetooth presentation over cached feed-owner facts and explicit intents."""
import math
import time
from app_widgets import toolbar_layout

ACTIONS = ('controller_on', 'controller_off', 'receive_start', 'receive_stop', 'radio_disconnect')
KEYS = dict(zip(('1', '0', 'r', 's', 'd'), ACTIONS))


def clean(value, limit=96):
    return ''.join(c for c in str(value) if c.isprintable())[:limit]


def project(snapshot, online=False, hardware=None):
    """Controller power, reception intent and radio connection are independent."""
    value = snapshot if isinstance(snapshot, dict) else {}
    valid = type(value.get('version')) is int and value['version'] == 1 and value.get('type') == 'state'
    controller = value.get('controller') if valid else None
    reception = value.get('reception') if valid else None
    radio = value.get('radio') if valid else None
    controller = controller if isinstance(controller, dict) else {}
    reception = reception if isinstance(reception, dict) else {}
    radio = radio if isinstance(radio, dict) else {}
    connected = bool(online and valid)
    powered = controller.get('powered') if connected and type(controller.get('powered')) is bool else None
    enabled = reception.get('enabled') if connected and type(reception.get('enabled')) is bool else None
    link = radio.get('connected') if connected and type(radio.get('connected')) is bool else None
    devices = controller.get('devices') if connected else None
    devices = devices if isinstance(devices, list) else []
    rows = tuple(clean(row.get('name') or row.get('address') or row.get('id') or 'Unnamed device')
                 for row in devices[:32] if isinstance(row, dict) and row.get('connected') is True)
    capabilities = value.get('capabilities') if connected else None
    capabilities = capabilities if isinstance(capabilities, list) else []
    available = connected and controller.get('available') is True
    if isinstance(hardware, dict):
        stamp = hardware.get('observed_at')
        observed = hardware.get('powered')
        if (hardware.get('available') is True and type(observed) is bool and
                type(stamp) in (int, float) and math.isfinite(stamp) and
                0 <= time.time() - stamp <= 15):
            powered = observed
            available = True
    return dict(online=connected, powered=powered, enabled=enabled, radio_connected=link,
                controller_available=available,
                devices=rows, suspended_reason=clean(reception.get('suspended_reason') or ''),
                stopping=connected and reception.get('stopping') is True,
                capabilities=tuple(action for action in ACTIONS if action in capabilities and
                                   (available or not action.startswith('controller_'))))


class State:
    """No collectors, transport, timers, or hardware access in presentation."""
    def __init__(self, snapshot=lambda: None, online=lambda: False, request=None, feedback=lambda: '', hardware=lambda: None, controller_request=None, controller_available=lambda: True):
        self.snapshot = snapshot
        self.online = online
        self.request_intent = request
        self.feedback = feedback
        self.controller_request = controller_request
        self.controller_available = controller_available
        self.hardware = hardware
        self.message = ''

    def read(self):
        result=project(self.snapshot(), self.online(), self.hardware())
        if result['controller_available'] and self.controller_available() and callable(self.controller_request):
            result['capabilities']=tuple(dict.fromkeys((*result['capabilities'],'controller_on','controller_off')))
        return result

    def available(self, action):
        result = self.read()
        return (callable(self.controller_request) if action.startswith('controller_') and self.controller_request else callable(self.request_intent)) and action in result['capabilities']

    def request(self, action):
        if action not in ACTIONS or not self.available(action):
            self.message = 'Bluetooth controls unavailable from this owner.'
            return False
        try:
            request=self.controller_request if action.startswith('controller_') and self.controller_request else self.request_intent
            accepted = request(action)
        except (OSError, ValueError, RuntimeError) as error:
            self.message = clean(error)
            return False
        self.message = '' if accepted else 'Owner is busy or unavailable.'
        return bool(accepted)

    def panel(self, ascii=False):
        result = self.read()
        powered = result['powered']
        role = 'unknown' if powered is None else 'bluetooth' if powered else 'warning'
        return [('bluetooth:open', 'BT  ')], {'bluetooth:open': role}


class Bluetooth:
    def __init__(self, state, local_receive=False):
        self.state = state
        self.local_receive = local_receive
        self.receive_choices = []
        self.receive_stage = 'idle'
        self.receive_index = 0
        self.station = ''
        self.pending = None
        self.wakeup = lambda: None
        self.width = 60
        self.height = 21
        self.focus = 0
        self.device_offset = 0
        self.hits = []
        self._spans = []

    def bind_wakeup(self, callback):
        self.wakeup = callback

    def modal(self):
        return self.receive_stage != 'idle' or self.pending is not None or bool(self.receive_choices)

    def start_receive(self, action='start'):
        from concurrent.futures import ThreadPoolExecutor
        from peripheral_setup import uv_pro_radios, radio_discovery, receive_profile, save_receive, validate_receive
        from optional_services import start
        if self.pending is not None:
            return True
        profile = None
        if action=='save':
            try:
                profile = validate_receive(dict(address=self.receive_choices[self.receive_index],
                                                callsign=self.station.strip().upper()))
            except ValueError as error:
                self.state.message = str(error)
                return True
        def work():
            if action=='scan':
                return 'pair',radio_discovery('scan')
            if action=='pair':
                address=self.receive_choices[self.receive_index]
                return 'callsign',radio_discovery('pair',address)
            if profile:
                save_receive(profile)
            else:
                radios=uv_pro_radios(paired=True)
                try: saved=receive_profile()
                except FileNotFoundError: saved={}
                if saved.get('address') not in radios:
                    return ('callsign',radios) if radios else ('scan',[])
            start(['receive'])
            return 'idle',[]
        pool = ThreadPoolExecutor(max_workers=1)
        self.state.message = {'scan':'Scanning for UV-PRO…','pair':'Pairing UV-PRO…'}.get(action,'Checking paired radio…')
        self.pending = pool.submit(work)
        def done(future):
            try:
                self.receive_stage,self.receive_choices = future.result()
                self.receive_index = 0
                self.state.message = 'Radio reception requested.' if self.receive_stage=='idle' else ''
            except Exception as error:
                self.state.message = clean(error)
            finally:
                self.pending = None
                pool.shutdown(wait=False)
                self.wakeup()
        self.pending.add_done_callback(done)
        return True

    def key(self, key):
        if self.pending is not None:return True
        if self.receive_stage in ('scan','pair'):
            if key in ('\r','\n'):return self.start_receive(self.receive_stage)
            if key in ('left','right') and self.receive_choices:
                self.receive_index=(self.receive_index+(1 if key=='right' else -1))%len(self.receive_choices)
            if key=='\x1b':
                self.receive_stage='idle';self.receive_choices=[];self.state.message=''
            return True
        if self.receive_choices:
            if key == '\x1b':
                self.receive_choices = []
                self.station = ''
                self.receive_stage='idle'
                self.state.message = ''
            elif key in ('left','right'):
                self.receive_index = (self.receive_index + (1 if key=='right' else -1)) % len(self.receive_choices)
            elif key in ('\r','\n'):
                return self.start_receive('save')
            elif key in ('\x7f','\b','backspace'):
                self.station = self.station[:-1]
            elif len(key)==1 and (key.isascii() and key.isalnum() or key=='-'):
                self.station = (self.station + key.upper())[:9]
            return True
        if self.local_receive and not self.state.read()['online'] and (key=='r' or key in ('\r','\n') and ACTIONS[self.focus]=='receive_start'):
            return self.start_receive()
        if key in ('\t', 'backtab', 'left', 'right'):
            self.focus = (self.focus + (-1 if key in ('backtab', 'left') else 1)) % len(ACTIONS)
        elif key in ('up', 'down', 'pageup', 'pagedown'):
            self.device_offset = max(0, self.device_offset + (-1 if key in ('up', 'pageup') else 1))
        elif key in ('\r', '\n'):
            self.state.request(ACTIONS[self.focus])
        elif key in KEYS:
            action = KEYS[key]
            self.focus = ACTIONS.index(action)
            self.state.request(action)
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
        for x, y, length, key in self.hits:
            if y == row and x <= column < x + length:
                return self.key(key)
        return False

    def lines(self):
        if self.receive_stage in ('scan','pair'):
            selecting=self.receive_stage=='pair'
            self.hits=[];self._spans=[]
            rows=['Pair UV-PRO','On the radio, turn on Pairing in the top menu.']
            if selecting:rows+=['UV-PRO '+self.receive_choices[self.receive_index],'Left/right selects a radio.']
            rows+=['[ Pair selected radio ]' if selecting else '[ Scan for UV-PRO ]']
            self.hits=[(0,len(rows)-1,len(rows[-1]),'\r')]
            return tuple(rows+[self.state.message,'Enter to continue · Esc to cancel'])
        if self.receive_choices:
            self.hits=[]; self._spans=[]
            return ('Start UV-PRO reception', 'Paired UV-PRO: '+self.receive_choices[self.receive_index],
                    'Left/right selects a radio.' if len(self.receive_choices)>1 else '',
                    'Station callsign: '+self.station+'_',self.state.message,
                    'Enter to save and start · Esc to cancel')
        result = self.state.read()
        word = lambda value: 'Unknown' if value is None else 'On' if value else 'Off'
        rows = ['Bluetooth controller: ' + word(result['powered'])]
        self.hits = []
        self._spans = []

        def toolbar(actions):
            labels, hits = toolbar_layout(actions, self.width)
            top = len(rows)
            rows.extend(labels)
            for x, y, length, key in hits:
                self.hits.append((x, top + y, length, key))
                action = KEYS[key]
                role = 'selected' if ACTIONS[self.focus] == action else 'toolbar'
                if not self.state.available(action) and not (self.local_receive and action=='receive_start'):
                    role = 'inset'
                self._spans.append((top + y, x, length, role))

        toolbar((('1', 'On'), ('0', 'Off')))
        rows += ['Off disconnects Bluetooth keyboards too.', '', 'Connected devices']
        devices = result['devices']
        count = min(6, max(1, self.height - 14))
        self.device_offset = min(self.device_offset, max(0, len(devices) - count))
        rows += ['  ' + name for name in devices[self.device_offset:self.device_offset + count]] or [
            '  None' if result['online'] and result['controller_available'] else '  Unavailable']
        intent = 'Unknown' if result['enabled'] is None else 'Enabled' if result['enabled'] else 'Stopped (intent)'
        if result['stopping']:intent='Stopping · stop requested'
        rows += ['', 'UV-Pro reception: ' + intent,
                 'Radio link: ' + ('Unknown' if result['radio_connected'] is None else 'Connected' if result['radio_connected'] else 'Disconnected')]
        reason = result['suspended_reason']
        reason={'controller_unknown':'Bluetooth state unknown','controller_off':'Bluetooth off'}.get(reason,reason.replace('_',' '))
        retries = 'Stopped' if result['enabled'] is False else 'Paused: Bluetooth off' if result['powered'] is False and result['enabled'] is True else 'Paused: ' + reason if reason else 'Managed by receive owner' if result['enabled'] is True else 'Unknown'
        rows.append('Retries: ' + retries)
        toolbar((('r', 'Start'), ('s', 'Stop'), ('d', 'Disconnect UV-Pro')))
        rows.append(self.state.message or clean(self.state.feedback()) or ('Owner connected' if result['online'] else 'Owner controls unavailable'))
        rows = rows[:max(1, self.height - 1)]
        rows += [''] * max(0, self.height - 1 - len(rows))
        rows.append('Tab / Enter: action · arrows: devices')
        return tuple(row[:self.width] for row in rows)

    def spans(self):
        return tuple(span for span in self._spans if span[0] < self.height - 1)
