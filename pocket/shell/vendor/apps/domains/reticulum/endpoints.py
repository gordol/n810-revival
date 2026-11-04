"""Station-specific RNode selection and explicit single-radio configurations."""
from collections import namedtuple
import re
from discovery_codec import unpack,legacy_value,atomic_write
import os
from pathlib import Path
import stat


def token(value, field):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}', value):
        raise ValueError('Invalid ' + field)
    return value


def saved_endpoint(state, endpoint):
    target=Path(state)/'radio-device.msgpack'
    path=target if target.exists() or target.is_symlink() else target.with_suffix('.json')
    if not path.exists() and not path.is_symlink():
        return endpoint
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 1024:
        raise ValueError('Unsafe saved radio device')
    raw=path.read_bytes()
    value=unpack(raw) if path==target else legacy_value(raw)
    if set(value) != {'version', 'station', 'radio', 'connection', 'port'} or value['version'] != 1:
        raise ValueError('Invalid saved radio device')
    if (value['station'], value['radio']) != (endpoint.station, endpoint.radio):
        raise ValueError('Saved radio belongs to a different station or radio')
    result=Endpoint(value['station'],value['radio'],value['connection'],value['port'])
    if path!=target:atomic_write(target,value)
    return result


class Endpoint(namedtuple('EndpointFields','station radio connection port')):
    __slots__=()
    station: str
    radio: str
    connection: str
    port: str

    def __new__(cls,station,radio,connection,port):
        self=super().__new__(cls,station,radio,connection,port)
        self._validate()
        return self

    def _validate(self):
        token(self.station, 'station identity')
        token(self.radio, 'radio identity')
        if self.connection not in ('usb', 'bluetooth', 'ble', 'hub'):
            raise ValueError('Select USB, Bluetooth serial, BLE or a configured hub')
        if self.connection == 'hub':
            if not isinstance(self.port, str) or not re.fullmatch(r'hub://[0-9a-f]{24}/3', self.port):
                raise ValueError('Select a configured hub LoRa service')
        elif self.connection == 'ble':
            if not isinstance(self.port, str) or not re.fullmatch(r'ble://[A-Za-z0-9 _.:-]{1,80}', self.port) or not self.port[6:].strip():
                raise ValueError('Select an explicit BLE device name or identifier')
        elif not isinstance(self.port, str) or not re.fullmatch(r'/dev/(?:[A-Za-z0-9._-]{1,120}|pts/[0-9]{1,10})', self.port):
            raise ValueError('Select an explicit device serial port on the owning station')

    def for_station(self, station):
        if station != self.station:
            raise ValueError('Radio belongs to ' + self.station + '; use that station’s owner service')
        return self.port

    def view(self, ui_station):
        return dict(station_id=self.station, radio_id=self.radio,
                    connection=self.connection, port=self.port,
                    location='local' if self.station == ui_station else 'remote',
                    label=self.station + ' / ' + self.radio + ' / ' + self.connection)


class RadioSettings(namedtuple('RadioSettingsFields','frequency bandwidth txpower spreadingfactor codingrate')):
    __slots__=()
    frequency: int
    bandwidth: int
    txpower: int
    spreadingfactor: int
    codingrate: int

    def __new__(cls,frequency,bandwidth,txpower,spreadingfactor,codingrate):
        self=super().__new__(cls,frequency,bandwidth,txpower,spreadingfactor,codingrate)
        self._validate()
        return self

    def _validate(self):
        ranges = dict(frequency=(850000000, 950000000), bandwidth=(7800, 500000),
                      txpower=(2, 17), spreadingfactor=(7, 12), codingrate=(5, 8))
        for field, (low, high) in ranges.items():
            value = getattr(self, field)
            if type(value) is not int or not low <= value <= high:
                raise ValueError('Unsupported 915 MHz RNode ' + field)
        if self.bandwidth not in (7800, 10400, 15600, 20800, 31250, 41700, 62500, 125000, 250000, 500000):
            raise ValueError('Unsupported LoRa bandwidth')


def radio_config(endpoint, settings, station):
    """Render only; starting Reticulum with this configuration enables the radio."""
    if endpoint.connection == 'hub':
        raise ValueError('Resolve the hub attachment before configuring its radio')
    port = endpoint.for_station(station)
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
    frequency = {s.frequency}
    bandwidth = {s.bandwidth}
    txpower = {s.txpower}
    spreadingfactor = {s.spreadingfactor}
    codingrate = {s.codingrate}
'''.format(port=port, s=settings)


def status(endpoint, ui_station, *, bonded=None, connected=None, interface_online=None,
           peer_authenticated=None, last_delivery=None):
    """Keep independent observations independent; unknown is not success."""
    result = endpoint.view(ui_station)
    result.update(bonded=bonded, connected=connected, interface_online=interface_online,
                  peer_authenticated=peer_authenticated, last_delivery=last_delivery)
    return result
