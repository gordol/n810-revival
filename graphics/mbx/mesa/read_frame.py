"""Validate Mesa post-transform frame input, never label it GPU output."""
from pathlib import Path
import collections, hashlib, json, math, struct, sys
HEADER = struct.Struct('<12I5f')
TRIANGLE = struct.Struct('<12I24f')

def read_frame(data):
    if len(data) < HEADER.size:
        raise ValueError('Truncated Mesa frame header')
    h = HEADER.unpack_from(data)
    magic, version, header_bytes, triangle_bytes, width, height, count, rejected = h[:8]
    if (magic, version, header_bytes, triangle_bytes) != (0x3146424d, 1, HEADER.size, TRIANGLE.size):
        raise ValueError('Unsupported Mesa frame ABI')
    if not 0 < width <= 4096 or not 0 < height <= 4096 or not 0 < count <= 16384:
        raise ValueError('Invalid frame dimensions or count')
    if len(data) != HEADER.size + count * TRIANGLE.size:
        raise ValueError('Truncated or trailing Mesa frame bytes')
    if rejected or h[9] or h[10] or h[11]:
        raise ValueError('Incomplete or unsupported frame capture')
    if not all(map(math.isfinite, h[12:])):
        raise ValueError('Nonfinite clear')
    triangles = []
    for i in range(count):
        t = TRIANGLE.unpack_from(data, HEADER.size + i * TRIANGLE.size)
        if not all(map(math.isfinite, t[12:])):
            raise ValueError('Nonfinite geometry')
        if t[0] > 1 or t[1] > 1 or t[2] > 7 or t[3] > 3 or t[4] > 1 or t[5] > 15:
            raise ValueError('Invalid raster state')
        if not 0 <= t[8] <= t[10] <= width or not 0 <= t[9] <= t[11] <= height:
            raise ValueError('Invalid clip rectangle')
        triangles.append(t)
    return h, triangles

def summarize(data):
    h, triangles = read_frame(data)
    state_counts = collections.Counter(t[:8] for t in triangles)
    positions = [t[12+i*8:16+i*8] for t in triangles for i in range(3)]
    colors = [t[16+i*8:20+i*8] for t in triangles for i in range(3)]
    return dict(status='VALIDATED_MESA_APPLICATION_INPUT_NOT_GPU_OUTPUT',
                sha256=hashlib.sha256(data).hexdigest(), width=h[4], height=h[5],
                triangles=h[6], clear_buffers=h[8], clear_color=h[12:16], clear_depth=h[16],
                position_ranges=[(min(v[i] for v in positions), max(v[i] for v in positions)) for i in range(4)],
                color_ranges=[(min(v[i] for v in colors), max(v[i] for v in colors)) for i in range(4)],
                states=[dict(depth_enabled=s[0], depth_write=s[1], depth_func=s[2], interpolation=s[3],
                             blend_enabled=s[4], color_mask=s[5], shader_inputs=s[6], sampler_views=s[7], count=n)
                        for s,n in state_counts.items()], hardware_acceleration_verified=False)

if __name__ == '__main__':
    print(json.dumps(summarize(Path(sys.argv[1]).read_bytes()), indent=2))
