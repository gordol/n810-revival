"""Convert OpenGL feedback into projected MBX triangles and conservative damage bounds."""
import array
import math

def load_mesh(path, size):
    words = array.array('f')
    words.frombytes(path.read_bytes())
    vertices = []
    tiles = set()
    i = 0
    while i < len(words):
        token, count = words[i:i+2]
        assert token == 0x703 and int(count) >= 3
        i += 2
        polygon = []
        for _ in range(int(count)):
            x,y,z,r,g,b,a = words[i:i+7]
            i += 7
            color = sum(round(255*c) << (8*j) for j,c in enumerate((r,g,b,a)))
            polygon.append((x/200-1, y/200-1,z*2-1,color))
        for j in range(1,len(polygon)-1):
            tri = [polygon[0],polygon[j],polygon[j+1]]
            vertices.extend(tri)
            xs = [size/2 * (1+v[0]) for v in tri]
            ys = [size/2 * (1-v[1]) for v in tri]
            # Conservative box with a pixel margin for subpixel rounding.
            for tx in range(max(0,math.floor((min(xs)-1)/16)),min(size//16-1,math.floor((max(xs)+1)/16))+1):
                for ty in range(max(0,math.floor((min(ys)-1)/16)),min(size//16-1,math.floor((max(ys)+1)/16))+1):
                    tiles.add((tx,ty))
    return vertices,tiles
