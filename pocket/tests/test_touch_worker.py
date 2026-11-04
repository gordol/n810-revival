"""Exercise stamped input across the real worker process boundary."""
from pathlib import Path
import select
import shutil
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace

SHELL=Path(__file__).resolve().parents[1]/'shell'
sys.path.insert(0,str(SHELL))
from pointer_events import PointerEvent,SourceStamp
from pointer_trace import PointerTrace
from touch_process import ProcessTouchSource
from runtime_codec import unpack

class TouchWorkerTests(unittest.TestCase):
    def test_stamped_press_move_release_cross_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            shutil.copyfile(SHELL/'pointer_events.py',root/'pointer_events.py')
            (root/'touch_evdev.py').write_text('''import os
from pointer_events import PointerEvent,SourceStamp
class TouchSource:
 def __init__(self,*args):
  self.r,self.w=os.pipe();os.write(self.w,b"x")
 def fileno(self):return self.r
 def drain(self):
  os.read(self.r,1)
  return [PointerEvent(("mouse",b,x,4,r),stamp=SourceStamp(100+i,"fixture")) for i,(b,x,r) in enumerate(((0,3,False),(32,4,False),(0,4,True)))]
 def diagnostics(self):return {}
 def close(self):os.close(self.r);os.close(self.w)
''')
            source=ProcessTouchSource('fixture','fixture',{},100,30,_source_root=root)
            events=[];deadline=time.monotonic()+20
            try:
                while len(events)<3 and time.monotonic()<deadline:
                    if select.select([source],[],[],1)[0]:events.extend(source.drain())
                self.assertEqual([tuple(e) for e in events],[('mouse',0,3,4,False),('mouse',32,4,4,False),('mouse',0,4,4,True)])
                self.assertEqual([e.stamp.ns for e in events],[100,101,102])
                self.assertIsNone(source.process.poll())
            finally:source.close();source.reaped.wait(3)

    def test_gesture_capture_stays_in_memory_until_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'trace.msgpack';trace=PointerTrace(path)
            trace.write(True);initial=path.read_bytes()
            event=PointerEvent(('mouse',32,3,4,False),stamp=SourceStamp(123,'fixture'))
            trace.received(SimpleNamespace(diagnostics=lambda:{}),[event])
            host=SimpleNamespace(damage=[],render_backend='native',render_reason=None,native_error=None,drag=['window',(),(1,2,30,10),False])
            trace.frame(host,(100,10),(130,20),(140,22),2,100,40)
            self.assertEqual(path.read_bytes(),initial)
            trace.close();data=unpack(path.read_bytes())
            self.assertEqual(data['events'][0]['source_events'][0]['stamp'],event.stamp._asdict())
            self.assertEqual(data['events'][1]['compose_cpu_ns'],10)
            self.assertEqual(data['events'][1]['output_stage_ns'],10)

    def test_trace_serializes_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'trace.msgpack';trace=PointerTrace(path)
            event=PointerEvent(('mouse',0,3,4,False),stamp=SourceStamp(123,'fixture'))
            trace.record(SimpleNamespace(focus='test',origin=(0,0)),SimpleNamespace(),event,3,4,80,'hit',{},True)
            trace.write(True)
            self.assertEqual(unpack(path.read_bytes())['events'][0]['source_stamp'],event.stamp._asdict())

if __name__=='__main__':unittest.main()
