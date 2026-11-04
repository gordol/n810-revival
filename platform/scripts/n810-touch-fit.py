#!/usr/bin/env python3
"""Fit four visible targets; use the fifth (center) as an independent check."""
import csv
import json
import math
import sys
from pathlib import Path

TARGETS = [(80, 48), (720, 48), (720, 432), (80, 432), (400, 240)]


def solve(matrix, vector):
    rows = [list(row) + [value] for row, value in zip(matrix, vector)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda row: abs(rows[row][col]))
        if abs(rows[pivot][col]) < 1e-10:
            raise ValueError('Degenerate touch coordinates')
        rows[col], rows[pivot] = rows[pivot], rows[col]
        scale = rows[col][col]
        rows[col] = [value / scale for value in rows[col]]
        for row in range(3):
            if row != col:
                scale = rows[row][col]
                rows[row] = [a - scale * b for a, b in zip(rows[row], rows[col])]
    return [row[3] for row in rows]


def fit(points):
    if len(points) != 5:
        raise ValueError('Exactly five targets required')
    for point, target in zip(points, TARGETS):
        if (point['screen_x'], point['screen_y']) != target:
            raise ValueError('Unexpected target order or geometry')
        if point['samples'] < 3:
            raise ValueError('Each target needs at least three input frames')
        if not all(math.isfinite(point[key]) and 0 <= point[key] <= 4095
                   for key in ('raw_x', 'raw_y')):
            raise ValueError('Invalid raw coordinates')
    # Normalize raw values for numerical stability, then convert coefficients back.
    vectors = [[p['raw_x'] / 4096, p['raw_y'] / 4096, 1] for p in points[:4]]
    normal = [[sum(v[i] * v[j] for v in vectors) for j in range(3)] for i in range(3)]
    coefficients = []
    for key in ('screen_x', 'screen_y'):
        rhs = [sum(v[i] * p[key] for v, p in zip(vectors, points[:4])) for i in range(3)]
        a, b, c = solve(normal, rhs)
        coefficients.append([a / 4096, b / 4096, c])
    errors = []
    for point in points:
        predicted = [a * point['raw_x'] + b * point['raw_y'] + c
                     for a, b, c in coefficients]
        errors.append(math.hypot(predicted[0] - point['screen_x'], predicted[1] - point['screen_y']))
    if max(errors[:4]) > 10 or errors[4] > 15:
        raise ValueError('Target error too large; repeat the visible calibration')
    return {'version': 1, 'device_name': 'TSC2005 touchscreen',
            'screen_width': 800, 'screen_height': 480,
            'mapping': 'pixel = a * raw_x + b * raw_y + c',
            'x': coefficients[0], 'y': coefficients[1],
            'corner_max_error_px': max(errors[:4]), 'center_error_px': errors[4]}


def main():
    if len(sys.argv) != 2:
        raise ValueError('Usage: n810-touch-fit.py TARGETS.csv > calibration.json')
    with Path(sys.argv[1]).open() as stream:
        points = [{key: float(value) for key, value in row.items()} for row in csv.DictReader(stream)]
    print(json.dumps(fit(points), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        print(error, file=sys.stderr)
        sys.exit(1)
