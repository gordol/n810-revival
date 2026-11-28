"""Blender 4.3: blender -b -P bake_market_person.py -- sam.glb sam.zlib"""
import hashlib
import io
import math
import struct
import sys
import zlib
import zipfile
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix,Quaternion,Vector
from PIL import Image

args=list(map(Path,sys.argv[sys.argv.index('--')+1:]))
source,destination=args[:2]
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
        if o.name.endswith('anatomical body'):
            # GLB splits the skin at shading and UV seams. Simplifying each
            # island separately leaves pinholes through the animated face.
            import bmesh
            skin=bmesh.new()
            skin.from_mesh(o.data)
            bmesh.ops.remove_doubles(skin,verts=list(skin.verts),dist=1e-6)
            skin.to_mesh(o.data)
            skin.free()
        mod=o.modifiers.new('Static topology for posing','DECIMATE')
        mod.ratio=ratio
        bpy.ops.object.modifier_move_to_index(modifier=mod.name,index=0)
        bpy.ops.object.modifier_apply(modifier=mod.name)

materials=list(dict.fromkeys(m for o in objects for m in o.data.materials))
tile=512
atlas=Image.new('RGBA',(tile*4,tile*4))
def srgb(v):
    return round(255*(12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055))
def garment(material):
    name=material.name
    if name.endswith(('original top','plum satin full-length top')):return 1
    if name.endswith(('original bottom','charcoal tailored trousers')):return 2
    return 0

for i,m in enumerate(materials):
    bsdf=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
    base=bsdf.inputs['Base Color']
    tex=next((link.from_node.image for link in base.links if link.from_node.type=='TEX_IMAGE'),None)
    if garment(m):
        normal_map=bsdf.inputs['Normal'].links[0].from_node
        normal=normal_map.inputs['Color'].links[0].from_node.image
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
                            garment(mat) or (3. if 'body.shoes' in mat.name else 0.)))
            indices.append(lookup[key])
    topology.append((o,np.array(original)))

def aim(bone,direction):
    b=arm.pose.bones[bone]
    rot=(b.tail-b.head).rotation_difference(arm.matrix_world.inverted().to_3x3()@Vector(direction))
    transform=b.matrix.copy()
    b.matrix=Matrix.Translation(transform.translation)@rot.to_matrix().to_4x4()@Matrix.Translation(-transform.translation)@transform
    bpy.context.view_layer.update()

def relax_hand(side,open_hand):
    # Curl each phalanx toward the palm. Derive the flexion axis from
    # the hand itself so it mirrors correctly on the opposite side.
    bones=arm.data.bones
    knuckle=bones['middle_01_'+side]
    across=bones['index_01_'+side].head_local-bones['pinky_01_'+side].head_local
    palm=across.cross(knuckle.tail_local-knuckle.head_local).normalized()
    if palm.dot(bones['thumb_03_'+side].tail_local-knuckle.head_local)<0:palm.negate()
    for finger,angle in (('index',7),('middle',10),('ring',13),('pinky',16)):
        for joint,factor in (('01',1.),('02',1.15),('03',.55)):
            name=f'{finger}_{joint}_{side}'
            bone=bones[name]
            axis=(bone.tail_local-bone.head_local).cross(palm)
            local=bone.matrix_local.to_3x3().inverted()@axis
            arm.pose.bones[name].rotation_quaternion=Quaternion(local,math.radians(angle*factor*(.4 if open_hand else 1.)))
    bpy.context.view_layer.update()

def hang_wrist(side,forward):
    # The wrist bone points diagonally across this rig's hand. Use the
    # knuckles to orient the palm, with the thumb toward the direction of travel.
    bones=arm.pose.bones
    wrist=bones['hand_'+side]
    middle=bones['middle_01_'+side].head
    across=bones['index_01_'+side].head-bones['pinky_01_'+side].head
    def basis(length,width):
        length=length.normalized()
        width=(width-length*width.dot(length)).normalized()
        return Matrix((length,width,length.cross(width))).transposed()
    local=arm.matrix_world.inverted().to_3x3()
    target=basis(local@Vector((0,-math.sin(forward),-math.cos(forward))),local@Vector((0,-1,0)))
    rotation=target@basis(middle-wrist.head,across).transposed()
    pivot=Matrix.Translation(wrist.head)
    wrist.matrix=pivot@rotation.to_4x4()@pivot.inverted()@wrist.matrix
    bpy.context.view_layer.update()

def world_head(name):
    return arm.matrix_world@arm.pose.bones[name].head

def ease(x):
    x=min(1.,max(0.,x))
    return x*x*(3-2*x)

def walking_legs(cycle):
    # Solve to the ankle in metres. Each stance travels back at street speed.
    # The swing starts and ends at the same velocity as the planted foot.
    phase=math.tau*cycle
    pelvis=arm.pose.bones['pelvis']
    # A small pelvic turn advances the stepping hip; the rib cage counters it.
    twist=math.radians(3.2)*math.cos(phase)
    up=arm.matrix_world.inverted().to_3x3()@Vector((0,0,1))
    pivot=Matrix.Translation(pelvis.head)
    transform=pivot@Matrix.Rotation(twist,4,up)@pivot.inverted()@pelvis.matrix
    shift=Vector((-.020*math.sin(phase),0,-.046-.012*math.cos(2*phase)))
    transform.translation+=arm.matrix_world.inverted().to_3x3()@shift
    pelvis.matrix=transform
    bpy.context.view_layer.update()
    spine=arm.pose.bones['spine_02']
    pivot=Matrix.Translation(spine.head)
    spine.matrix=pivot@Matrix.Rotation(-1.7*twist,4,up)@pivot.inverted()@spine.matrix
    bpy.context.view_layer.update()
    for side,sign in (('l',1),('r',-1)):
        t=(cycle+(.5 if sign==1 else 0))%1
        stance=.57
        stride=1.10
        forward=stride*(stance/2-t)
        lift=0.
        # Rock over the heel at contact and the toe at push-off. Smoothstep
        # leaves the sole flat through midstance and joins the swing smoothly.
        heel=-.17
        toe=.30
        roll=heel*(1-ease(t/.13))+toe*ease((t-.40)/(stance-.40))
        if t>=stance:
            swing=(t-stance)/(1-stance)
            forward+=stride*swing*swing*(3-2*swing)
            lift=.065*math.sin(math.pi*swing)**2
            roll=toe+(heel-toe)*ease(swing)
        hip=world_head('thigh_'+side)
        knee=world_head('calf_'+side)
        rest=arm.matrix_world@arm.data.bones['foot_'+side].head_local
        goal=Vector((sign*(.098+.013*lift/.065),rest.y-forward,rest.z+lift))
        # Rotate the ankle about the contacting end of the shoe, including
        # its fore/aft displacement, before solving the knee to that ankle.
        contact=Vector((0,.052 if roll<0 else -.155,-rest.z))
        goal+=contact-Matrix.Rotation(roll,3,'X')@contact
        axis=(goal-hip).normalized()
        pole=Vector((0,-1,0))
        pole=(pole-axis*pole.dot(axis)).normalized()
        thigh=(knee-hip).length
        calf=arm.pose.bones['calf_'+side]
        shin=(arm.matrix_world.to_3x3()@(calf.tail-calf.head)).length
        length=min((goal-hip).length,thigh+shin-.0001)
        along=(thigh**2-shin**2+length**2)/(2*length)
        bend=math.sqrt(max(0,thigh**2-along**2))
        aim('thigh_'+side,axis*along+pole*bend)
        aim('calf_'+side,goal-world_head('calf_'+side))
        foot=arm.pose.bones['foot_'+side]
        # Restore the shoe's rest orientation after solving its parents.
        basis=arm.data.bones['foot_'+side].matrix_local.copy()
        # The source foot is a separate root, not a child of the calf.
        basis.translation=arm.matrix_world.inverted()@goal
        foot.matrix=basis
        bpy.context.view_layer.update()
        if roll:
            direction=arm.matrix_world.to_3x3()@(foot.tail-foot.head)
            aim('foot_'+side,Matrix.Rotation(roll,3,'X')@direction)

def walking_arms(phase):
    for side,sign in (('l',1),('r',-1)):
        # Left foot trails at stride zero as the left arm swings forward.
        # Drive the elbow parent shared by the wrist and forearm twist bone.
        # Sam's jacket needs clearance at the hip. A smaller right-hand
        # swing keeps the arms asymmetric without pinning the elbow in place.
        swing=.83 if jacket and side=='r' else 1.
        shoulder=sign*.21*swing*math.cos(phase)
        forearm=.35+sign*.29*swing*math.cos(phase-.18)
        upper_out=.22 if jacket else .32
        lower_out=.065 if jacket else .105
        aim('upperarm_'+side,(sign*upper_out,-math.sin(shoulder),-math.cos(shoulder)))
        aim('lowerarm_'+side,(sign*lower_out,-math.sin(forearm),-math.cos(forearm)))
        # A sleeve twist bone can point the right way without moving the
        # hand. Check the rendered joint chain before writing the asset.
        bones=arm.pose.bones
        wrist_axis=arm.matrix_world.to_3x3()@(bones['hand_'+side].head-bones['lowerarm_'+side].head)
        intended=Vector((sign*lower_out,-math.sin(forearm),-math.cos(forearm)))
        if wrist_axis.angle(intended)>math.radians(3):
            raise ValueError(f'{side} wrist does not follow its elbow')
        hang_wrist(side,forearm-.04)
        relax_hand(side,False)

def clearance_surfaces():
    """Keep forearms/hands separate from the shirt body and upper trousers."""
    result=[]
    for obj in objects:
        shirt=any(garment(m) for m in obj.data.materials)
        if not shirt and not obj.name.endswith('anatomical body'):continue
        mesh=obj.data
        mesh.calc_loop_triangles()
        groups=[obj.vertex_groups[max(v.groups,key=lambda g:g.weight).group].name if v.groups else ''
                for v in mesh.vertices]
        probes=[];clothes=[]
        for tri in mesh.loop_triangles:
            ids=tuple(tri.vertices)
            names=[groups[k] for k in ids]
            if all(n.startswith(('lowerarm','hand','index','middle','pinky','ring','thumb')) for n in names):
                probes.append(ids)
            if shirt and all(n.startswith(('spine','pelvis','thigh','calf')) for n in names):
                clothes.append(ids)
        result.append((obj,probes,clothes))
    return result

def check_clearance(points,arms,clothes,pose):
    from mathutils.bvhtree import BVHTree
    limbs=BVHTree.FromPolygons(points,arms,all_triangles=True)
    torso=BVHTree.FromPolygons(points,clothes,all_triangles=True)
    if limbs.overlap(torso):raise ValueError(f'Forearm or hand intersects clothing in pose {pose}')

surfaces=clearance_surfaces()
arm_faces=[];cloth_faces=[];point_count=0
for obj,probes,fabric in surfaces:
    arm_faces.extend(tuple(point_count+k for k in tri) for tri in probes)
    cloth_faces.extend(tuple(point_count+k for k in tri) for tri in fabric)
    point_count+=len(obj.data.vertices)
walk_surfaces=[]
# The imported accessory walk has widely spaced ankles and exaggerated
# vertical travel. Start each sample from rest to avoid inheriting that pose.
jacket=any(o.name.startswith('Sam | anatomical body') for o in objects)
arm.animation_data_clear()
poses=[];contacts=[]
for frame in range(16):
    for bone in arm.pose.bones:bone.matrix_basis=Matrix.Identity(4)
    bpy.context.view_layer.update()
    if frame<12:
        walking_legs(frame/12)
        walking_arms(math.tau*frame/12)
    else:
        left=frame in (13,15)
        lean=1 if left else -1
        for name,axis,degrees in (('spine_01','Y',2.8*lean),('spine_02','Z',4*lean),
                                  ('neck_01','Z',7*lean),('head','X',-3 if left else 2)):
            bone=arm.pose.bones[name]
            pivot=Matrix.Translation(bone.head)
            world_axis=arm.matrix_world.inverted().to_3x3()@Vector({'X':(1,0,0),'Y':(0,1,0),'Z':(0,0,1)}[axis])
            bone.matrix=pivot@Matrix.Rotation(math.radians(degrees),4,world_axis)@pivot.inverted()@bone.matrix
            bpy.context.view_layer.update()
        for side,sign in (('l',1),('r',-1)):
            bent=(sign==lean)
            upper=(.18*sign,-(.16 if bent else .05),-.98)
            lower=(.01*sign,-(.41 if bent else .22),-.95)
            if frame==14 and side=='r':
                upper=(.14,-.84,-.51)
                lower=(.10,-.96,.29)
            if frame==15:
                upper=(.20*sign,-.58,-.72)
                lower=(-.32*sign,-.86,.32)
            aim('upperarm_'+side,upper)
            aim('lowerarm_'+side,lower)
            reaching=frame==15 or (frame==14 and side=='r')
            if not reaching:hang_wrist(side,.27 if bent else .10)
            relax_hand(side,reaching)
    graph=bpy.context.evaluated_depsgraph_get()
    if frame<12:
        sampled=[]
        for obj,_,_ in surfaces:
            ev=obj.evaluated_get(graph)
            sampled.extend(tuple(ev.matrix_world@v.co) for v in ev.data.vertices)
        sampled=np.asarray(sampled)
        walk_surfaces.append(sampled)
        check_clearance(sampled,arm_faces,cloth_faces,frame)
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
# Check the interpolation the GPU actually displays, including the loop seam.
for frame,start in enumerate(walk_surfaces):
    end=walk_surfaces[(frame+1)%12]
    for fraction in (.25,.5,.75):
        check_clearance(start+(end-start)*fraction,arm_faces,cloth_faces,frame+fraction)
# Fit the selected CC0 optical frames to each pose using the two eyeballs.
if len(args)>2:
    pack=args[2].read_bytes()
    if hashlib.sha256(pack).hexdigest()!='f215c58e09e31b7ee568c814067cb47704cee6da1f6fc01cffb8e9fca37bafdd':
        raise ValueError('Expected the documented Glasses 01 CC0 pack')
    uv=np.array(uvs)
    eye_slot=2 if jacket else 4
    eyes=np.flatnonzero((uv[:,0]*4).astype(int)+4*(uv[:,1]*4).astype(int)==eye_slot)
    base=np.frombuffer(poses[0],'<i2').reshape(-1,6)[eyes,:3]
    right_eye=base[:,0]>base[:,0].mean()
    with zipfile.ZipFile(io.BytesIO(pack)) as archive:
        for style,filename in enumerate(("Sagerfrog's_Glasses_01.obj","TBM_Glasses_Frames_01.obj"),4):
            path=next(n for n in archive.namelist() if n.endswith('/'+filename))
            points=[];faces=[]
            for line in archive.read(path).decode().splitlines():
                parts=line.split()
                if parts[:1]==['v']:points.append(list(map(float,parts[1:4])))
                if parts[:1]==['f']:
                    corners=[int(term.split('/')[0])-1 for term in parts[1:]]
                    faces.extend((corners[0],a,b) for a,b in zip(corners[1:],corners[2:]))
            points=np.array(points)
            points-=np.array([points[:,0].mean(),(points[:,1].max()+points[:,1].min())/2,points[:,2].max()])
            points*=.157/np.ptp(points[:,0])
            points[:,2]+=.024
            faces=np.array(faces)
            normals=np.zeros_like(points)
            tri=points[faces]
            for corner in faces.T:np.add.at(normals,corner,np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]))
            normals/=np.maximum(1e-9,np.linalg.norm(normals,axis=1)[:,None])
            for frame,pose in enumerate(poses):
                eye=np.frombuffer(pose,'<i2').reshape(-1,6)[eyes,:3]/10000.
                across=eye[right_eye].mean(0)-eye[~right_eye].mean(0)
                across/=np.linalg.norm(across)
                forward=np.cross(across,[0,1,0]);forward/=np.linalg.norm(forward)
                basis=np.array([across,np.cross(forward,across),forward])
                coords=points@basis+eye.mean(0)
                poses[frame]+=np.column_stack((coords*10000,normals@basis*32767)).round().astype('<i2').tobytes()
            indices.extend((faces+vertex_count).ravel())
            uvs.extend([(.875,.875,float(style))]*len(points))
            vertex_count+=len(points)
blob=struct.pack('<4s5I',b'NPC3',vertex_count,len(indices),len(poses),atlas.width,atlas.height)
blob+=np.asarray(contacts,dtype='<f4').tobytes()
blob+=np.asarray(indices,dtype='<u4').tobytes()+np.asarray(uvs,dtype='<f4').tobytes()
destination.write_bytes(zlib.compress(blob+b''.join(poses)+atlas.tobytes(),9))
print(destination,vertex_count,len(indices)//3,'triangles',destination.stat().st_size)
