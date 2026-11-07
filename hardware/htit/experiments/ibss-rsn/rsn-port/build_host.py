#!/usr/bin/env python3
"""Build the experimental upstream IBSS RSN adapter. No device or network access."""
from upstream_adapter import add_driver_sequence_callback
import hashlib
import pathlib
import shutil
import subprocess
import tarfile
import os,sys
from source_archive import archive as source_archive

HERE=pathlib.Path(__file__).resolve().parent
REPO=HERE.parents[2]
ARCHIVE=None
DIGEST='08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6'
BUILD=pathlib.Path(os.environ.get('HTIT_RSN_WORK','artifacts/htit-rsn')).resolve()/'host'

def build():
    global ARCHIVE
    ARCHIVE=source_archive()
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()!=DIGEST:
        raise SystemExit('Upstream archive checksum mismatch')
    BUILD.mkdir(parents=True,exist_ok=True)
    with tarfile.open(ARCHIVE) as archive:
        archive.extractall(BUILD,filter='data')
    src=BUILD/'wpa_supplicant-2.12'
    # Relocate this wrapper so its two platform headers resolve to our adapter.
    for name in ('ibss_rsn.c','ibss_rsn.h'):
        shutil.copyfile(src/'wpa_supplicant'/name,BUILD/name)
    add_driver_sequence_callback(BUILD/'ibss_rsn.c')
    files=[BUILD/'ibss_rsn.c',HERE/'rsn_port.c',HERE/'timers.c']
    files += [src/p for p in (
        'src/rsn_supp/wpa.c','src/rsn_supp/wpa_ie.c','src/rsn_supp/pmksa_cache.c',
        'src/ap/wpa_auth.c','src/ap/wpa_auth_ie.c','src/ap/pmksa_cache_auth.c',
        'src/common/wpa_common.c','src/common/ieee802_11_common.c',
        'src/utils/common.c','src/utils/wpabuf.c','src/utils/bitfield.c',
        'src/utils/os_unix.c','src/utils/wpa_debug.c',
        'src/crypto/crypto_openssl.c','src/crypto/sha1-prf.c',
        'src/crypto/sha256-prf.c','src/crypto/sha1-tprf.c',
    )]
    flags=subprocess.check_output(['pkg-config','--cflags','--libs','openssl'],text=True).split()
    command=['cc','-shared','-fPIC','-g','-O1','-Wall','-Wextra',
        '-Wno-unused-parameter','-Wno-deprecated-declarations',
        '-DCONFIG_IBSS_RSN','-DCONFIG_NO_STDOUT_DEBUG','-DCONFIG_NO_WPA_MSG',
        '-DCONFIG_NO_RANDOM_POOL','-DCONFIG_NO_CONFIG_WRITE',
        '-DCONFIG_NO_RADIUS','-DCONFIG_NO_VLAN','-DCONFIG_SHA256',
        '-I'+str(HERE),'-I'+str(BUILD),'-I'+str(src/'src'),'-I'+str(src/'src/utils'),
        *map(str,files),*flags,*(['-framework','CoreFoundation','-framework','SystemConfiguration'] if sys.platform=='darwin' else []),
        '-o',str(BUILD/'librsn.dylib')]
    subprocess.run(command,check=True)
    return BUILD/'librsn.dylib'

if __name__=='__main__':print(build())
