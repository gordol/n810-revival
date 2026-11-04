"""Built-in owner contracts shared by attachment, publication and controls.

These are supported client adapters, not permission grants. A peer catalogue
never gets to select a Python factory or enable an unregistered adapter.
"""
from collections import namedtuple
OwnerService=namedtuple('OwnerService','id title app factory')
OWNER_SERVICES=(OwnerService('reticulum','Reticulum','Reticulum','configure_reticulum'),
                OwnerService('meshcore','MeshCore','Messages','configure_meshcore'))
OWNER_IDS=tuple(service.id for service in OWNER_SERVICES)

def owner_factory(registry,identifier):
    for service in OWNER_SERVICES:
        if service.id==identifier:return getattr(registry,service.factory)
    raise ValueError('Unsupported owner service: '+identifier)

def saved_owner(identifier,directory):
    if identifier=='reticulum':
        from app_registry import saved_reticulum_selection
        return saved_reticulum_selection(directory)
    if identifier=='meshcore':
        from meshcore_service import saved_selection
        try:return saved_selection(directory)
        except FileNotFoundError:return None
    raise ValueError('Unsupported owner service: '+identifier)
