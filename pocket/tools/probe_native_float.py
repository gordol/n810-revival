"""Check exact native Flux output and measure kernel CPU cost in one process.

Run separately with each explicitly built library, on its target architecture.
Compare output_sha256 before comparing timings. This does not own the display,
load a GPU module, or measure presented desktop FPS.
"""
import argparse
from array import array
import hashlib
import importlib.util
import json
import time


def probe(library, frames=100):
    spec = importlib.util.spec_from_file_location('_cellengine', str(library))
    lib = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(lib)
    noop = lambda: None
    digest = hashlib.sha256()
    cases = 0
    for width, height in ((1, 1), (40, 15), (100, 29)):
        for ascii_mode, step, density, glow, arms in (
            (False, 0., 1., .15, 2), (True, 7., .5, 0., 0),
            (False, 41., 4., 1., 4), (False, .2, 1.3, .8, 2),
            (False, 1e12, 2., .7, 4), (False, -1e12, 2., .7, 4),
        ):
            base = lib.nebula(width, height, ascii_mode, noop)
            plane = lib.flux_surface(width, height, step, ascii_mode,
                                     density, glow, arms, base, noop)
            indices = array('I', range(width * height))
            digest.update(lib.export_cells(base, indices, True))
            digest.update(lib.export_cells(plane, indices, True))
            digest.update(lib.scene_indices(plane))
            cases += 1
    width, height = 100, 29
    base = lib.nebula(width, height, False, noop)
    for step in range(5):
        lib.flux_surface(width, height, float(step), False, 1., .15, 2, base, noop)
    wall, cpu = time.monotonic_ns(), time.process_time_ns()
    for step in range(frames):
        plane = lib.flux_surface(width, height, float(step), False,
                                 1., .15, 2, base, noop)
    cpu_ns, wall_ns = time.process_time_ns() - cpu, time.monotonic_ns() - wall
    return dict(cases=cases, output_sha256=digest.hexdigest(), frames=frames,
                width=width, height=height, cpu_ms=cpu_ns / 1e6,
                wall_ms=wall_ns / 1e6, cpu_ms_per_frame=cpu_ns / frames / 1e6,
                scope='Native Flux production only; no GPU or presentation')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('library')
    parser.add_argument('--frames', type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.frames <= 10000:
        parser.error('--frames must be between 1 and 10000')
    print(json.dumps(probe(args.library, args.frames), sort_keys=True))
