"""Bounded validated-announce observations, separate from saved contact trust."""
import hashlib
import math
import tempfile
from pathlib import Path
import stat
import os
import threading
import time

from discovery_codec import pack, unpack
from endpoints import token


SERVICES = ('pocket.data.v1', 'lxmf.delivery', 'lxmf.propagation', 'nomadnetwork.node')


def name_text(value):
    if not isinstance(value, str):
        return None
    return ''.join(c for c in value if c.isprintable())[:64] or None


def bounded_snapshot(state, limit):
    for field in ('heard','packets','messages'):
        while state.get(field) and encoded_size(state)>limit:
            state[field].pop(0 if field in ('messages','packets') else -1)
    return state


class HeardStore:
    def __init__(self, directory):
        self.path = Path(directory) / 'heard.msgpack'
        self.records = {}
        if self.path.exists() or self.path.is_symlink():
            info = self.path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 131072:
                raise ValueError('Unsafe Heard observations')
            value = unpack(self.path.read_bytes())
            if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('records'), list) or len(value['records']) > 64:
                raise ValueError('Unsupported Heard observations')
            for record in value['records']:
                if not isinstance(record, dict):
                    raise ValueError('Invalid Heard observation')
                for field in ('destination', 'identity', 'public_key', 'announce_hash'):
                    if record.get(field) is not None:
                        if not isinstance(record[field], bytes):
                            raise ValueError('Discovery addresses must use binary encoding')
                        record[field] = record[field].hex()
                self.check(record)
                self.records[record['destination']] = record

    @staticmethod
    def check(record):
        if not isinstance(record, dict) or set(record) != {'destination', 'identity', 'public_key', 'service', 'advertised_name', 'last_heard', 'observation', 'announce_hash', 'path_known_at_observation', 'hops_at_observation', 'path_interface_at_observation', 'station_id', 'radio_id'}:
            raise ValueError('Invalid Heard observation')
        for field, length in (('destination', 16), ('identity', 16), ('public_key', 64)):
            value = record.get(field)
            if not isinstance(value, str) or len(value) != length * 2 or len(bytes.fromhex(value)) != length:
                raise ValueError('Invalid Heard address or public key')
        if hashlib.sha256(bytes.fromhex(record['public_key'])).digest()[:16].hex() != record['identity']:
            raise ValueError('Heard identity does not match its public key')
        for field in ('advertised_name', 'path_interface_at_observation'):
            if record.get(field) is not None and name_text(record[field]) != record[field]:
                raise ValueError('Invalid Heard display name')
        for field in ('station_id', 'radio_id'):
            token(record.get(field), 'Heard ' + field)
        if record.get('observation') not in ('announce', 'path_response') or type(record.get('path_known_at_observation')) is not bool:
            raise ValueError('Invalid Heard observation metadata')
        if record.get('hops_at_observation') is not None and (type(record['hops_at_observation']) is not int or not 0 <= record['hops_at_observation'] <= 256):
            raise ValueError('Invalid observed hop count')
        digest = record.get('announce_hash')
        if digest is not None and (not isinstance(digest, str) or len(digest) != 64 or len(bytes.fromhex(digest)) != 32):
            raise ValueError('Invalid announce hash')
        if record.get('service') not in SERVICES + ('unknown',):
            raise ValueError('Unknown Heard service classification')
        if type(record.get('last_heard')) not in (int, float) or not math.isfinite(record['last_heard']) or not 0 <= record['last_heard'] < 1e12:
            raise ValueError('Invalid Heard timestamp')

    def observe(self, records):
        staged = dict(self.records)
        for record in records:
            self.check(record)
            staged[record['destination']] = record
        recent = sorted(staged.values(), key=lambda row: row['last_heard'], reverse=True)[:64]
        encoded = []
        for record in recent:
            row = dict(record)
            for field in ('destination', 'identity', 'public_key', 'announce_hash'):
                if row[field] is not None:
                    row[field] = bytes.fromhex(row[field])
            encoded.append(row)
        data = pack(dict(version=1, records=encoded))
        if len(data) > 131072:
            raise ValueError('Heard observations exceed storage limit')
        fd, temporary = tempfile.mkstemp(prefix='.heard-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.records = {row['destination']: row for row in recent}

    def rows(self, contacts):
        rows = []
        for record in sorted(self.records.values(), key=lambda row: row['last_heard'], reverse=True):
            contact = contacts.get(record['identity'])
            rows.append(dict(record, saved=contact is not None,
                             local_name=contact['card']['label'] if contact else None,
                             peer_verified=bool(contact and contact['state'] == 'verified')))
        return rows


class AnnounceObserver:
    aspect_filter = None
    receive_path_responses = True

    def __init__(self, owner):
        self.owner = owner
        self.pending = {}
        self.lock = threading.Lock()
        self.notified = False

    def received_announce(self, destination_hash, announced_identity, app_data,
                         announce_packet_hash=None, is_path_response=False):
        if announced_identity is None or not isinstance(destination_hash, bytes) or len(destination_hash) != 16:
            return
        rns, lxmf = self.owner.RNS, self.owner.LXMF
        public = announced_identity.get_public_key()
        if not isinstance(public, bytes) or len(public) != 64:
            return
        service = next((name for name in SERVICES if
                        rns.Destination.hash_from_name_and_identity(name, announced_identity) == destination_hash), 'unknown')
        advertised = None
        if isinstance(app_data, bytes) and len(app_data) <= 1024:
            try:
                if service == 'lxmf.delivery':
                    advertised = lxmf.display_name_from_app_data(app_data)
                elif service == 'lxmf.propagation':
                    advertised = lxmf.pn_name_from_app_data(app_data)
                elif service == 'nomadnetwork.node':
                    advertised = app_data.decode('utf-8', errors='replace')
            except Exception:
                advertised = None
        known = rns.Transport.has_path(destination_hash)
        interface = rns.Transport.next_hop_interface(destination_hash) if known else None
        record = dict(destination=destination_hash.hex(), identity=announced_identity.hash.hex(),
                      public_key=public.hex(), service=service, advertised_name=name_text(advertised),
                      last_heard=time.time(), observation='path_response' if is_path_response else 'announce',
                      announce_hash=announce_packet_hash.hex() if announce_packet_hash else None,
                      path_known_at_observation=bool(known), hops_at_observation=rns.Transport.hops_to(destination_hash) if known else None,
                      path_interface_at_observation=name_text(getattr(interface, 'name', None) or str(interface)) if interface else None,
                      station_id=self.owner.station, radio_id=self.owner.transport_id)
        with self.lock:
            if record['destination'] not in self.pending and len(self.pending) >= 64:
                self.pending.pop(next(iter(self.pending)))
            self.pending[record['destination']] = record
            if not self.notified:
                self.notified = True
                self.owner.post(dict(event='heard_ready'))

    def take(self):
        with self.lock:
            records = list(self.pending.values())
            self.pending.clear()
            self.notified = False
            return records


def encoded_size(state):
    if __package__:
        from .wire import encode
    else:
        from wire import encode
    try:return len(encode(state))
    except ValueError:return 32769
