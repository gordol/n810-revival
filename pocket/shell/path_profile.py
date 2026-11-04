"""Compute sampled terrain clearance and Fresnel clearance from elevation CSV."""
import argparse
import csv
import json
import math
from pathlib import Path
import sys

EARTH_M = 6371000.0
LIGHT_M_S = 299792458.0


def finite(value, label):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(label + ' must be finite')
    return float(value)


def profile(samples, *, frequency_mhz, tx_height_m, rx_height_m, k=4/3, fresnel_fraction=.6):
    frequency = finite(frequency_mhz, 'Frequency')
    tx = finite(tx_height_m, 'TX height')
    rx = finite(rx_height_m, 'RX height')
    k = finite(k, 'Earth radius factor')
    fraction = finite(fresnel_fraction, 'Fresnel fraction')
    if not 0 < frequency <= 100000 or not 0 <= tx <= 10000 or not 0 <= rx <= 10000 or not .1 <= k <= 10 or not 0 <= fraction <= 1:
        raise ValueError('Frequency, heights, k or Fresnel fraction outside bounds')
    if not isinstance(samples, (list, tuple)) or not 3 <= len(samples) <= 10000:
        raise ValueError('Provide 3 to 10000 ordered terrain samples')
    clean = []
    for distance, elevation in samples:
        distance = finite(distance, 'Distance')
        elevation = None if elevation is None else finite(elevation, 'Elevation')
        if distance < 0 or (clean and distance <= clean[-1][0]):
            raise ValueError('Distances must strictly increase from zero')
        clean.append((distance, elevation))
    total = clean[-1][0]
    if clean[0][0] != 0 or not 0 < total <= 200000:
        raise ValueError('Profile must start at zero and end within 200 km')
    if clean[0][1] is None or clean[-1][1] is None:
        raise ValueError('Both endpoint elevations are required')
    start = clean[0][1] + tx
    end = clean[-1][1] + rx
    wavelength = LIGHT_M_S / (frequency * 1e6)
    rows = []
    for distance, elevation in clean:
        ray = start + (end - start) * distance / total
        bulge = distance * (total - distance) / (2 * k * EARTH_M)
        radius = math.sqrt(wavelength * distance * (total - distance) / total)
        adjusted = None if elevation is None else elevation + bulge
        clearance = None if adjusted is None else ray - adjusted
        rows.append(dict(distance_m=distance, elevation_m=elevation, earth_bulge_m=bulge,
                         terrain_adjusted_m=adjusted, ray_m=ray, fresnel_radius_m=radius,
                         clearance_m=clearance,
                         fresnel_clearance_m=None if clearance is None else clearance - fraction * radius))
    missing = sum(row['elevation_m'] is None for row in rows)
    known = [row for row in rows if row['clearance_m'] is not None]
    obstruction = any(row['clearance_m'] < 0 for row in known)
    fresnel_obstruction = any(row['fresnel_clearance_m'] < 0 for row in known)
    return dict(distance_m=total, frequency_mhz=frequency, tx_height_m=tx, rx_height_m=rx,
                effective_earth_radius_factor=k, fresnel_fraction=fraction,
                missing_samples=missing, sample_count=len(rows),
                sampled_los='blocked' if obstruction else 'unknown' if missing else 'clear',
                sampled_fresnel='obstructed' if fresnel_obstruction else 'unknown' if missing else 'clear',
                minimum_sampled_clearance_m=min(row['clearance_m'] for row in known),
                minimum_sampled_fresnel_clearance_m=min(row['fresnel_clearance_m'] for row in known),
                basis='Sampled elevations and effective-earth geometry; not measured RF coverage. Unsampled obstacles are unknown.',
                samples=rows)


def read_csv(path):
    with Path(path).open(newline='') as source:
        reader = csv.DictReader(source)
        if reader.fieldnames != ['distance_m', 'elevation_m']:
            raise ValueError('CSV columns must be distance_m,elevation_m')
        rows = []
        for row in reader:
            if len(rows) == 10000:
                raise ValueError('Too many terrain samples')
            if None in row or row['distance_m'] is None or row['elevation_m'] is None:
                raise ValueError('Malformed CSV row')
            rows.append((float(row['distance_m']), None if not row['elevation_m'].strip() else float(row['elevation_m'])))
        return rows


def plot(result, destination):
    """Optional desktop export; the calculator itself uses only the standard library."""
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    destination = Path(destination)
    if destination.suffix.lower() not in ('.png', '.svg', '.pdf'):
        raise ValueError('Plot output must be PNG, SVG or PDF')
    rows = result['samples']
    distances = [r['distance_m'] / 1000 for r in rows]
    terrain = [float('nan') if r['terrain_adjusted_m'] is None else r['terrain_adjusted_m'] for r in rows]
    ray = [r['ray_m'] for r in rows]
    fraction = result['fresnel_fraction']
    lower = [r['ray_m'] - fraction*r['fresnel_radius_m'] for r in rows]
    upper = [r['ray_m'] + fraction*r['fresnel_radius_m'] for r in rows]
    fig, axis = plt.subplots(figsize=(10, 4.8), constrained_layout=True)
    try:
        axis.fill_between(distances, lower, upper, color='#2b83ba', alpha=.14,
                          label=f'{fraction:.0%} first Fresnel zone')
        axis.plot(distances, terrain, color='#6a613c', linewidth=2, label='Terrain with earth curvature')
        axis.plot(distances, ray, color='#2b83ba', linewidth=1.5, label='Direct ray')
        axis.set(xlabel='Distance (km)', ylabel='Elevation in effective-earth profile (m)',
                 title=f"Sampled path at {result['frequency_mhz']:g} MHz · LOS {result['sampled_los']} · Fresnel {result['sampled_fresnel']}")
        axis.grid(alpha=.2)
        axis.legend(loc='best')
        fig.text(.01, .005, f"k={result['effective_earth_radius_factor']:.3g}; missing samples={result['missing_samples']}. Geometry only; not measured coverage.", fontsize=8)
        with destination.open('xb') as output:
            fig.savefig(output, format=destination.suffix[1:].lower(), dpi=150)
    finally:
        plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--frequency-mhz', type=float, required=True)
    parser.add_argument('--tx-height-m', type=float, required=True)
    parser.add_argument('--rx-height-m', type=float, required=True)
    parser.add_argument('--k', type=float, default=4/3)
    parser.add_argument('--fresnel-fraction', type=float, default=.6)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plot', type=Path, help='optional PNG/SVG/PDF export; requires matplotlib')
    args = parser.parse_args(argv)
    try:
        result = profile(read_csv(args.csv), frequency_mhz=args.frequency_mhz,
                         tx_height_m=args.tx_height_m, rx_height_m=args.rx_height_m,
                         k=args.k, fresnel_fraction=args.fresnel_fraction)
        if args.output:
            with args.output.open('x') as output:
                json.dump(result, output, indent=2, allow_nan=False)
                output.write('\n')
        if args.plot:
            plot(result, args.plot)
        print(json.dumps({key: value for key, value in result.items() if key != 'samples'}, sort_keys=True))
        return 0
    except (OSError, ValueError, csv.Error, ImportError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
