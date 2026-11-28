"""Bake the CarConcept glTF exterior into material groups for the compatibility renderer."""
import argparse
import json
import struct
import zlib
from pathlib import Path
import numpy as np

def bake(source):
    data=source.read_bytes()
    size=struct.unpack_from('<I',data,12)[0]
    gltf=json.loads(data[20:20+size])
    payload=memoryview(data)[28+size:]

    def read(index):
        accessor=gltf['accessors'][index]
        view=gltf['bufferViews'][accessor['bufferView']]
        dtype=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[accessor['componentType']])
        columns={'SCALAR':1,'VEC3':3}[accessor['type']]
        return np.ndarray((accessor['count'],columns),dtype=dtype,buffer=payload,
                          offset=view.get('byteOffset',0)+accessor.get('byteOffset',0),
                          strides=(view.get('byteStride',columns*dtype.itemsize),dtype.itemsize))

    groups=[[] for _ in range(29)]
    def visit(index,parent):
        node=gltf['nodes'][index]
        transform=parent@np.asarray(node.get('matrix',np.eye(4))).reshape(4,4).T
        for child in node.get('children',[]):visit(child,transform)
        if 'mesh' not in node or node.get('name','').startswith(('Interior','Engine')):return
        for prim in gltf['meshes'][node['mesh']]['primitives']:
            pos=read(prim['attributes']['POSITION'])@transform[:3,:3].T+transform[:3,3]
            normal=read(prim['attributes']['NORMAL'])@np.linalg.inv(transform[:3,:3])
            grid=np.round(pos/.034)
            _,ids=np.unique(grid,axis=0,return_inverse=True)
            count=np.bincount(ids)
            verts=np.column_stack([np.bincount(ids,weights=col)/count for col in np.column_stack((pos,normal)).T])
            verts[:,3:]/=np.maximum(.001,np.linalg.norm(verts[:,3:],axis=1))[:,None]
            tris=ids[read(prim['indices']).reshape(-1,3)]
            tris=tris[(tris[:,0]!=tris[:,1])&(tris[:,1]!=tris[:,2])&(tris[:,0]!=tris[:,2])]
            groups[prim['material']].append(verts[tris.ravel()])
    for root in gltf['scenes'][gltf.get('scene',0)]['nodes']:visit(root,np.eye(4))
    groups=[np.concatenate(g) if g else np.empty((0,6)) for g in groups]
    vertices=np.concatenate(groups)
    # Orient the nose toward local +Z using the headlamp and brake-lamp positions.
    if groups[14][:,2].mean()<groups[13][:,2].mean():vertices[:,[0,2,3,5]]*=-1
    low=vertices[:,:3].min(axis=0);high=vertices[:,:3].max(axis=0)
    vertices[:,:3]-=[(low[0]+high[0])/2,low[1],(low[2]+high[2])/2]
    vertices[:,:3]*=4.5/(high[2]-low[2])
    header=struct.pack('<29I',*(len(g) for g in groups))
    return zlib.compress(header+vertices.astype('<f4').tobytes(),9)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.write_bytes(bake(args.source))
