#!/usr/bin/env python3
"""Verify pinned artifacts; --fetch allows public downloads; no installation.

Default retrieves only the open C55x source. --all also selects the TI manual
and the two proprietary MBX reference archives. No supplied software is run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import tempfile
import urllib.request


def verify(path, spec):
    if not path.is_file() or path.stat().st_size != spec['bytes']:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == spec['sha256']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cache', type=Path)
    parser.add_argument('--fetch', action='store_true')
    parser.add_argument('--all', action='store_true')
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    specs = json.loads(Path(__file__).with_name('artifacts.json').read_text())['artifacts']
    for spec in specs:
        if spec['group'] != 'c55x' and not args.all:
            continue
        target = args.cache / spec['name']
        if not verify(target, spec):
            if target.exists():
                raise ValueError(f'existing artifact failed verification: {target}')
            if not args.fetch:
                raise FileNotFoundError(f'missing {target}; --fetch permits download')
            descriptor, temp_name = tempfile.mkstemp(prefix=target.name + '.', suffix='.partial', dir=args.cache)
            os.close(descriptor)
            temporary = Path(temp_name)
            started = time.monotonic()
            try:
                with urllib.request.urlopen(spec['url'], timeout=30) as response, temporary.open('wb') as output:
                    if 'text/html' in response.headers.get('Content-Type', '').lower():
                        raise ValueError('HTML response is not the requested artifact')
                    received = 0
                    while chunk := response.read(262144):
                        received += len(chunk)
                        if received > spec['bytes'] or time.monotonic() - started > 240:
                            raise ValueError('download exceeded size/time bound')
                        output.write(chunk)
                if not verify(temporary, spec):
                    raise ValueError('download size/SHA256 mismatch')
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        print(f"verified {spec['name']} {spec['sha256']}")


if __name__ == '__main__':
    main()
