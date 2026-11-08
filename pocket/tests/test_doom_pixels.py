"""Doom's graphical path validates its ABI before launch and bounds native writes."""
from pathlib import Path
import ctypes as C
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'graphics'),str(ROOT/'shell')]
from doom_pixels import Engine,engine_module

class DoomPixels(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temporary=tempfile.TemporaryDirectory(prefix='doom-bridge-test-')
  cls.addClassCleanup(cls.temporary.cleanup)
  output=Path(cls.temporary.name)/'bridge.so'
  subprocess.run(['cc','-std=c11','-shared','-fPIC',str(ROOT/'shell/apps/doom-app/bridge.c'),'-o',str(output)],check=True)
  cls.lib=C.CDLL(str(output));cls.lib.convert_pixels.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t]+[C.c_uint]*6
 def test_native_letterbox_colors_and_write_guards(self):
  frame=engine_module.Frame()
  for y in range(200):
   for x in range(320):frame.pixels[y*320+x]=0xff0000 if x<160 else 0x00ff00
  output=(C.c_uint16*40)(*([0x5aa5]*40))
  self.assertEqual(self.lib.convert_pixels(C.byref(frame),C.byref(output,8),32,8,4,2,1,4,2),0)
  self.assertEqual(list(output)[:4],[0x5aa5]*4);self.assertEqual(list(output)[-4:],[0x5aa5]*4)
  self.assertEqual(list(output)[4:12],[0]*8)
  self.assertEqual(list(output)[12:20],[0,0,0xf800,0xf800,0x07e0,0x07e0,0,0])
  before=list(output)
  for dimensions in [(8,4,7,1,2,2),(8,4,2,3,4,2),(4097,4,0,0,1,1),(8,4,0,0,0,1)]:
   self.assertEqual(self.lib.convert_pixels(C.byref(frame),C.byref(output,8),32,*dimensions),-1)
   self.assertEqual(list(output),before)
 def test_engine_input_stream_handles_partial_mouse_packets_and_keys(self):
  source=ROOT/'shell/apps/doom-app';headers=source/'vendor/doomgeneric/doomgeneric'
  directory=Path(self.temporary.name);obj=directory/'engine-input.o';test=directory/'input.c';binary=directory/'input-test'
  test.write_text(r'''#include "doomgeneric.h"
#include "d_event.h"
#include <assert.h>
#include <unistd.h>
#include <fcntl.h>
pixel_t *DG_ScreenBuffer;
void doomgeneric_Create(int n,char **v){(void)n;(void)v;}
void doomgeneric_Tick(void){}
static event_t last;static int events;
void D_PostEvent(event_t *e){last=*e;events++;}
int main(void){
 int f[2],pressed;unsigned char key;assert(!pipe(f));assert(dup2(f[0],0)==0);fcntl(0,F_SETFL,O_NONBLOCK);
 const unsigned char head[]={2,1},tail[]={8,0,253,255};
 assert(write(f[1],head,2)==2);assert(!DG_GetKey(&pressed,&key)&&events==0);
 assert(write(f[1],tail,4)==4);assert(!DG_GetKey(&pressed,&key));
 assert(events==1&&last.type==ev_mouse&&last.data1==1&&last.data2==8&&last.data3==-3);
 const unsigned char drag_release[]={2,1,10,0,0,0,2,0,0,0,0,0};
 assert(write(f[1],drag_release,sizeof(drag_release))==sizeof(drag_release));assert(!DG_GetKey(&pressed,&key));
 assert(events==2&&last.data1==0&&last.data2==10);
 const unsigned char keys[]={1,'w',0,'w'};assert(write(f[1],keys,4)==4);
 assert(DG_GetKey(&pressed,&key)&&pressed==1&&key=='w');assert(DG_GetKey(&pressed,&key)&&pressed==0&&key=='w');
 return 0;
}
''')
  subprocess.run(['cc','-std=c11','-DENGINE','-Dmain=bridge_main','-I'+str(headers),'-c',str(source/'bridge.c'),'-o',str(obj)],check=True)
  subprocess.run(['cc','-std=c11','-I'+str(headers),str(test),str(obj),'-o',str(binary)],check=True)
  subprocess.run([str(binary)],check=True,timeout=5)
 def test_old_bridge_rejected_before_process_or_frame_allocation(self):
  class Symbol:
   def __call__(self):return C.sizeof(engine_module.Frame)
  class OldBridge:
   bridge_now_ns=Symbol();frame_size=Symbol();snapshot=Symbol();convert=Symbol()
  with tempfile.TemporaryDirectory() as state,patch('ctypes.CDLL',return_value=OldBridge()),patch.object(engine_module.subprocess,'Popen') as spawn:
   with self.assertRaisesRegex(ValueError,'make doom'):Engine(None,Path(state),resource_root=Path(state))
   spawn.assert_not_called();self.assertEqual(list(Path(state).iterdir()),[])

if __name__=='__main__':unittest.main()
