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
