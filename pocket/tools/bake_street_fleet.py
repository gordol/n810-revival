"""Bake original delivery van, transit bus and tractor-trailer meshes with Blender."""
from array import array
import math
from pathlib import Path
import struct
import zlib

import bpy

OUTPUT=Path(__file__).resolve().parents[1]/'graphics/assets/seattle'
PAINT,GLASS,RUBBER,CHROME,WHITE,HEAD,TAIL,AMBER=10,1,0,15,17,14,13,12


def box(center,size,material,bevel=.04):
    bpy.ops.mesh.primitive_cube_add(size=1,location=center)
    obj=bpy.context.object
    obj.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    obj['group']=material
    if bevel:
        mod=obj.modifiers.new('Stamped edge','BEVEL')
        mod.width=min(bevel,min(size)*.45)
        mod.segments=3
        obj.modifiers.new('Panel normals','WEIGHTED_NORMAL')
    return obj


def cylinder(center,radius,width,material):
    bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=radius,depth=width,
                                        rotation=(0,math.pi/2,0),location=center)
    obj=bpy.context.object
    obj['group']=material
    for polygon in obj.data.polygons:polygon.use_smooth=len(polygon.vertices)==4


def wheels(axles,halfwidth,radius,duals):
    for i,z in enumerate(axles):
        for side in (-1,1):
            x=side*(halfwidth-.12)
            cylinder((x,radius,z),radius,.26,RUBBER)
            if i in duals:cylinder((x-side*.27,radius,z),radius,.23,RUBBER)
            cylinder((x+side*.135,radius,z),radius*.65,.045,CHROME)
            cylinder((x+side*.166,radius,z),radius*.28,.06,RUBBER)
            for j in range(6):
                angle=j*math.tau/6
                cylinder((x+side*.17,radius+radius*.43*math.sin(angle),z+radius*.43*math.cos(angle)),.033,.025,CHROME)


def bake(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bus=name=='transit-bus'
    truck=name=='tractor-trailer'
    w=1.21 if bus or truck else .93
    end=7.64 if truck else 5.74 if bus else 2.24
    height=3.16 if bus or truck else 2.24
    box((0,.56,0),(w*1.8,.34,2*end-.3),RUBBER)
    if truck:
        box((0,2.42,-2.25),(2.5,2.68,11.05),WHITE,.1)
        for side in (-1,1):
            for z in range(-7,4):
                box((side*1.26,2.43,z),(.035,2.6,.04),CHROME)
            box((side*1.16,1.08,-2.25),(.16,.13,11.),CHROME)
            box((side*.57,2.4,-7.8),(1.09,2.47,.08),WHITE)
            box((side*.56,2.4,-7.86),(.04,2.27,.045),CHROME)
        box((0,1.8,4.64),(2.32,2.84,2.51),PAINT,.24)
        box((0,1.32,6.74),(1.85,1.02,1.80),PAINT,.23)
        cab_front=5.93
        wheels([6.55,3.38,2.16,-5.61,-6.82],w,.50,{1,2,3,4})
    else:
        box((0,(height+.42)/2,0),(2*w,height-.42,2*end),PAINT,.20)
        cab_front=end
        wheels([end*.66,-end*.65],w,.49 if bus else .34,{1} if bus else set())
        for side in (-1,1):
            for j in range(8 if bus else 1):
                z=end-.85-j*1.36
                box((side*w,height-.76,z),(.045,1.02 if bus else .77,1.24 if bus else 1.02),GLASS,.09)
            box((side*w,.90,0),(.04,.11,2*end-.46),WHITE)
        if bus:box((0,height+.13,-2.2),(1.55,.3,2.8),WHITE,.13)
    box((0,height-.74,cab_front),(w*1.78,.92 if bus or truck else .66,.07),GLASS,.085)
    if truck:
        for side in (-1,1):
            box((side*1.16,2.45,5.12),(.05,.78,1.05),GLASS)
            box((side*1.06,.81,4.5),(.48,.23,1.47),CHROME)
    box((0,.74,end),(2*w,.26,.14),CHROME)
    for n in range(5):box((0,.99+.072*n,end+.012),(w*1.04,.029,.07),CHROME)
    for side in (-1,1):
        box((side*w*.78,1.12,end+.035),(.30,.16,.08),HEAD)
        box((side*w*.8,.89,-end-.045),(.26,.17,.08),TAIL)
        box((side*(w+.13),height-.92,cab_front-.28),(.20,.34,.12),RUBBER)
        for j in range(3):box((side*(w+.02),.87,-end+.48+end*.76*j),(.04,.065,.105),AMBER)
    graph=bpy.context.evaluated_depsgraph_get()
    groups=[array('f') for _ in range(29)]
    for obj in bpy.context.scene.objects:
        evaluated=obj.evaluated_get(graph)
        mesh=evaluated.data
        mesh.calc_loop_triangles()
        rotation=obj.matrix_world.to_3x3()
        for tri in mesh.loop_triangles:
            for loop in tri.loops:
                vertex=mesh.vertices[mesh.loops[loop].vertex_index]
                normal=rotation @ mesh.corner_normals[loop].vector
                groups[obj['group']].extend((* (obj.matrix_world @ vertex.co), *normal.normalized()))
    blob=struct.pack('<29I',*(len(group)//6 for group in groups))+b''.join(group.tobytes() for group in groups)
    (OUTPUT/(name+'.zlib')).write_bytes(zlib.compress(blob,9))


for vehicle in ('tractor-trailer','transit-bus','delivery-van'):bake(vehicle)
