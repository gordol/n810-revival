"""Fetch and verify the public WPA source used by the optional RSN adapter."""
import hashlib,os,urllib.request
from pathlib import Path
DIGEST='08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6'
URL='https://w1.fi/releases/wpa_supplicant-2.12.tar.gz'
def archive():
    root=Path(os.environ.get('HTIT_RSN_WORK','artifacts/htit-rsn')).resolve()
    root.mkdir(parents=True,exist_ok=True)
    target=root/'wpa_supplicant-2.12.tar.gz'
    if not target.exists():
        with urllib.request.urlopen(URL,timeout=60) as response:body=response.read(16*1024*1024+1)
        if hashlib.sha256(body).hexdigest()!=DIGEST:raise ValueError('WPA source checksum mismatch')
        temporary=target.with_suffix('.part');temporary.write_bytes(body);temporary.replace(target)
    if hashlib.sha256(target.read_bytes()).hexdigest()!=DIGEST:raise ValueError('WPA source checksum mismatch')
    return target
