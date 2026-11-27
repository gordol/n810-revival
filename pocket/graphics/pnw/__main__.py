"""Prepare the same regional data and GPU buffers consumed by Pocket."""
import argparse
from functools import partial
import subprocess
import sys
import zlib


def prepare_outdoors(outing):
    from pnw.outings import build_world
    textured=build_world(outing,prepare=True)
    if outing=='plane' and not textured:
        print('Elevation ready. Aerial imagery unavailable. Retry to add it.',flush=True)


def jobs(region):
    if region=='rainier':
        from pnw.river_scene_cache import summit_world,valley_world
        for quality in ('low','high'):
            yield f'valley {quality}',partial(valley_world,quality=='high',[],prepare=True)
        yield 'summit and meadow',partial(summit_world,prepare=True)
    else:
        yield region,partial(prepare_outdoors,'plane' if region=='sound' else 'hoh')
        if region=='sound':
            from pnw.cockpit import panel
            from pnw.market_visit import FLOORS,indoor
            yield 'cockpit',panel
            for floor in FLOORS:
                yield floor,partial(indoor,floor,prepare=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('regions',nargs='+',choices=('sound','hoh','rainier'))
    failed=False
    for region in dict.fromkeys(parser.parse_args().regions):
        for label,prepare in jobs(region):
            print(f'Checking {label}…',flush=True)
            try:prepare()
            except (OSError,ValueError,ImportError,subprocess.SubprocessError,zlib.error) as error:
                print(f'Could not prepare {label}: {error}',file=sys.stderr)
                failed=True
    if failed:raise SystemExit(1)


if __name__=='__main__':main()
