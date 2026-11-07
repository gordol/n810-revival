"""Exercise the actual C framing code against the host implementation."""
import ctypes as C
import importlib.util
from pathlib import Path
import random
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'host'))
from hub import Frame, Decoder, CompanionDecoder, crc16


class CFrame(C.Structure):
    _fields_ = [('service', C.c_uint8), ('op', C.c_uint8), ('id', C.c_uint16),
                ('len', C.c_uint16), ('data', C.c_uint8 * 512)]


class Parser(C.Structure):
    _fields_ = [('bytes', C.c_uint8 * 521), ('used', C.c_size_t),
                ('active', C.c_bool), ('escaped', C.c_bool), ('bad', C.c_bool)]


CB = C.CFUNCTYPE(None, C.POINTER(CFrame), C.c_void_p)


class ProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        binary = str(Path(cls.tmp.name)/'wire.dylib')
        subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC',
                        str(ROOT/'main/wire.c'), '-o', binary], check=True)
        cls.lib = C.CDLL(binary)
        cls.lib.hub_feed.argtypes = [C.POINTER(Parser), C.c_char_p, C.c_size_t, CB, C.c_void_p]
        cls.lib.hub_encode.argtypes = [C.POINTER(CFrame), C.c_void_p, C.c_size_t]
        cls.lib.hub_encode.restype = C.c_size_t

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def cdecode(self, chunks):
        out = []
        parser = Parser()
        @CB
        def receive(ptr, _):
            f = ptr.contents
            out.append(Frame(f.service, f.op, f.id, bytes(f.data[:f.len])))
        for chunk in chunks:
            self.lib.hub_feed(C.byref(parser), chunk, len(chunk), receive, None)
        return out

    def test_crc_known_vector(self):
        self.assertEqual(crc16(b'123456789'), 0x29b1)

    def test_cross_language_fragmentation_and_encoding(self):
        rng = random.Random(42)
        frames = [Frame(rng.randrange(4), rng.randrange(256), rng.randrange(65536), rng.randbytes(n))
                  for n in (0, 1, 19, 20, 172, 255, 512)]
        frames += [Frame(1, 1, 65535, b'~}'*256)]
        for f in frames:
            native = CFrame(f.service, f.op, f.id, len(f.data))
            native.data[:len(f.data)] = f.data
            output = C.create_string_buffer(1044)
            n = self.lib.hub_encode(C.byref(native), output, len(output))
            self.assertEqual(output.raw[:n], f.encode())
        stream = b'ROM boot noise\r\n' + b''.join(f.encode() for f in frames)
        for chunk_size in (1, 2, 7, 32, 513, 4096):
            chunks = [stream[n:n+chunk_size] for n in range(0, len(stream), chunk_size)]
            self.assertEqual(self.cdecode(chunks), frames)
            decoder = Decoder()
            self.assertEqual([f for chunk in chunks for f in decoder.feed(chunk)], frames)

    def test_corruption_truncation_and_oversize_recover(self):
        good = Frame(1, 1, 7, b'command')
        corrupted = bytearray(good.encode())
        corrupted[8] ^= 1
        stream = bytes(corrupted) + b'~' + b'x'*2048 + b'~' + good.encode()[:-4] + good.encode() + b'~abc}~' + good.encode()
        self.assertEqual(self.cdecode([stream]), [good, good])
        self.assertEqual(Decoder().feed(stream), [good, good])

    def test_companion_boundaries(self):
        commands = [b'\x16\x03', b'\x01'+b'\0'*7, b'~}'*200]
        stream = b''.join(b'<'+struct.pack('<H',len(p))+p for p in commands)
        decoder = CompanionDecoder()
        self.assertEqual([p for b in stream for p in decoder.feed(bytes([b]))], commands)
        with self.assertRaises(ValueError):
            CompanionDecoder().feed(b'<\xff\xff')
        with self.assertRaises(ValueError):
            CompanionDecoder().feed(b'bad')


if __name__ == '__main__':
    unittest.main()
