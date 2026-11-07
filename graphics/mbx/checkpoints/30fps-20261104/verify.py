#!/usr/bin/env python3
"""Verify the source bytes and decoded fixture against the sealed checkpoint."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def verify():
    manifest = json.loads((ROOT / 'SOURCE.json').read_text())
    for name, entry in manifest['source_files'].items():
        data = (ROOT / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('Checkpoint source differs: ' + name)
        if entry.get('encoding') == 'hex':
            decoded = bytes.fromhex(data.decode())
            if (len(decoded) != entry['decoded_bytes'] or
                    hashlib.sha256(decoded).hexdigest() != entry['decoded_sha256']):
                raise ValueError('Checkpoint fixture differs: ' + name)
    kernel = ROOT / 'experiments/vgp-service-20261104/kernel'
    for name, expected in manifest['module_build_source_sha256'].items():
        if hashlib.sha256((kernel / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Tested module input differs: ' + name)
    print(f"Verified {len(manifest['source_files'])} archived files and "
          f"{len(manifest['module_build_source_sha256'])} tested module inputs.", flush=True)
    return manifest


if __name__ == '__main__':
    verify()
