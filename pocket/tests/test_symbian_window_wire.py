import pathlib,sys,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'shell'))
from symbian_window_wire import *

class WindowWireTest(unittest.TestCase):
    def test_native_size_is_not_a_tile_contract(self):
        image=(0,0,240,320,2,240,320,1,123,7,0,960)
        encoded=packet(FRAME,9,240,320,[image])
        self.assertEqual(decode(encoded),(FRAME,9,240,320,(image,)))
    def test_current_tiling_stays_below_application(self):
        images=[]
        for y in range(0,320,128):
            for x in range(0,240,128):images.append((x,y,min(128,240-x),min(128,320-y),1,128,128,1,123,8,len(images),0))
        self.assertEqual(len(decode(packet(FRAME,1,240,320,images))[4]),6)
    def test_bad_coverage_and_tokens_rejected(self):
        image=(0,0,240,320,2,240,320,1,123,7,0,960)
        for changed in ((3,319),(8,0),(9,0),(10,14),(11,1)):
            bad=list(image);bad[changed[0]]=changed[1]
            with self.assertRaises(ValueError):packet(FRAME,1,240,320,[bad])
        with self.assertRaises(ValueError):packet(FRAME,1,240,320,[image,image])
        with self.assertRaises(ValueError):decode(packet(BEGIN,1)+b'x')
    def test_controls_cannot_carry_pixel_data(self):
        for kind in (BEGIN,READY,ACK,CLOSE,PAUSE,RESUME,ERROR):
            self.assertEqual(decode(packet(kind,99)),(kind,99,0,0,()))
            with self.assertRaises(ValueError):packet(kind,99,240,320)

if __name__=='__main__':unittest.main()
