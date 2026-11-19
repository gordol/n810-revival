"""Shared root-storage policy; the kernel and card use the same PARTUUID."""

def validate_target(target):
    if target not in ('internal','sd'):raise ValueError('Choose internal or sd storage')
    return target


def validate_size(target,size):
    validate_target(target)
    limit=1900 if target=='internal' else 8191
    if type(size) is not int or not 1024<=size<=limit:
        raise ValueError(f'{target} root must be 1024–{limit} MiB')
    return size


def require_target(manifest,target):
    if manifest.get('storage_target','internal')!=target:
        raise ValueError('This operation requires a '+target+' storage kit')
