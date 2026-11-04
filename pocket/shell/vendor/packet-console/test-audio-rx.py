import array
import ast
import base64
import ctypes as c
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import socket
import subprocess
import tempfile
import threading
import time
import unittest

spec=importlib.util.spec_from_file_location('audio_rx',Path(__file__).with_name('n810-audio-rx.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)


def frame(payload,kind=0):
    raw=bytes([kind])+payload
    return b'~'+raw.replace(b'}',b'}]') .replace(b'~',b'}^')+b'~'


def fake_sbc():return bytes([0x9c,0x71,32,0])+bytes(68) #32k,16blocks,mono,8subbands,72bytes


class FakeDecoder:
    def decode(self,raw):return array.array('h',[1000]*128).tobytes()
    def reset(self):pass


class Tests(unittest.TestCase):
    def test_incremental_vendor_framing_escaping_and_bounds(self):
        parser=a.AudioFrames();wire=frame(b'abc~}',3);out=[]
        for value in wire:out+=parser.feed(bytes([value]))
        self.assertEqual(out,[(3,b'abc~}')])
        parser.feed(b'~\0'+b'x'*65537);self.assertGreater(parser.dropped,0)
        self.assertLessEqual(len(parser.data),65536)
    def test_probe_native_rate_and_output_not_forced_to8k(self):
        info=a.sbc_header(fake_sbc());self.assertEqual((info['rate'],info['samples'],info['size']),(32000,128,72))
        events=[];pipeline=a.Pipeline(FakeDecoder(),events.append,'fixture-radio')
        for _ in range(5):pipeline.feed(frame(fake_sbc()),1000000000)
        pcm=[e for e in events if e['type']=='pcm'];self.assertEqual(len(pcm),1)
        self.assertEqual(pcm[0]['sample_rate'],32000);self.assertEqual(pcm[0]['sample_count'],640)
        self.assertEqual(len(base64.b64decode(pcm[0]['pcm_b64'])),1280)
        self.assertIsNone(pcm[0]['capture_monotonic_ns']);self.assertFalse(pcm[0]['capture_time_known'])
    def test_tx_echo_ignored_and_audio_end_resets_segment(self):
        events=[];pipeline=a.Pipeline(FakeDecoder(),events.append,'fixture-radio');before=pipeline.stream
        pipeline.feed(frame(fake_sbc(),9));self.assertEqual(pipeline.tx_echo_frames,1)
        self.assertFalse(any(e['type']=='pcm' for e in events))
        pipeline.feed(frame(b'',1));self.assertNotEqual(pipeline.stream,before)
    def test_encoded_then_one_decoder_pcm_same_source(self):
        encoded=[];receiver=a.Pipeline(None,encoded.append,'fixture-radio')
        for i in range(5):receiver.feed(frame(fake_sbc()),1000000000+i*4000000)
        output=[];decoder=a.Pipeline(FakeDecoder(),output.append,'fixture-radio');reader=a.EncodedInput(decoder)
        reader.feed(b''.join(json.dumps(e).encode()+b'\n' for e in encoded))
        pcm=[e for e in output if e['type']=='pcm'];self.assertEqual(len(pcm),1)
        self.assertEqual(pcm[0]['source_stream_id'],receiver.stream)
        self.assertEqual(pcm[0]['sample_rate'],32000)
        event=next(e for e in encoded if e['type']=='sbc');event=dict(event,sequence=999,first_sample=999)
        reader.feed(json.dumps(event).encode()+b'\n')
        self.assertTrue(any(e['type']=='gap' and e['reason']=='source_reset_or_gap' for e in output))
    def test_audio_socket_has_no_send_paths(self):
        tree=ast.parse(Path(a.__file__).read_text())
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name):
                self.assertFalse(node.func.value.id=='radio' and node.func.attr in ('send','sendall','sendto'))
        self.assertNotIn('AudioConnection',Path(a.__file__).read_text())
    @unittest.skipUnless(os.environ.get('N810_AUDIO_TEST_LIBSBC'),'Optional local real-codec library not provided')
    def test_actual_decoder_unix_fanout_without_audio_files(self):
        path=os.environ['N810_AUDIO_TEST_LIBSBC'];decoder=a.Decoder(path);lib=decoder.lib;encoder=a.SBCState()
        self.assertEqual(lib.sbc_init(c.byref(encoder),0),0)
        encoder.frequency=1;encoder.blocks=3;encoder.subbands=1;encoder.mode=0;encoder.bitpool=32;encoder.endian=0
        lib.sbc_encode.argtypes=[c.POINTER(a.SBCState),c.c_void_p,c.c_size_t,c.c_void_p,c.c_size_t,c.POINTER(c.c_ssize_t)];lib.sbc_encode.restype=c.c_ssize_t
        raw=array.array('h',[round(12000*math.sin(2*math.pi*1000*i/32000)) for i in range(128)]).tobytes()
        output=c.create_string_buffer(1024);written=c.c_ssize_t()
        try:
            lib.sbc_encode(c.byref(encoder),raw,len(raw),output,len(output),c.byref(written));sbc=output.raw[:written.value]
        finally:lib.sbc_finish(c.byref(encoder));decoder.close()
        with tempfile.TemporaryDirectory(prefix='arx-',dir='/tmp') as folder:
            source=Path(folder)/'src';target=Path(folder)/'pcm';listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(source));listener.listen(1)
            errors=[]
            def serve():
                try:
                    peer,_=listener.accept()
                    with peer:
                        events=[];pipeline=a.Pipeline(None,events.append,'fixture-only')
                        for i in range(100):
                            pipeline.feed(frame(sbc),1000000000+i*4000000)
                            while events:peer.sendall(json.dumps(events.pop(0)).encode()+b'\n')
                            time.sleep(.004)
                except OSError as exc:errors.append(str(exc))
            thread=threading.Thread(target=serve,daemon=True);thread.start()
            process=subprocess.Popen([sys.executable,a.__file__,'--wait-for-consumer','--input-socket',str(source),'--socket',str(target),'--duration','2','--receiver-id','fixture-only','--libsbc',path],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                end=time.monotonic()+3
                while not target.exists() and time.monotonic()<end:time.sleep(.01)
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
                    client.settimeout(3);client.connect(str(target));pending=b'';found=None
                    while found is None:
                        data=client.recv(8192)
                        if not data:break
                        pending+=data
                        while b'\n' in pending:
                            line,_,pending=pending.partition(b'\n');event=json.loads(line)
                            if event['type']=='pcm':found=event;break
                stdout,stderr=process.communicate(timeout=4)
                self.assertEqual(process.returncode,0,stderr);self.assertIsNotNone(found)
                self.assertEqual((found['sample_rate'],found['sample_count']),(32000,640))
                self.assertGreater(json.loads(stdout)['decoded_samples'],0)
                self.assertEqual(set(p.name for p in Path(folder).iterdir()),{'src'})
            finally:
                if process.poll() is None:process.kill();process.wait()
                listener.close();thread.join(timeout=1)

    @unittest.skipUnless(os.environ.get('N810_AUDIO_TEST_LIBSBC'),'Optional local real-codec library not provided')
    def test_actual_libsbc_roundtrip(self):
        path=os.environ['N810_AUDIO_TEST_LIBSBC'];decoder=a.Decoder(path);lib=decoder.lib;encoder=a.SBCState()
        self.assertEqual(lib.sbc_init(c.byref(encoder),0),0)
        encoder.frequency=1;encoder.blocks=3;encoder.subbands=1;encoder.mode=0;encoder.bitpool=32;encoder.endian=0
        lib.sbc_encode.argtypes=[c.POINTER(a.SBCState),c.c_void_p,c.c_size_t,c.c_void_p,c.c_size_t,c.POINTER(c.c_ssize_t)];lib.sbc_encode.restype=c.c_ssize_t
        raw=array.array('h',[round(12000*math.sin(2*math.pi*1000*i/32000)) for i in range(128)]).tobytes()
        output=c.create_string_buffer(1024);written=c.c_ssize_t()
        try:
            self.assertEqual(lib.sbc_encode(c.byref(encoder),raw,len(raw),output,len(output),c.byref(written)),256)
            sbc=output.raw[:written.value];self.assertEqual(a.sbc_header(sbc)['rate'],32000)
            result=decoder.decode(sbc);self.assertEqual(len(result),256)
            values=array.array('h');values.frombytes(result)
            self.assertGreater(max(abs(v) for v in values),100)
        finally:lib.sbc_finish(c.byref(encoder));decoder.close()


if __name__=='__main__':unittest.main()
