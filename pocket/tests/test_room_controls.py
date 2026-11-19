from pathlib import Path
from types import SimpleNamespace
import sys,unittest
root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'graphics'),str(root/'shell'),str(root/'shell/apps/surface-renderer')]
from room_pixels import PixelRoom
class Call:
    def __init__(self):self.calls=[]
    def __call__(self,*args):self.calls.append(args);return 0
class RoomControls(unittest.TestCase):
    def test_normal_app_dispatch_controls_native_target_practice(self):
        room=object.__new__(PixelRoom);room._sync=lambda:True
        room.lib=SimpleNamespace(pocket_game_enable=Call(),pocket_game_fire=Call(),pocket_game_reset=Call())
        room.x=0.;room.eye_height=340.;room.z=0.;room.yaw=0.;room.pitch=0.;room.pixel_dirty=False
        self.assertTrue(room.key('G'));self.assertEqual(room.lib.pocket_game_enable.calls,[(1,)])
        self.assertTrue(room.key(' '));self.assertEqual(room.lib.pocket_game_fire.calls,[(0.,340.,0.,0.,0.)])
        self.assertTrue(room.key('r'));self.assertEqual(room.lib.pocket_game_reset.calls,[()])
        self.assertTrue(room.key('g'));self.assertEqual(room.lib.pocket_game_enable.calls,[(1,),(0,)])
        self.assertTrue(room.pixel_dirty)
if __name__=='__main__':unittest.main()
