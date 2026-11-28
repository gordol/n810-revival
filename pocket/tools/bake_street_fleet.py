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


def shell(sections, material):
    """Loft chamfered transverse sections in game coordinates."""
    verts=[]
    for z,w,b,t in sections:
        for x,y in ((-.94*w,b),(-w,b+.08),(-w,t-.10),(-.87*w,t),
                    (.87*w,t),(w,t-.10),(w,b+.08),(.94*w,b)):
            verts.append((x,y,z))
    faces=[tuple(reversed(range(8)))]
    for i in range(len(sections)-1):
        for j in range(8):
            a=8*i+j
            b=8*i+(j+1)%8
            faces.append((a,b,b+8,a+8))
    faces.append(tuple(range(len(verts)-8,len(verts))))
    mesh=bpy.data.meshes.new('Bodywork')
    mesh.from_pydata(verts,[],faces)
    mesh.update()
    obj=bpy.data.objects.new('Bodywork',mesh)
    bpy.context.collection.objects.link(obj)
    obj['group']=material
    mod=obj.modifiers.new('Pressed edges','BEVEL')
    mod.width=.034
    mod.segments=3
    obj.modifiers.new('Panel normals','WEIGHTED_NORMAL')


def passenger(name):
    utility=name=='crossover'
    roof=1.71 if utility else 1.46
    rear=-1.82 if utility else -1.56
    shell([(-2.18,.79,.42,.89),(-1.85,.91,.38,1.01),
           (1.18,.92,.36,.98),(1.95,.86,.42,.88),(2.19,.78,.45,.79)],PAINT)
    shell([(rear,.85,.91,1.07),(rear+.46,.76,.93,roof),
           (.40,.74,.93,roof),(1.20,.84,.92,1.04)],GLASS)
    box((0,roof,.5*(rear+.86)),(1.33,.08,.40-rear-.46),PAINT,.07)
    wheels([-1.37,1.35],.94,.33,set())
    for side in (-1,1):
        box((side*.81,(roof+.97)/2,-.34),(.09,roof-.96,.10),RUBBER)
        for z in (-.85,.34):
            box((side*.92,.86,z),(.035,.046,.16),CHROME)
        box((side*.94,1.07,.75),(.21,.115,.23),PAINT)
        box((side*.64,.76,2.13),(.34,.12,.13),HEAD,.04)
        box((side*.64,.83,-2.15),(.36,.14,.10),TAIL,.04)
    box((0,.61,2.18),(.83,.18,.06),RUBBER)
    box((0,.57,-2.19),(.38,.13,.04),WHITE)
    if name=='patrol':
        for side in (-1,1):
            box((side*.922,.69,-.10),(.036,.36,1.48),WHITE)
            box((side*.34,.65,2.23),(.06,.54,.09),RUBBER)
        box((0,.72,2.28),(.78,.065,.08),RUBBER)
        box((0,roof+.085,-.12),(1.14,.12,.25),RUBBER)
    if utility:
        for side in (-1,1):
            box((side*.61,roof+.07,-.47),(.06,.07,1.56),CHROME)


def pickup():
    shell([(-2.60,.91,.46,.96),(1.75,.99,.46,1.13),(2.59,.86,.53,1.03)],PAINT)
    for side in (-1,1):
        box((side*.91,1.13,-1.63),(.13,.43,1.92),PAINT)
        box((side*.70,.88,-2.56),(.20,.24,.08),TAIL)
        box((side*.72,.94,2.54),(.34,.14,.09),HEAD)
    box((0,1.10,-2.54),(1.84,.41,.11),PAINT)
    box((0,.99,-1.55),(1.65,.06,1.82),RUBBER)
    shell([(-.69,.91,1.01,1.36),(-.55,.81,1.01,1.86),
           (.61,.79,1.01,1.86),(1.35,.89,1.01,1.16)],GLASS)
    box((0,1.85,.03),(1.45,.09,1.17),PAINT)
    wheels([-1.72,1.64],1.,.40,set())


def electric():
    shell([(-2.21,.79,.42,.89),(-1.76,.91,.34,1.02),(.85,.91,.34,.95),(2.24,.78,.43,.71)],PAINT)
    shell([(-1.95,.79,.87,.96),(-1.12,.77,.91,1.37),(-.38,.72,.91,1.51),
           (.39,.72,.88,1.46),(1.42,.81,.83,.94)],GLASS)
    wheels([-1.39,1.39],.94,.34,set())
    for side in (-1,1):
        box((side*.65,.73,2.12),(.45,.05,.13),HEAD)
        box((side*.83,1.13,-.39),(.06,.46,.08),RUBBER)
        box((side*.88,.96,-.56),(.05,.05,.19),CHROME)
    box((0,.80,-2.18),(1.49,.05,.06),TAIL)


def motorbike():
    for z in (-.72,.70):
        cylinder((0,.30,z),.30,.15,RUBBER)
        cylinder((0,.30,z),.215,.16,CHROME)
        cylinder((0,.30,z),.15,.168,RUBBER)
    shell([(-.89,.12,.50,.67),(-.49,.19,.50,.76),(.14,.21,.39,.83),(.50,.16,.47,.83)],PAINT)
    box((0,.76,-.30),(.32,.09,.46),RUBBER)
    box((0,.48,.04),(.36,.27,.38),CHROME)
    for side in (-1,1):
        fork=box((side*.11,.54,.60),(.05,.53,.05),CHROME)
        fork.rotation_euler.x=-.29
    box((0,.94,.45),(.64,.05,.07),RUBBER)
    box((0,.78,.56),(.23,.16,.08),HEAD)
    box((0,.63,-.89),(.17,.07,.05),TAIL)


def bake(name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if name=='pickup':
        pickup()
        export(name)
        return
    if name=='electric':
        electric()
        export(name)
        return
    if name=='motorbike':
        motorbike()
        export(name)
        return
    if name in ('sedan','crossover','patrol'):
        passenger(name)
        export(name)
        return
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


def export(name):
    bpy.context.view_layer.update()
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


for vehicle in ('tractor-trailer','transit-bus','delivery-van','sedan','crossover','patrol','pickup','electric','motorbike'):bake(vehicle)
