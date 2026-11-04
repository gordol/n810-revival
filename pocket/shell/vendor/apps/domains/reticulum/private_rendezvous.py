"""Private direct-contact destinations using saved verified RNS public keys."""
from contacts import public_key

SERVICE = 'pocket.data.v1'


def destination_for(owner, peer, expected_key=None):
    """Resolve only the existing service; never announce, probe, grant or start RNS."""
    if not isinstance(peer,str) or len(peer)!=32 or any(c not in '0123456789abcdef' for c in peer):
        raise ValueError('Select a complete peer identity')
    record = owner.book.contacts.get(peer)
    if not record or record.get('state') != 'verified':
        raise ValueError('Verify the selected full peer key before private contact')
    key = public_key(record['card']['public_key'])
    if expected_key is not None and key != expected_key:
        raise ValueError('Selected peer key changed')
    if owner.RNS is None or owner.stack is None or owner.identity is None:
        raise ValueError('Connect the selected Reticulum transport first')
    RNS = owner.RNS
    identity = RNS.Identity(create_keys=False)
    identity.load_public_key(key)
    if identity.hash.hex() != peer:
        raise ValueError('Saved contact identity does not match its full key')
    destination = RNS.Destination(identity,RNS.Destination.OUT,RNS.Destination.SINGLE,'pocket','data','v1')
    route = 'cached_path' if RNS.Transport.has_path(destination.hash) else 'direct_contact'
    return destination, route
