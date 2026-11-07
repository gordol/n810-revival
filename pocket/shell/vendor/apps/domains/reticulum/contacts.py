"""Public Reticulum contact cards and explicit full-key fingerprint comparison."""
import hashlib
import hmac
if __package__:
    from .discovery_codec import pack,unpack,legacy_value
else:
    from discovery_codec import pack,unpack,legacy_value
import re
import os
from pathlib import Path
import tempfile
import time


def public_key(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{128}', value):
        raise ValueError('A public Reticulum identity requires 64 bytes')
    return bytes.fromhex(value)


def fingerprint(key):
    digest = hashlib.sha256(key).hexdigest().upper()
    return ' '.join(digest[i:i + 8] for i in range(0, len(digest), 8))


def card(key, label=''):
    if not isinstance(key, bytes) or len(key) != 64:
        raise ValueError('A public Reticulum identity requires 64 bytes')
    if not isinstance(label, str) or len(label) > 80 or not all(c.isprintable() for c in label):
        raise ValueError('Invalid contact label')
    return dict(type='reticulum_contact', version=1, label=label,
                identity=hashlib.sha256(key).digest()[:16].hex(), public_key=key.hex())


def parse_card(text):
    if isinstance(text,dict):value=text
    elif isinstance(text,bytes):
        if len(text)>2048:raise ValueError('Contact card exceeds 2 KiB')
        value=unpack(text)
    elif isinstance(text,str):
        if len(text.encode('utf-8'))>2048:raise ValueError('Contact card exceeds 2 KiB')
        value=legacy_value(text)
    else:raise ValueError('Expected a structured or binary contact card')
    if not isinstance(value, dict) or set(value) != {'type', 'version', 'label', 'identity', 'public_key'}:
        raise ValueError('Unsupported contact card fields')
    if value['type'] != 'reticulum_contact' or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('Unsupported contact card format')
    result = card(public_key(value['public_key']), value['label'])
    if value['identity'] != result['identity']:
        raise ValueError('Contact identity does not match its public key')
    # Importing a card establishes a candidate key, never human verification.
    return result


def compare(key, expected):
    if not isinstance(expected, str):
        return False
    normalized = ''.join(expected.split()).upper()
    if not re.fullmatch(r'[0-9A-F]{64}', normalized):
        return False
    return hmac.compare_digest(fingerprint(key).replace(' ', ''), normalized)


class ContactBook:
    """Single-owner persistent contacts; verification is bound to exact key bytes."""
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        info = self.directory.lstat()
        import stat
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Contacts directory must be privately owned with mode 0700')
        self.path = self.directory / 'contacts.msgpack'
        self.contacts = {}
        self._signature = None
        source=self.path if self.path.exists() or self.path.is_symlink() else self.path.with_suffix('.json')
        if source.exists() or source.is_symlink():
            info = source.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 1024 * 1024:
                raise ValueError('Unsafe contacts file')
            raw = source.read_bytes()
            value = unpack(raw) if source==self.path else legacy_value(raw)
            if not isinstance(value, dict) or value.get('version') != 1 or not isinstance(value.get('contacts'), dict):
                raise ValueError('Unsupported contacts file')
            if len(value['contacts']) > 1024:
                raise ValueError('Too many contacts')
            for identity, record in value['contacts'].items():
                contact = parse_card(record['card'])
                if identity != contact['identity'] or record.get('state') not in ('unverified', 'verified', 'revoked'):
                    raise ValueError('Invalid stored contact')
                if record['state'] == 'verified' and not compare(public_key(contact['public_key']), record.get('fingerprint')):
                    raise ValueError('Stored verification does not match the contact key')
                self.contacts[identity] = record
            if source==self.path:self._signature=hashlib.sha256(raw).digest()
            else:
                if source.read_bytes()!=raw:raise ValueError('Legacy contacts changed during migration')
                self._save(self.contacts)

    def _save(self, contacts):
        # One service owns this book. Detect outside changes rather than overwrite.
        current = hashlib.sha256(self.path.read_bytes()).digest() if self.path.exists() else None
        if current != self._signature:
            raise ValueError('Contacts changed outside this owner; reload before saving')
        raw = pack(dict(version=1,contacts=contacts))
        if len(raw) > 1024 * 1024:
            raise ValueError('Contacts exceed 1 MiB')
        fd, temporary = tempfile.mkstemp(prefix='.contacts-', dir=self.directory)
        try:
            with os.fdopen(fd, 'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            self.contacts = contacts
            self._signature = hashlib.sha256(raw).digest()
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def import_contact(self, text):
        contact = parse_card(text)
        identity = contact['identity']
        if identity in self.contacts:
            if self.contacts[identity]['card']['public_key'] != contact['public_key']:
                raise ValueError('Identity collision: existing key retained')
            return identity
        if len(self.contacts) >= 1024:
            raise ValueError('Contacts limit reached')
        records = dict(self.contacts)
        records[identity] = dict(card=contact, state='unverified')
        self._save(records)
        return identity

    def rename(self, identity, label):
        if not isinstance(label, str) or not 1 <= len(label) <= 64 or not label.strip() or not label.isprintable():
            raise ValueError('Nickname must contain 1–64 printable characters')
        record = self.contacts[identity]
        contact = dict(record['card'], label=label)
        records = dict(self.contacts)
        records[identity] = dict(record, card=contact)
        self._save(records)

    def verify(self, identity, expected_fingerprint):
        record = self.contacts[identity]
        key = public_key(record['card']['public_key'])
        if not compare(key, expected_fingerprint):
            raise ValueError('Fingerprint does not match the current peer key')
        if record['state'] == 'revoked':
            raise ValueError('Revoked key cannot be verified again; enroll a new identity')
        records = dict(self.contacts)
        records[identity] = dict(record, state='verified', fingerprint=fingerprint(key), verified_at=time.time())
        self._save(records)

    def revoke(self, identity):
        records = dict(self.contacts)
        records[identity] = dict(records[identity], state='revoked', revoked_at=time.time())
        self._save(records)

    def rows(self):
        result = []
        for identity, record in self.contacts.items():
            contact = record['card']
            conflicts = [other for other, value in self.contacts.items()
                         if other != identity and contact['label'] and
                         value['card']['label'] == contact['label']]
            result.append(dict(identity=identity, label=contact['label'], public_key=contact['public_key'],
                               state=record['state'], pinned=record['state'] == 'verified',
                               same_label_identities=conflicts))
        return result
