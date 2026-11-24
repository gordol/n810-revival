"""World-space touch navigation, wildlife picking and clean PNG storage."""
import os
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'graphics'),str(root/'shell')]
from river_explore import ground_target, photo_paths, read_photo, save_photo, sighting, walk_to


class RiverExplorationTests(unittest.TestCase):
    camera=(0,1,0,0,0)

    def test_route_stops_on_near_bank(self):
        target=ground_target(self.camera,.5,.7,1,lambda x,z:0,lambda x,z:z>2.5)
        self.assertTrue(2<target[1]<2.5)
        owner=SimpleNamespace(x=0,z=0,yaw=0)
        while target is not None:target=walk_to(owner,target,.1)
        self.assertTrue(2<owner.z<2.5)
        self.assertIsNone(ground_target(self.camera,.5,.25,1,lambda x,z:0,lambda x,z:z>2.5))

    def test_waypoint_keeps_moving_while_looking_elsewhere(self):
        owner=SimpleNamespace(x=0,z=0,yaw=-1.4)
        walk_to(owner,(0,12),.1,face_path=False)
        self.assertGreater(owner.z,0)
        self.assertEqual(owner.yaw,-1.4)

    def test_visible_subject_at_tap(self):
        animals=[('behind',0,1,-2,.5),('near',0,1,5,.5),('far',0,1,16,.5)]
        self.assertEqual(sighting(self.camera,.5,.5,1,animals,lambda x,z:0),'near')
        self.assertIsNone(sighting(self.camera,.9,.2,1,animals,lambda x,z:0))
        self.assertIsNone(sighting(self.camera,.5,.5,1,animals,lambda x,z:2))

    def test_png_scanlines_keep_orientation(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,XDG_DATA_HOME=temp):
            rgb=bytes([255,0,0,0,0,255])
            path=save_photo('trout',1,2,rgb)
            self.assertEqual(photo_paths(),[path])
            self.assertEqual(read_photo(path),(1,2,rgb))
            image=path.read_bytes()
            offset=image.index(b'IDAT')
            size=struct.unpack('>I',image[offset-4:offset])[0]
            self.assertEqual(zlib.decompress(image[offset+4:offset+4+size]),bytes([0,255,0,0,0,0,0,255]))

    def test_private_discovery_pages_survive_reopening(self):
        sys.path[:0]=[str(root/'shell/apps/surface-renderer'),str(root/'shell/apps/landscape-lab')]
        from river_notebook import DiscoveryBook,record_plant
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,XDG_DATA_HOME=temp):
            view=SimpleNamespace(name='Rainier walk',host=SimpleNamespace(window=lambda _:SimpleNamespace(w=42,h=24)))
            record_plant('blueberry');record_plant('blueberry')
            for _ in range(2):save_photo('trout',1,1,bytes(3))
            book=DiscoveryBook(view)
            self.assertEqual({e[1] for e in book.entries},{'trout','blueberry'})
            book.page=next(i for i,e in enumerate(book.entries) if e[1]=='trout')
            from river_overlay import book_layout,tools,hit
            for width,height in ((20,9),(40,21),(90,32)):
                page,buttons=book_layout(width,height)
                for _,_,box in buttons+tools(width,height,True):
                    x,y,w,h=box
                    self.assertGreaterEqual(h,2)
                    self.assertTrue(hit(box,x+w-.01,y+h-.01))
                    self.assertLessEqual(x+w,width);self.assertLessEqual(y+h,height)
            self.assertFalse(book.tap_xy(2,3))
            self.assertEqual(len(view.album),2)
