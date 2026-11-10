import os,pathlib,socket,struct,sys,unittest
from types import SimpleNamespace
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'shell'),str(ROOT/'graphics')]
from symbian_pixels import View
from symbian_window_wire import *

@unittest.skipUnless(sys.platform=="linux", "Linux window descriptor transport")
class WindowTest(unittest.TestCase):
    def setUp(self):
        self.producer,frames=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        self.control,control=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
        self.reader,keyboard=os.pipe();os.set_blocking(self.reader,False)
        host=SimpleNamespace(bounds=lambda w:(2,3,32,22),window=lambda name:None,origin=(0,0),invalidate=lambda bounds:None,close=lambda name:None)
        self.view=View(host,'Snakes',frames,keyboard,control);self.retired=[]
        self.context=SimpleNamespace(retire_retained=lambda name,**options:self.retired.append(name))
    def tearDown(self):
        self.view.close();self.producer.close();self.control.close();os.close(self.reader)
    def message(self,kind,serial=1,*args):
        self.producer.sendall(packet(kind,serial,*args));self.view.receive()
    def test_publication_requires_retire_then_present_ack(self):
        self.message(BEGIN)
        self.assertTrue(self.view.prepare_gpu(self.context))
        self.assertEqual(self.retired,['Snakes']);self.assertEqual(decode(self.producer.recv(MAX_PACKET))[:2],(READY,1))
        image=(0,0,240,320,2,240,320,1,99,7,0,960)
        self.message(FRAME,1,240,320,[image])
        self.assertTrue(self.view.prepare_gpu(self.context))
        frame,x,y,w,h=self.view.render_retained();self.assertEqual((x,y,w,h),(24,64,240,320))
        self.producer.setblocking(False)
        with self.assertRaises(BlockingIOError):self.producer.recv(MAX_PACKET)
        self.view.frame_presented();self.assertEqual(decode(self.producer.recv(MAX_PACKET))[:2],(ACK,1))
        self.assertEqual(self.view.pixel_frames,1)
        self.message(BEGIN,2);self.assertFalse(self.view.prepare_gpu(self.context));self.assertIsNone(self.view.frame)
    def test_focus_cancel_releases_held_keys(self):
        self.view.key_event('left','press');self.view.cancel_keys()
        data=os.read(self.reader,256)
        self.assertEqual([struct.unpack_from('<iiHHi',data,i)[3:] for i in range(0,len(data),16)],[(105,1),(105,0)])
    def test_guest_owns_repeat_timer(self):
        self.view.key_event('down','press')
        for _ in range(8):self.view.key_event('down','repeat')
        self.view.key_event('down','release')
        data=os.read(self.reader,1024)
        self.assertEqual([struct.unpack_from('<iiHHi',data,i)[3:] for i in range(0,len(data),16)],[(108,1),(108,0)])
    def test_unrequested_frame_is_rejected(self):
        image=(0,0,240,320,2,240,320,1,99,7,0,960)
        with self.assertRaises(ValueError):self.message(FRAME,1,240,320,[image])
    def test_producer_close_forgets_before_retirement_ack(self):
        self.view.context=self.context;self.view.serial=4;self.view.phase='displayed'
        self.message(CLOSE,4)
        self.assertEqual(self.retired,['Snakes','Snakes'])
        self.assertEqual(self.control.recv(8),b'F')
        self.assertEqual(decode(self.producer.recv(MAX_PACKET))[:2],(READY,4))
        self.assertTrue(self.view.closed)
    def test_close_retires_before_broker_stop(self):
        self.view.context=self.context;self.view.close()
        self.assertEqual(self.retired,['Snakes']);self.assertEqual(self.control.recv(1),b'C')
        self.assertEqual(self.view.readiness_sources(),())

class RetainedAllocationTest(unittest.TestCase):
    def test_new_generation_reuses_consumer_storage(self):
        from gpu_scene import Context
        from symbian_pixels import Frame
        class Function:
            def __init__(self,result):self.result=result;self.calls=[]
            def __call__(self,*args):self.calls.append(args);return self.result
        names={'pocket_scene_retained_supported':1,'pocket_scene_retained':100,'pocket_scene_retained_forget':0,'pocket_scene_retained_rebind':0,'pocket_scene_retained_draw':0,'pocket_scene_texture_free':None}
        lib=SimpleNamespace(**{name:Function(result) for name,result in names.items()})
        context=Context.__new__(Context);context.lib=lib;context.handle=1
        context.images={};context.retained_handles=set();context.retained_idle={}
        context.check=lambda value:self.assertEqual(value,0)
        image=(0,0,240,320,2,240,320,1,99,1,0,960)
        app=SimpleNamespace(name='Snakes',frame=Frame(1,240,320,(image,)))
        app.render_retained=lambda:(app.frame,24,32,240,320)
        context.retained_scene(app);context.retire_retained('Snakes',keep=True)
        next_image=(*image[:9],2,*image[10:]);app.frame=Frame(2,240,320,(next_image,))
        context.retained_scene(app)
        self.assertEqual(len(lib.pocket_scene_retained.calls),1)
        self.assertEqual(len(lib.pocket_scene_retained_rebind.calls),1)
        self.assertEqual(len(lib.pocket_scene_texture_free.calls),0)
        context.retire_retained('Snakes')
        self.assertEqual(len(lib.pocket_scene_texture_free.calls),1)

if __name__=='__main__':unittest.main()
