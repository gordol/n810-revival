#!/usr/bin/env python3
"""Refresh the private local WWARA directory; never programs a radio."""
import argparse
import importlib.util
from pathlib import Path
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
URL = 'https://www.wwara.org/DataBaseExtract.zip'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'data/repeaters/repeaters.json')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('repeaters', ROOT/'shell/vendor/packet-console/n810-repeaters.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    request = urllib.request.Request(URL, headers={'User-Agent': 'Pocket-RepeaterDirectory/1.0'})
    with urllib.request.urlopen(request, timeout=60) as response:
        content = response.read(8*1024*1024+1)
    if len(content) > 8*1024*1024:
        raise ValueError('Directory download exceeds 8 MiB')
    with tempfile.TemporaryDirectory() as folder:
        archive = Path(folder)/'wwara.zip'
        archive.write_bytes(content)
        data = module.import_wwara(archive)
    if not data['repeaters']:
        raise ValueError('Empty directory; keeping previous snapshot')
    module.write(args.output, data)
    print(f"Installed {len(data['repeaters'])} WWARA repeaters, edition {data['edition']}: {args.output}")


if __name__ == '__main__':
    main()
