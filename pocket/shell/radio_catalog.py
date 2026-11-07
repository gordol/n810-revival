# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Saved radio files shared over bounded pages, independently of live polling.

The catalog owner reads files on its sampling worker. Clients assemble a complete
revision on a worker and publish it atomically; UI reads never perform transfers.
"""
import hashlib
import heapq
import json
import time

LIMIT=8*1024*1024
PAGE=16000


def load(root,cached):
    snapshot=None
    for path in heapq.nlargest(10,(root/'backups').glob('*/backup.json')):
        candidate=cached(path)
        if candidate and candidate.get('complete') is True and ('restore_bank' not in candidate or candidate.get('restored') is True):
            snapshot=candidate;break
    return dict(radio_snapshot=snapshot,radio_banks=cached(root/'banks.json'),radio_profiles=cached(root/'profiles.json'))


def pack(catalog):
    raw=json.dumps(catalog,separators=(',',':'),ensure_ascii=True).encode()
    if len(raw)>LIMIT:raise ValueError('Saved radio catalog exceeds 8 MiB')
    return raw,dict(revision=hashlib.sha256(raw).hexdigest(),size=len(raw))


def page(raw,manifest,payload):
    if payload.get('revision')!=manifest.get('revision'):raise ValueError('Radio catalog changed; retry sync')
    offset=payload.get('offset')
    if type(offset) is not int or not 0<=offset<len(raw) or offset%PAGE:raise ValueError('Invalid radio catalog offset')
    return dict(version=1,**manifest,offset=offset,chunk=raw[offset:offset+PAGE])


def fetch(exchange,manifest):
    size=manifest.get('size');revision=manifest.get('revision')
    if type(size) is not int or not 0<size<=LIMIT or not isinstance(revision,str) or len(revision)!=64:
        raise ValueError('Invalid saved radio catalog manifest')
    parts=[]
    for offset in range(0,size,PAGE):
        row=exchange(dict(version=1,action='snapshot',scope='radio-catalog',payload=dict(revision=revision,offset=offset)))
        chunk=row.get('chunk')
        if row.get('revision')!=revision or row.get('size')!=size or row.get('offset')!=offset or not isinstance(chunk,bytes) or len(chunk)!=min(PAGE,size-offset):
            raise ValueError('Incomplete saved radio catalog page')
        parts.append(chunk)
    raw=b''.join(parts)
    if hashlib.sha256(raw).hexdigest()!=revision:raise ValueError('Saved radio catalog checksum mismatch')
    catalog=json.loads(raw)
    if not isinstance(catalog,dict):raise ValueError('Invalid saved radio catalog')
    return dict(catalog,captured=time.time())
