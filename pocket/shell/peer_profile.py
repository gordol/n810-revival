# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Private, reusable profiles for native encrypted TCP peers."""
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import sys
from runtime_codec import atomic_write


def create_profile(base, mode, host, port, station, interpreter=None):
    if mode not in ('listen','connect'):raise ValueError('Choose Listen or Connect')
    host=str(ipaddress.ip_address(host.strip()))
    if mode=='connect' and ipaddress.ip_address(host).is_unspecified:raise ValueError('Enter the other device address')
    port=int(port)
    if not 1<=port<=65535:raise ValueError('Port must be between 1 and 65535')
    if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,80}',station):raise ValueError('Name: letters, numbers, dot, dash or underscore')
    identity=hashlib.sha256((mode+'\0'+host+'\0'+str(port)+'\0'+station).encode()).hexdigest()[:16]
    folder=Path(base).expanduser().resolve()/'direct-peers'/identity
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    if folder.is_symlink() or folder.stat().st_uid!=os.geteuid() or folder.stat().st_mode&0o077:
        raise ValueError('Peer profile must be a private folder owned by this user')
    value=dict(mode='local',state=str(folder/'identity'),interpreter=interpreter or sys.executable,
               station=station,carriers=[dict(type='tcp-server' if mode=='listen' else 'tcp-client',host=host,port=port)],relay=False)
    atomic_write(folder/'reticulum-owner.msgpack',value)
    return folder
