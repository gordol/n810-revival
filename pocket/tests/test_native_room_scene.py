# SPDX-License-Identifier: GPL-2.0-or-later
"""Shared native scene admission, retained lifetime, and failure boundaries."""
from pathlib import Path
from types import SimpleNamespace as NS
import ctypes as C,sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'graphics'))
from gpu_scene import Context
from scenes import RoomScene
class Call:
 def __init__(self,result):self.result=result;self.calls=[]
 def __call__(self,*args):self.calls.append(args);return self.result
class NativeRoom(unittest.TestCase):
 def setUp(self):
  self.ctx=object.__new__(Context);self.ctx.handle=1;self.ctx.images={};self.ctx.native_room=True;self.ctx.room_binding=None
  self.ctx.lib=NS(pocket_scene_room=Call(4),pocket_scene_room_create=Call(20),pocket_scene_room_source=Call(0),pocket_scene_image=Call(0))
  self.released=[];self.ctx.release=self.released.append
  self.callback=C.CFUNCTYPE(C.c_int)(lambda:0)
  self.scene=RoomScene(.75,20,0,.08,.03,340,320,200)
  self.app=NS(name='Room',lib=NS(pocket_room_draw_tile=self.callback,pocket_room_set_eye_height=self.callback),stats={},pixel_frames=0,pixel_jobs=0,pixel_dirty=True,render_scene=lambda:(self.scene,8,16))
 def test_retains_target_and_reuses_unchanged_frame(self):
  self.assertEqual(self.ctx.native_scene(self.app),(8,16,320,200));self.ctx.native_scene(self.app)
  self.assertEqual(len(self.ctx.lib.pocket_scene_room_create.calls),1);self.assertEqual(len(self.ctx.lib.pocket_scene_room.calls),1)
  self.assertEqual(len(self.ctx.lib.pocket_scene_image.calls),2);self.assertEqual(len(self.ctx.lib.pocket_scene_room_source.calls),1)
  self.scene=RoomScene(.9,20,0,.08,.03,340,320,200);self.ctx.native_scene(self.app)
  self.assertEqual(len(self.ctx.lib.pocket_scene_room_create.calls),1);self.assertEqual(self.app.pixel_frames,2);self.assertFalse(self.released)
 def test_resize_replaces_only_after_success(self):
  self.ctx.native_scene(self.app);self.ctx.lib.pocket_scene_room_create.result=21
  self.scene=RoomScene(.9,20,0,.08,.03,340,400,256);self.ctx.lib.pocket_scene_room.result=-1
  with self.assertRaises(RuntimeError):self.ctx.native_scene(self.app)
  self.assertEqual(self.released,[21]);self.assertEqual(self.ctx.images['Room'][1],20);self.assertEqual(self.app.pixel_frames,1)
 def test_missing_backend_keeps_explicit_image_path(self):
  self.ctx.native_room=False;self.app.render_scene=lambda:(_ for _ in ()).throw(AssertionError('producer called'))
  self.assertIsNone(self.ctx.native_scene(self.app));self.assertFalse(self.ctx.lib.pocket_scene_room.calls)
 def test_session_does_not_swap_producer(self):
  self.ctx.native_scene(self.app);other=C.CFUNCTYPE(C.c_int)(lambda:0);self.app.lib.pocket_room_draw_tile=other
  with self.assertRaisesRegex(RuntimeError,'changed within'):self.ctx.native_scene(self.app)
if __name__=='__main__':unittest.main()
