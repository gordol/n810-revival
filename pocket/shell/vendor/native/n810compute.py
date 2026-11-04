# SPDX-License-Identifier: MIT
"""Retained binary64 camera projection through one optional native batch call."""
from array import array
import ctypes
import math
from itertools import islice
from functools import lru_cache
from pathlib import Path

MAX_POINTS = 65536
DoublePtr = ctypes.POINTER(ctypes.c_double)


def camera_values(camera):
    right, down, forward = camera.axes()
    values = array('d', (*camera.origin, *right, *down, *forward,
                         camera.span_x, camera.span_y, camera.focal))
    if not all(math.isfinite(v) and abs(v) <= 1e12 for v in values):
        raise ValueError('camera is outside the finite numerical domain')
    if min(abs(camera.span_x), abs(camera.span_y)) < 1e-12:
        raise ValueError('camera span is too small')
    return values


def python_project(values, points):
    origin, right, down, forward = (values[i:i+3] for i in (0, 3, 6, 9))
    result = []
    for point in points:
        p = tuple(a-b for a, b in zip(point, origin))
        depth = sum(a*b for a, b in zip(p, forward))
        scale = values[14]/depth if values[14] and abs(depth) > 1e-9 else 1
        result.append((sum(a*b for a, b in zip(p, right))*scale/values[12]+.5,
                       sum(a*b for a, b in zip(p, down))*scale/values[13]+.5,
                       depth))
    return result


@lru_cache(maxsize=4)
def load_library(library):
    lib = ctypes.CDLL(str(Path(library).resolve()))
    lib.n810_compute_abi.argtypes = []
    lib.n810_compute_abi.restype = ctypes.c_uint32
    if lib.n810_compute_abi() != 1:
        raise ValueError('unsupported compute ABI')
    lib.n810_compute_vfp.argtypes = []
    lib.n810_compute_vfp.restype = ctypes.c_int
    lib.n810_project.argtypes = [DoublePtr, DoublePtr, DoublePtr,
                ctypes.c_size_t, ctypes.c_int]
    lib.n810_project.restype = ctypes.c_int
    return lib


class Projector:
    """Caller-owned point/output storage. Calls are synchronous and single owner."""
    def __init__(self, points, library=None):
        self.points = tuple(tuple(point) for point in islice(points, MAX_POINTS+1))
        if len(self.points) > MAX_POINTS or any(len(p) != 3 for p in self.points):
            raise ValueError('expected at most 65536 three-component points')
        self.input = array('d', (v for p in self.points for v in p))
        if self.input.itemsize != 8 or not all(math.isfinite(v) and abs(v) <= 1e12 for v in self.input):
            raise ValueError('points must be finite binary64 within +/-1e12')
        self.output = array('d', [0.0]) * len(self.input)
        self._input = (ctypes.c_double*len(self.input)).from_buffer(self.input)
        self._output = (ctypes.c_double*len(self.output)).from_buffer(self.output)
        self.library = None
        self.last_backend = 'python'
        if library is not None:
            self.library = load_library(str(library))

    def project(self, camera, backend='auto'):
        if backend not in ('auto', 'python', 'soft', 'vfp'):
            raise ValueError('unknown projection backend')
        values = camera_values(camera)
        if backend == 'python' or (self.library is None and backend == 'auto'):
            self.last_backend = 'python'
            return python_project(values, self.points)
        if self.library is None:
            raise RuntimeError('native library was not supplied')
        c = (ctypes.c_double*15).from_buffer(values)
        status = self.library.n810_project(c, self._input, self._output,
                                          len(self.points),
                                          dict(auto=0, soft=1, vfp=2)[backend])
        if status == -4:
            self.last_backend = 'python-threshold'
            return [camera.project(p) for p in self.points]
        if status < 0:
            raise RuntimeError('native projection rejected the batch: '+str(status))
        self.last_backend = 'vfp' if status == 2 else 'soft'
        return list(zip(self.output[0::3], self.output[1::3], self.output[2::3]))
