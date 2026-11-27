"""Prepare the same regional data and GPU buffers consumed by Pocket."""
import argparse

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('regions',nargs='+',choices=('sound','hoh','rainier'))
    for region in dict.fromkeys(parser.parse_args().regions):
        print(f'Preparing {region} terrain…',flush=True)
        if region=='rainier':
            from rainier_data import download
            from pnw import summit_approach,summit_horizon
            from pnw.river_scene_cache import valley_world
            from pnw.river_detail import RiverQuality
            download()
            summit_approach.samples()
            summit_horizon.samples()
            valley_world(RiverQuality().high,[])
        else:
            from pnw.outings import build_world
            world=build_world('plane' if region=='sound' else 'hoh',require_cache=True)
            print(f'{world[3]:,} vertices ready',flush=True)
            if region=='sound' and world[-1] is None:
                print('Elevation ready. Aerial imagery unavailable; retry to add it.',flush=True)
            del world
            if region=='sound':
                from pnw.cockpit import panel
                panel()

if __name__=='__main__':main()
