"""Blender 4.3: blender -b -P bake_market_person.py -- sam.glb sam.zlib"""
import hashlib
import io
import math
import struct
import sys
import zlib
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix,Vector
from PIL import Image

source,destination=map(Path,sys.argv[sys.argv.index('--')+1:])
if hashlib.sha256(source.read_bytes()).hexdigest() not in (
    'fbf6558ff408b6c5d12c82a5aaa506e07ec796f963a9ac1d4b9c88a39b0fd429',
    '3c22e60a599526d264f7cbb744e5bc1f6b1e93a79daade322942c49e7aac6ab3'):
    raise ValueError('Expected a documented Innerscene character GLB')
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(source))
scene=bpy.context.scene
arm=next(o for o in scene.objects if o.type=='ARMATURE')
objects=[o for o in scene.objects if o.type=='MESH' and o.find_armature()==arm
         and o.name not in ('Phone','teeth_base','Hairline | fine scalp roots')]
for o in objects:
    ratio={'Sam | anatomical body':.18,'Maya | anatomical body':.18,'ponytail01':.60,'short01':.48,'shoes01':.55}.get(o.name)
    if ratio:
        bpy.context.view_layer.objects.active=o
        mod=o.modifiers.new('Static topology for posing','DECIMATE')
        mod.ratio=ratio
        bpy.ops.object.modifier_move_to_index(modifier=mod.name,index=0)
        bpy.ops.object.modifier_apply(modifier=mod.name)

materials=list(dict.fromkeys(m for o in objects for m in o.data.materials))
tile=512
atlas=Image.new('RGBA',(tile*4,tile*4))
def srgb(v):
    return round(255*(12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055))
for i,m in enumerate(materials):
    bsdf=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    base=bsdf.inputs['Base Color']
    tex=next((link.from_node.image for link in base.links if link.from_node.type=='TEX_IMAGE'),None)
    cloth=m.name.endswith(('original top','original bottom'))
    if cloth:
        normal=next(n.image for n in m.node_tree.nodes if n.type=='TEX_IMAGE')
        pixels=np.asarray(Image.open(io.BytesIO(normal.packed_file.data)).convert('RGB').resize((tile,tile)),dtype=float)/127.5-1
        # Carry seams, lapels and fabric folds into the atlas for the mobile pass.
        light=np.clip(.85-.38*pixels[:,:,0]+.48*pixels[:,:,1],.40,1.0)
        bitmap=Image.fromarray((255*light).astype('uint8')).convert('RGBA')
    elif tex:
        bitmap=Image.open(io.BytesIO(tex.packed_file.data)).convert('RGBA').resize((tile,tile),Image.Resampling.LANCZOS)
        if 'short01' not in m.name and 'ponytail01' not in m.name and 'eyebrow' not in m.name and 'eyelash' not in m.name:bitmap.putalpha(255)
    else:
        bitmap=Image.new('RGBA',(tile,tile),tuple(srgb(v) for v in base.default_value[:3])+(255,))
    atlas.paste(bitmap,(i%4*tile,i//4*tile))

topology=[];indices=[];uvs=[];vertex_count=0
for o in objects:
    mesh=o.data
    mesh.calc_loop_triangles()
    lookup={};original=[]
    for tri in mesh.loop_triangles:
        mat=o.data.materials[tri.material_index]
        slot=materials.index(mat)
        for loop in tri.loops:
            k=mesh.loops[loop].vertex_index
            u,v=mesh.uv_layers.active.data[loop].uv if mesh.uv_layers.active else (.5,.5)
            key=(k,round(u,6),round(v,6),slot)
            if key not in lookup:
                lookup[key]=vertex_count;vertex_count+=1
                original.append(k)
                u=min(1.,max(0.,u));v=min(1.,max(0.,v))
                uvs.append(((slot%4*tile+.5+u*(tile-1))/atlas.width,
                            (slot//4*tile+.5+(1-v)*(tile-1))/atlas.height,
                            1. if mat.name.endswith('original top') else 2. if mat.name.endswith('original bottom') else 3. if 'body.shoes' in mat.name else 0.))
            indices.append(lookup[key])
    topology.append((o,np.array(original)))

def aim(bone,direction):
    b=arm.pose.bones[bone]
    rot=(b.tail-b.head).rotation_difference(arm.matrix_world.inverted().to_3x3()@Vector(direction))
    transform=b.matrix.copy()
    b.matrix=Matrix.Translation(transform.translation)@rot.to_matrix().to_4x4()@Matrix.Translation(-transform.translation)@transform
    bpy.context.view_layer.update()

poses=[];contacts=[]
for frame in range(17):
    if frame<12:scene.frame_set(frame*2)
    else:
        if frame==12:
            arm.animation_data_clear()
            for bone in arm.pose.bones:bone.matrix_basis=Matrix.Identity(4)
            bpy.context.view_layer.update()
        t=max(0,frame-13)/3
        for side,sign in (('l',1),('r',-1)):
            aim('upperarm_'+side,(.15*sign,-(.12+1.15*t),-.98+.64*t))
            aim('lowerarm_prox_'+side,(-.08*sign,-(.24+1.0*t),-.9+1.25*t))
    graph=bpy.context.evaluated_depsgraph_get()
    points=[];normals=[];sole=None
    for o,used in topology:
        ev=o.evaluated_get(graph)
        mesh=ev.data
        matrix=np.asarray(ev.matrix_world)
        pp=np.empty(len(mesh.vertices)*3,np.float32);mesh.vertices.foreach_get('co',pp)
        nn=np.empty_like(pp);mesh.vertices.foreach_get('normal',nn)
        pp=pp.reshape(-1,3)[used]@matrix[:3,:3].T+matrix[:3,3]
        nn=nn.reshape(-1,3)[used]@np.linalg.inv(matrix[:3,:3])
        if o.name.startswith('shoes'):
            shoes=pp
            sole=shoes[:,2].min()
        points.append(pp);normals.append(nn)
    for left in (False,True):
        foot=shoes[(shoes[:,0]>0)==left]
        lowest=foot[:,2].min()
        toe=foot[foot[:,2]<lowest+.018].mean(axis=0)
        contacts.append((toe[0],lowest-sole,-toe[1]))
    pp=np.concatenate(points);nn=np.concatenate(normals)
    pp[:,2]-=sole
    # Blender's -Y forward, Z up -> game +Z forward, Y up.
    pp=pp[:,[0,2,1]];pp[:,2]*=-1
    nn=nn[:,[0,2,1]];nn[:,2]*=-1
    nn/=np.maximum(1e-7,np.linalg.norm(nn,axis=1)[:,None])
    poses.append(np.column_stack((pp*10000,nn*32767)).round().astype('<i2').tobytes())
blob=struct.pack('<4s5I',b'NPC2',vertex_count,len(indices),len(poses),atlas.width,atlas.height)
blob+=np.asarray(contacts,dtype='<f4').tobytes()
blob+=np.asarray(indices,dtype='<u4').tobytes()+np.asarray(uvs,dtype='<f4').tobytes()
destination.write_bytes(zlib.compress(blob+b''.join(poses)+atlas.tobytes(),9))
print(destination,vertex_count,len(indices)//3,'triangles',destination.stat().st_size)
