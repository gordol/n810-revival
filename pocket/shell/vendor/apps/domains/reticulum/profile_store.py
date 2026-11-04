"""Private named radio profiles; persistence never activates a radio."""
from discovery_codec import unpack,legacy_value,atomic_write as atomic_state
import os
from pathlib import Path
import stat

from endpoints import Endpoint, token, saved_endpoint


FIELDS = ('frequency', 'bandwidth', 'txpower', 'spreadingfactor', 'codingrate')




class ProfileStore:
    def __init__(self, state, station, radio, connection, port, minimum, maximum, seed=None):
        self.endpoint = saved_endpoint(state, Endpoint(station, radio, connection, port))
        if type(minimum) is not int or type(maximum) is not int or not 0 <= minimum <= maximum <= 37:
            raise ValueError('Explicit supported hardware power limits are required')
        self.minimum, self.maximum = minimum, maximum
        self.path = Path(state) / 'radio-profiles.msgpack'
        self.profiles, self.selected = {}, None
        source=self.path if self.path.exists() or self.path.is_symlink() else self.path.with_suffix('.json')
        if source.exists() or source.is_symlink():
            info = source.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 65536:
                raise ValueError('Unsafe profile store')
            raw=source.read_bytes()
            value=unpack(raw) if source==self.path else legacy_value(raw)
            if value.get('version') != 1 or not isinstance(value.get('profiles'), list) or len(value['profiles']) > 32:
                raise ValueError('Unsupported profile store')
            for profile in value['profiles']:
                checked = self.validate(profile)
                if checked['id'] in self.profiles:
                    raise ValueError('Duplicate profile identity')
                self.profiles[checked['id']] = checked
            self.selected = value.get('selected')
            if self.selected is not None and self.selected not in self.profiles:
                raise ValueError('Selected profile is missing')
            if source!=self.path:self.commit(self.profiles,self.selected)
        elif seed:
            raw=Path(seed).read_bytes()
            profile=self.validate(unpack(raw) if Path(seed).suffix=='.msgpack' else legacy_value(raw))
            self.commit({profile['id']: profile}, profile['id'])

    def validate(self, profile):
        if not isinstance(profile, dict) or set(profile) - set(('id', 'label') + FIELDS):
            raise ValueError('Unsupported radio profile fields')
        result = dict(profile)
        result['id'] = token(result.get('id') or os.urandom(16).hex(), 'profile identity')
        label = result.get('label')
        if not isinstance(label, str) or not 1 <= len(label) <= 64 or not label.strip() or not all(c.isprintable() for c in label):
            raise ValueError('Profile name must contain 1–64 printable characters')
        ranges = dict(frequency=(850000000, 950000000), bandwidth=(7800, 500000),
                      txpower=(self.minimum, self.maximum), spreadingfactor=(7, 12), codingrate=(5, 8))
        for field, (low, high) in ranges.items():
            if type(result.get(field)) is not int or not low <= result[field] <= high:
                raise ValueError('Unsupported ' + field + ': expected ' + str(low) + '–' + str(high))
        if result['bandwidth'] not in (7800, 10400, 15600, 20800, 31250, 41700, 62500, 125000, 250000, 500000):
            raise ValueError('Unsupported LoRa bandwidth')
        return result

    def commit(self, profiles, selected):
        atomic_state(self.path, dict(version=1, selected=selected, profiles=list(profiles.values())))
        self.profiles, self.selected = profiles, selected

    def dispatch(self, action, payload):
        if action == 'save_profile' and set(payload) == {'profile'}:
            profile = self.validate(payload['profile'])
            if profile['id'] not in self.profiles and len(self.profiles) >= 32:
                raise ValueError('Profile limit reached')
            profiles = dict(self.profiles)
            profiles[profile['id']] = profile
            self.commit(profiles, self.selected)
            return profile['id']
        if action in ('select_profile', 'delete_profile') and set(payload) == {'profile'}:
            identity = payload['profile']
            if identity not in self.profiles:
                raise ValueError('Unknown profile')
            profiles, selected = dict(self.profiles), self.selected
            if action == 'select_profile':
                selected = identity
            else:
                del profiles[identity]
                if selected == identity:
                    selected = None
            self.commit(profiles, selected)
            return identity
        raise ValueError('Invalid profile request')

    def configuration(self, resolved_port=None):
        if self.selected not in self.profiles:
            raise ValueError('Select a saved profile before connecting')
        port = self.endpoint.port
        if self.endpoint.connection == 'hub':
            if resolved_port is None:
                raise ValueError('Resolve the configured hub before connecting')
            port = Endpoint(self.endpoint.station, self.endpoint.radio, 'usb', resolved_port).port
        elif resolved_port is not None:
            raise ValueError('Only a hub uses a resolved local endpoint')
        profile = self.profiles[self.selected]
        return '''[reticulum]
enable_transport = No
share_instance = No
discover_interfaces = No
autoconnect_discovered_interfaces = 0
enable_remote_management = No
enable_interface_management = No
respond_to_probes = No
[logging]
loglevel = 3
[interfaces]
  [[Selected RNode]]
    type = RNodeInterface
    enabled = Yes
    port = {port}
    frequency = {frequency}
    bandwidth = {bandwidth}
    txpower = {txpower}
    spreadingfactor = {spreadingfactor}
    codingrate = {codingrate}
{flow_control}'''.format(port=port, flow_control='    flow_control = True\n' if self.endpoint.connection == 'hub' else '', **profile)
