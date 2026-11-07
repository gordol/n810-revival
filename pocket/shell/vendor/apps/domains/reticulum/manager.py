"""Native framework form for an injected station-owned Reticulum service."""


def display(value):
    if value is None:
        return 'Unknown'
    if type(value) is bool:
        return 'Yes' if value else 'No'
    return ''.join(c if c.isprintable() else ' ' for c in str(value))[:240]


GUIDE = (
    'Radio: the physical RNode and its USB or Bluetooth serial connection.',
    'Interface: Reticulum’s use of that radio with matching LoRa settings.',
    'Identity: a cryptographic public identity, independent of the radio.',
    'Destination: an address for one app on an identity.',
    'Path: how Reticulum reaches a destination across available interfaces.',
    'Link: an encrypted session with an authenticated destination.',
    'Message: app content; delivery needs a response from the peer.',
    'Bluetooth pairing secures the local hop; Reticulum secures the radio link.',
    'The laptop UI can control a radio owned by another station.',
    'The station label always identifies whose radio is being controlled.',
)


class Manager:
    tab_order=(0,2,3,7,8,1,4,5,6)
    tabs = ('Radio', 'Profiles', 'Peers', 'Messages', 'Packets', 'Tools', 'Help', 'Heard', 'Data')

    def __init__(self, host=None, app_context=None):
        self.service = app_context.services.get('reticulum') if app_context else None
        self.width, self.height = 80, 24
        self.tab = self.index = 0
        self.state = {}
        self.error = ''
        self.compose = None
        self.compose_peer = None
        self.sharing = None
        self.discovery_confirmation = False
        self.revoking = None
        self.verification = None
        self.importing = None
        self.notice = ''
        self.editing = None
        self.naming = None
        self.hits = []
        self._spans = []
        self._lists = {}
        self._navigation_actions = ()

    def poll_interval(self):
        return None

    def open(self):
        self.poll()

    def readiness_sources(self):
        if self.service is not None and hasattr(self.service, 'readiness_sources'):
            return self.service.readiness_sources(self.poll_ready)
        if self.service is not None and getattr(self.service, 'readable', None) is not None:
            return ((self.service.readable, self.poll_ready),)
        return ()

    def poll_ready(self):
        self.service.drain()
        self.poll()

    def poll(self):
        if self.service is None:
            return
        try:
            selected_heard = self.selected('heard') if self.tab == 7 else None
            state = self.service.snapshot()
            if not isinstance(state, dict) or state.get('version') != 1:
                raise ValueError('Unsupported Reticulum service snapshot')
            self.state = state
            if selected_heard:
                self.index = next((index for index, row in enumerate(self.rows('heard'))
                                   if row.get('destination') == selected_heard['destination']), 0)
            self.error = ''
        except (OSError, ValueError, TypeError) as error:
            self.error = str(error)

    def rows(self, name):
        value = self.state.get(name, ())
        return value if isinstance(value, (list, tuple)) else ()

    def selected(self, name):
        rows = self.rows(name)
        return rows[self.index % len(rows)] if rows else None

    def request(self, action, **payload):
        if self.service is None:
            self.notice = 'Reticulum service unavailable; no action sent.'
            return False
        if action not in self.state.get('capabilities', ()):
            self.notice = 'Selected owner does not provide ' + action + '.'
            return False
        try:
            request_id = self.service.request(action, payload)
            self.notice = action.replace('_', ' ').capitalize() + ' requested'
            return True
        except (OSError, ValueError, TypeError) as error:
            self.notice = str(error)
            return False

    profile_fields = (('label', 'Name'), ('frequency', 'Frequency (Hz)'),
                      ('bandwidth', 'Bandwidth (Hz)'), ('txpower', 'Power (dBm)'),
                      ('spreadingfactor', 'Spreading factor'), ('codingrate', 'Coding rate denominator (4/N)'))

    def edit_profile(self, profile=None):
        profile = profile or {}
        from app_widgets import TextInput
        self.editing = dict(id=profile.get('id'), index=0,
                            values=[str(profile.get(name, '')) for name, label in self.profile_fields])
        self.editing['inputs']=[TextInput(value,limit=64) for value in self.editing['values']]

    def key(self, key):
        if self.discovery_confirmation:
            if key=='\x1b':self.discovery_confirmation=False
            elif key.lower()=='y':
                if self.request('service_discovery',enabled=True):self.discovery_confirmation=False
            return True
        if self.tab==8 and key=='a' and 'service_discovery' in self.state.get('capabilities',()):
            if self.state.get('data_bridge',{}).get('public_discovery'):self.request('service_discovery',enabled=False)
            else:self.discovery_confirmation=True
            return True
        if self.sharing is not None:
            if key == '\x1b': self.sharing = None
            elif key.lower() == 'y':
                if self.request('service_share', **self.sharing): self.sharing = None
            return True
        if self.revoking is not None:
            if key == '\x1b': self.revoking = None
            elif key.lower() == 'y' and self.request('revoke_peer', peer=self.revoking): self.revoking = None
            return True
        if self.naming is not None:
            form = self.naming
            if key == '\x1b':
                self.naming = None
            elif key in ('\r', '\n'):
                if self.request(form['action'], **dict(form['payload'], **{form.get('field','label'):form['value']})):
                    self.naming = None
            elif key in ('\x7f', '\b'):
                form['value'] = form['value'][:-1]
            elif key == '\x15':
                form['value'] = ''
            elif len(key) == 1 and key.isprintable() and len(form['value']) < 64:
                form['value'] += key
            return True
        if self.editing is not None:
            form = self.editing
            index = form['index']
            if key == '\x1b':
                self.editing = None
            elif key in ('\t', 'down', 'backtab', 'up'):
                form['index'] = (index + (-1 if key in ('backtab', 'up') else 1)) % len(self.profile_fields)
            elif key == '\x15':
                form['inputs'][index].text='';form['inputs'][index].cursor=0
                form['values'][index]=''
            elif key in ('\r', '\n'):
                if index < len(self.profile_fields) - 1:
                    form['index'] += 1
                else:
                    try:
                        profile = {name: value if name == 'label' else int(value)
                                   for (name, label), value in zip(self.profile_fields, form['values'])}
                        if form['id']:
                            profile['id'] = form['id']
                        if self.request('save_profile', profile=profile):
                            self.editing = None
                    except ValueError:
                        self.notice = 'Enter whole numbers in the numeric fields.'
            else:
                editor=form['inputs'][index]
                editor.key(key)
                form['values'][index]=editor.text
            return True
        if self.importing is not None:
            if key == '\x1b':
                self.importing = None
            elif key in ('\r', '\n'):
                self.request('import_peer', card=self.importing)
                self.importing = None
            elif key in ('\x7f', '\b'):
                self.importing = self.importing[:-1]
            elif key.isprintable() and len((self.importing + key).encode()) <= 2048:
                self.importing += key
            return True
        if self.verification is not None:
            if key == '\x1b':
                self.verification = None
            elif key.lower() == 'y':
                peer, digest = self.verification
                self.request('verify_peer', peer=peer, fingerprint=digest)
                self.verification = None
            return True
        if self.compose is not None:
            if key == '\x1b':
                self.compose = None
            elif key == '\x13':
                if self.compose_peer and self.compose and self.request('send', peer=self.compose_peer, text=self.compose):
                    self.compose = None
                    self.compose_peer = None
            elif key in ('\x7f', '\b'):
                self.compose = self.compose[:-1]
            elif len(key) == 1 and key.isprintable() and len((self.compose + key).encode()) <= 240:
                self.compose += key
            return True
        if key in ('\t', 'backtab', 'left', 'right'):
            order = self.tab_order
            self.tab = order[(order.index(self.tab) + (-1 if key in ('backtab', 'left') else 1)) % len(order)]
            self.index = 0
        elif key in ('up', 'down', 'j', 'k', 'home', 'end', 'pageup', 'pagedown'):
            from app_widgets import SelectList
            name = {0:'radios', 1:'profiles', 2:'peers', 3:'messages', 4:'packets', 7:'heard', 8:'peers'}.get(self.tab)
            if name:
                listing = self._lists.setdefault(name, SelectList(()))
                listing.rows = tuple(str(i) for i in range(len(self.rows(name))))
                listing.index = self.index
                listing.key(key)
                self.index = listing.index
        elif key == 'f5' or key == 'r' and self.tab != 8:
            self.poll()
        elif self.tab == 8 and key in ('c', 'w', 'u', 'r', 'd', 'g'):
            bridge = self.state.get('data_bridge') or {}
            peer = self.selected('peers')
            if peer and peer.get('pinned') and key in ('c','w','g') and 'service_share' in self.state.get('capabilities', ()):
                self.sharing = dict(peer=peer['identity'],expected_public_key=peer['public_key'],service='device' if key=='g' else 'reticulum',
                                    operations=['snapshot','subscribe'] + (['send'] if key == 'w' else []))
            elif peer and peer.get('pinned') and key == 'u' and hasattr(self.service,'connect'):
                connections=getattr(getattr(self.service,'registry',None),'providers',{}).get('connections')
                if connections is not None:
                    connections.connect('peer',peer['identity']);self.notice='Connecting device; see Connections for service status.'
                else:self.service.connect('peer',peer['identity'])
            elif peer and peer.get('pinned') and key in ('c', 'r'):
                self.request('data_bridge_connect' if key == 'c' else 'data_bridge_request', peer=peer['identity'], expected_public_key=peer['public_key'], service='pocket.data.v1', capabilities=['status'])
            elif key == 'd' and peer:
                self.request('data_bridge_disconnect', peer=peer['identity'])
        elif self.tab==0 and key in ('a','o','x','b','v'):
            if key=='b' and 'configure_node' in self.state.get('capabilities',()):
                self.naming=dict(action='configure_node',payload={},field='endpoint',value=(self.state.get('external_node') or {}).get('endpoint',''))
            elif key=='v':self.request('refresh_node')
            elif key in ('a','o','x'):self.request('configure_node',mode={'a':'auto','o':'disabled','x':'external-only'}[key])
        elif self.tab == 0 and key in ('c', 'd', 'p'):
            radio = self.selected('radios')
            if radio:
                self.request({'c': 'connect', 'd': 'disconnect', 'p': 'pair'}[key],
                             station=radio['station_id'], radio=radio['radio_id'])
        elif self.tab == 1:
            profile = self.selected('profiles')
            if key == 'n' and 'save_profile' in self.state.get('capabilities', ()):
                self.edit_profile()
            elif key == 'e' and profile and 'save_profile' in self.state.get('capabilities', ()):
                self.edit_profile(profile)
            elif key in ('\r', '\n') and profile:
                self.request('select_profile', profile=profile['id'])
            elif key == 'x' and profile:
                self.request('delete_profile', profile=profile['id'])
        elif self.tab == 7 and key in ('s', 'n', 'm'):
            heard = self.selected('heard')
            if not heard:
                self.notice = 'No heard destination selected.'
            elif key == 'm':
                if heard.get('service') == 'lxmf.delivery' and heard.get('saved') and heard.get('peer_verified'):
                    self.compose, self.compose_peer = '', heard['identity']
                else:
                    self.notice = 'Save and verify an LXMF delivery peer before writing a message.'
            elif heard.get('saved'):
                self.naming = dict(action='rename_peer', payload=dict(peer=heard['identity']),
                                   value=heard.get('local_name') or '')
            else:
                self.naming = dict(action='save_heard', payload=dict(destination=heard['destination']),
                                   value=heard.get('advertised_name') or heard['identity'][:12])
        elif self.tab == 2 and key == 'n':
            peer = self.selected('peers')
            if peer:
                self.naming = dict(action='rename_peer', payload=dict(peer=peer['identity']), value=peer.get('label') or '')
        elif self.tab == 2 and key == 'm':
            peer = self.selected('peers')
            if peer and peer.get('pinned') is True:
                self.compose = ''
                self.compose_peer = peer['identity']
            else:
                self.notice = 'Select a peer whose identity has been verified first.'
        elif self.tab == 2 and key == 'x':
            peer = self.selected('peers')
            if peer: self.revoking = peer['identity']
        elif self.tab == 2 and key == 'v':
            if __package__:
                from .contacts import fingerprint, public_key
            else:
                from contacts import fingerprint, public_key
            peer = self.selected('peers')
            if peer:
                try:
                    key_bytes = public_key(peer.get('public_key'))
                    import hashlib
                    if hashlib.sha256(key_bytes).digest()[:16].hex() != peer['identity']:
                        raise ValueError('Peer identity does not match the supplied key')
                    self.verification = (peer['identity'], fingerprint(key_bytes))
                except ValueError as error:
                    self.notice = str(error)
        elif self.tab == 2 and key == 'i':
            self.importing = ''
        elif self.tab == 2 and key == 'a':
            self.notice='Use Messages → Reticulum → Discovery to publish messaging presence explicitly.'
        else:
            return False
        return True

    def navigation_targets(self):
        from native_navigation import Target
        name=self.navigation_list_name()
        content=Target('content',name.capitalize() if name else 'Information','list' if name else 'details')
        return [Target('tabs','Tabs','tabs'),content]+[Target('action:'+key,label,'action',key) for key,label in self._navigation_actions]

    def navigation_list_name(self):
        return {0:'radios',1:'profiles',2:'peers',3:'messages',4:'packets',7:'heard',8:'peers'}.get(self.tab)

    def navigation_list(self,key):
        name=self.navigation_list_name()
        if key!='content' or name is None:return None,None
        from app_widgets import SelectList
        widget=self._lists.setdefault(name,SelectList(()))
        values=self.rows(name)
        # Drawing normally supplies the formatted labels. Keep focus usable
        # before the first draw and when a source revision changes its length.
        if len(widget.rows)!=len(values):
            widget.rows=tuple(display(row.get('label') or row.get('identity') or row.get('id') or row.get('radio_id') or index)
                              for index,row in enumerate(values))
        widget.index=min(self.index,max(0,len(values)-1))
        return widget,lambda:setattr(self,'index',widget.index)

    def navigation_action_spans(self,key):
        return tuple((y,left,right-left,'input') for y,left,right,action,value in self.hits if action=='key' and value==key)

    def navigation_modal_hint(self):
        if self.compose is not None:return ('Message','Ctrl-S sends · Enter keeps draft · Esc cancel')
        if self.editing is not None:return ('Profile','Tab field · Enter next/save · Esc cancel')
        if self.naming is not None or self.importing is not None:return ('Input','Enter save · Esc cancel')
        return ('Confirm','Y confirm · Esc cancel')

    def modal(self):
        return self.discovery_confirmation or any(value is not None for value in (self.sharing, self.revoking, self.naming, self.importing, self.verification, self.editing, self.compose))

    def pointer(self, column, row, width, button=0, released=False):
        if released or button & 32:
            return False
        if button & 64:
            return self.key('down' if button & 1 else 'up')
        if button != 0:
            return False
        self.width = width
        self.lines()
        for y, left, right, action, value in self.hits:
            if y == row and left <= column < right:
                if action == 'tab':
                    self.tab, self.index, self.notice = value, 0, ''
                elif action == 'select':
                    self.index = value
                elif action == 'field':
                    self.editing['index'] = value
                else:
                    self.key(value)
                return True
        return False

    def spans(self):
        return tuple(self._spans)

    def lines(self):
        if self.discovery_confirmation:
            from textwrap import wrap
            rows=[part for line in ('Publish service presence?', 'Reachable Reticulum nodes can discover this bridge identity. Service access still requires permission.') for part in wrap(line,self.width)][:self.height-2]
            row=len(rows);rows.append('[Y Publish] [Esc Cancel]')
            self.hits=[(row,0,11,'key','y'),(row,12,24,'key','\x1b')]
            self._spans=[(row,0,24,'control')]
            return rows
        from app_widgets import Canvas, SelectList
        self.hits = []
        self._spans = []
        self._navigation_actions = []
        rows = []
        width = max(20, self.width)
        height = max(8, self.height)
        def text(value):
            rows.append(display(value)[:width])
        def buttons(items):
            line = ''
            for label, action, value in items:
                if action=='key' and value not in [key for key,_ in self._navigation_actions]:self._navigation_actions.append((value,label))
                label = '[' + label + ']'
                if line and len(line) + len(label) + 1 > width:
                    rows.append(line); line = ''
                left = len(line)
                line += label + ' '
                self.hits.append((len(rows), left, left + len(label), action, value))
                self._spans.append((len(rows), left, len(label), 'selected' if action == 'tab' and value == self.tab else 'control'))
            if line: rows.append(line.rstrip())
        def commands(items):
            buttons([(label, 'key', key) for capability, label, key in items
                     if capability is None or capability in self.state.get('capabilities', ())])
        def listing(name, format_row, reserve=3):
            values = self.rows(name)
            count = max(1, height - len(rows) - reserve)
            widget = self._lists.setdefault(name, SelectList(()))
            widget.replace(tuple(format_row(value) for value in values),
                           tuple(value.get('identity') or value.get('destination') or value.get('id') or str(i) for i, value in enumerate(values)))
            widget.index = min(self.index, max(0, len(values)-1))
            widget.reveal()
            canvas = Canvas(width, count + 1)
            widget.draw(canvas, 0, 1, width, count)
            top = len(rows)
            rows.extend(canvas.lines())
            self._spans.extend((top+y, x, n, role) for y, x, n, role in canvas.spans)
            for i in range(widget.offset, min(len(values), widget.offset + count)):
                self.hits.append((top + 1 + i - widget.offset, 0, width, 'select', i))
            return self.selected(name)
        if self.modal():
            if self.sharing is not None:
                text('Share device read access' if self.sharing['service']=='device' else 'Share Reticulum service')
                text(self.sharing['peer'])
                text('Read system telemetry and retained radio receptions.' if self.sharing['service']=='device' else 'Read contacts, messages and live events.')
                if 'send' in self.sharing['operations']: text('Also allow sending through this owner.')
                commands([('service_share', 'Grant Y', 'y'), (None, 'Cancel Esc', '\x1b')])
            elif self.revoking is not None:
                text('Revoke peer trust?')
                text(self.revoking)
                text('This key cannot be verified again.')
                commands([('revoke_peer', 'Revoke Y', 'y'), (None, 'Cancel Esc', '\x1b')])
            elif self.compose is not None:
                text('Message to ' + str(self.compose_peer))
                commands([('send', 'Send Ctrl-S', '\x13'), (None, 'Cancel Esc', '\x1b')])
                text(self.compose or 'Type your message')
                text(str(len(self.compose.encode())) + '/240 bytes')
            elif self.naming is not None:
                text('External node: /dev/serial-device or rfcomm://MAC/1' if self.naming.get('field')=='endpoint' else 'Local nickname')
                commands([(None, 'Save Enter', '\r'), (None, 'Cancel Esc', '\x1b')])
                text(self.naming['value'])
            elif self.importing is not None:
                text('Import public contact card')
                commands([('import_peer', 'Import Enter', '\r'), (None, 'Cancel Esc', '\x1b')])
                text(self.importing or 'Paste the public contact card here')
            elif self.verification is not None:
                peer, digest = self.verification
                text('Compare the full fingerprint with your peer')
                commands([('verify_peer', 'Matches Y', 'y'), (None, 'Cancel Esc', '\x1b')])
                for offset in range(0, len(digest), width): text(digest[offset:offset+width])
                text('Confirm only after comparison through a trusted channel.')
            elif self.editing is not None:
                text('Edit profile' if self.editing['id'] else 'New profile')
                commands([(None, 'Next / Save Enter', '\r'), (None, 'Cancel Esc', '\x1b')])
                for i, ((name, label), value) in enumerate(zip(self.profile_fields, self.editing['values'])):
                    prefix=('> ' if i == self.editing['index'] else '  ')+label+': '
                    editor=self.editing['inputs'][i]
                    shown,spans=editor.presentation(max(0,width-len(prefix)),focused=i==self.editing['index'])
                    text(prefix+shown)
                    self._spans.extend((len(rows)-1,len(prefix)+x,n,role) for x,n,role in spans)
                    self.hits.append((len(rows)-1, 0, width, 'field', i))
            if self.notice: text(self.notice)
            return rows[:height]
        # Display order puts operating tasks first; stable indices retain key semantics.
        buttons([(('*' if i == self.tab else '') + self.tabs[i], 'tab', i) for i in (0, 2, 3, 7, 8, 1, 4, 5, 6)])
        phase = self.state.get('radio_state', 'unavailable')
        text(str(self.state.get('station_id') or 'Local station') + (' | Carriers ' if self.state.get('carriers') else ' | Radio ') + str(phase))
        if self.tab == 0:
            commands([('connect', 'Connect C', 'c'), ('disconnect', 'Disconnect D', 'd'), ('pair', 'Pair P', 'p')])
            buttons(([('Profiles', 'tab', 1)] if not self.state.get('carriers') else []) + [('Peers', 'tab', 2)])
            profile = self.state.get('selected_profile') or {}
            radio = self.selected('radios') or {}
            if self.state.get('carriers'):
                text('Carriers: ' + ', '.join(c['type'] for c in self.state['carriers']))
                text('Services: encrypted; peer verification required')
                text('Connections: detach to stop an owner started by this shell')
            else:
                text('Profile: ' + str(profile.get('label') or 'Choose or create a profile'))
            text('Device: ' + str(radio.get('radio_id') or 'Not configured') + ' / ' + str(radio.get('connection') or ''))
            text(('Carrier: ' if self.state.get('carriers') else 'Serial: ') + display(radio.get('connected')) + ' | Interface: ' + display(radio.get('interface_online')))
            node=self.state.get('external_node')
            if node is not None:
                text('Offload: '+str(node.get('mode'))+' | '+('Switching…' if node.get('switching') else 'Active: '+str(node.get('selected'))))
                commands([('configure_node','Auto A','a'),('configure_node','Disabled O','o'),('configure_node','External only X','x'),('configure_node','Board B','b'),('refresh_node','Refresh V','v')])
                age=node.get('sample_age')
                text('Board: '+str(node.get('state'))+(' | '+str(int(age))+'s ago' if age is not None else ''))
                if node.get('identity'):text('Node: '+node['identity'])
                settings=node.get('radio') or {}
                if settings.get('frequency'):text(str(settings['frequency'])+' Hz | '+str(settings.get('txpower'))+' dBm | SF '+str(settings.get('spreadingfactor')))
                if node.get('reason') or node.get('error'):text(node.get('reason') or node.get('error'))
            if profile:
                text(str(profile.get('frequency')) + ' Hz | ' + str(profile.get('bandwidth')) + ' Hz BW')
                text(str(profile.get('txpower')) + ' dBm | SF ' + str(profile.get('spreadingfactor')) + ' | CR 4/' + str(profile.get('codingrate')))
            if phase == 'opening': text('Connecting… Disconnect cancels.')
            elif phase == 'closing': text('Disconnecting… Wait for idle before reconnecting.')
        elif self.tab == 1:
            commands([('save_profile', 'New N', 'n'), ('save_profile', 'Edit E', 'e'), ('select_profile', 'Select Enter', '\r'), ('delete_profile', 'Delete X', 'x')])
            if not self.rows('profiles'): text('No profiles. Choose New to enter radio settings.')
            listing('profiles', lambda p: str(p.get('label')) + (' (active)' if p.get('selected') else ''))
        elif self.tab in (2, 8):
            if self.tab == 2:
                commands([('import_peer', 'Import I', 'i'), ('verify_peer', 'Verify V', 'v'), ('rename_peer', 'Rename N', 'n'), ('send', 'Message M', 'm'), ('revoke_peer', 'Revoke X', 'x')])
            else:
                commands([('service_discovery', 'Discovery A', 'a'), ('service_share', 'Device read G', 'g'), ('service_share', 'Owner read C', 'c'), ('service_share', 'Allow send W', 'w'), (None, 'Use peer U', 'u'), ('data_bridge_disconnect', 'Revoke D', 'd')])
                bridge = self.state.get('data_bridge') or {}
                peer = self.selected('peers') or {}
                shared = peer.get('identity') in bridge.get('grants', ())
                grant = next((g for g in bridge.get('service_grants', ()) if g['peer']==peer.get('identity') and g['service']=='reticulum'), {})
                text('Granted: ' + ', '.join(grant.get('operations', ())) if grant else 'No service grant to selected peer')
                text('Use peer opens its service in this app through your local RNS owner.')
                result = next((r for r in bridge.get('requests', ()) if r['peer'] == peer.get('identity')), {})
                if result.get('pending'): text('Requesting status…')
                if result.get('error'): text(result['error'])
                remote = result.get('response') or {}
                if remote:
                    text('Peer service: ' + display(remote.get('service_online')) + ' | Interface: ' + display(remote.get('interface_online')))
                    text('Observed: ' + display(remote.get('observed_at')))
                if 'data_bridge_connect' not in self.state.get('capabilities', ()) and not bridge:
                    text('Connect the radio to use peer data services.')
            if not self.rows('peers'): text('No contacts. Open Peers and import a public card.')
            peer = listing('peers', lambda p: str(p.get('label') or p.get('identity')) + (' (verified)' if p.get('pinned') else ' (unverified)'))
            if peer: text('Identity: ' + str(peer.get('identity')))
        elif self.tab == 7:
            commands([('save_heard', 'Save / Rename N', 'n'), ('send', 'Message M', 'm')])
            if not self.rows('heard'): text('No announcements received. Connect to listen.')
            listing('heard', lambda p: str(p.get('local_name') or p.get('advertised_name') or p.get('identity')) + ' / ' + str(p.get('service')))
        elif self.tab in (3, 4):
            name = 'messages' if self.tab == 3 else 'packets'
            buttons([('Write to peer', 'tab', 2)])
            if not self.rows(name): text('No ' + name + ' recorded.')
            record = listing(name, lambda p: ' / '.join(display(p.get(k)) for k in (('direction', 'state', 'peer') if name == 'messages' else ('direction', 'kind', 'bytes'))), reserve=4)
            if record and name == 'messages':
                content = display(record.get('text'))
                for offset in range(0, len(content), width): text(content[offset:offset+width])
        elif self.tab == 5:
            text('Radio diagnostics')
            radio = self.selected('radios') or {}
            text('Received: ' + display(radio.get('rx_bytes')) + ' bytes')
            text('Sent: ' + display(radio.get('tx_bytes')) + ' bytes')
            text('Port: ' + display(radio.get('port')))
            commands([(None, 'Refresh F5', 'f5')])
        else:
            text('Connect: Radio → select profile → Connect.')
            text('Message: Peers → import → verify → Message.')
            text('Data: share read access or allow send with a verified peer.')
            text('Use peer attaches this app to that peer’s service over Reticulum.')
            text('Disconnect removes your grant and cancels that peer request.')
            text('Click bracketed controls or use the printed key.')
            text('Tab moves focus; [ ] changes page; ? opens the manual.')
        error = self.error or self.state.get('error') or (self.state.get('message_error') or {}).get('error')
        job = self.state.get('last_job') or {}
        status = error or job.get('error') or self.notice
        if not status and job.get('state') == 'running': status = str(job.get('action')) + ' in progress…'
        if status:
            rows = rows[:height-1]
            text(status)
        self.hits = [hit for hit in self.hits if hit[0] < min(height, len(rows))]
        return rows[:height]

    def close(self):
        pass


def descriptor():
    return dict(id='reticulum', title='Reticulum', preferred_size=(88, 26), minimum_size=(40, 12),
                description='Connect a radio, message peers and share status',
                category='Radio', factory=Manager, uses=(dict(id='reticulum', required=False),),
                help=(('Reticulum', GUIDE),))
