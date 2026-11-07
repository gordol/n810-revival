"""Synthetic CAL/JFFS2 corruption and reconstruction checks; no device inputs."""
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
import zlib

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
cal = load('n810-cal-inspect')
jffs = load('n810-jffs2-extract')

def record(payload, version=1):
    header = cal.HEADER.pack(b'ConF', 2, version, 0, b'synthetic-test', len(payload), cal.cal_crc32(payload), 0)
    return header[:-4] + struct.pack('<I', cal.cal_crc32(header[:-4])) + payload

class ReaderTests(unittest.TestCase):
    def test_cal_valid_versions_and_corrupt_payload(self):
        first, second = record(b'old'), record(b'new', 2)
        rows = cal.scan(first + b'\xff' * 13 + second)
        self.assertEqual([r['version'] for r in rows], [1, 2])
        self.assertTrue(all(r['header_crc_ok'] and r['data_crc_ok'] for r in rows))
        bad = cal.scan(second[:-1] + b'!')[0]
        self.assertTrue(bad['header_crc_ok'])
        self.assertFalse(bad['data_crc_ok'])

    def test_cal_truncation_and_header_crc(self):
        raw = record(b'example')
        self.assertEqual(cal.scan(raw[:-1]), [])
        bad = bytearray(raw); bad[8] ^= 1
        self.assertFalse(cal.scan(bytes(bad))[0]['header_crc_ok'])

    def test_jffs_newer_fragments_and_truncation(self):
        def node(version, offset, payload, size):
            return dict(version=version, physical=version*4, offset=offset,
                        payload=payload, isize=size, dsize=len(payload), compr=0)
        self.assertEqual(jffs.reconstruct([node(1,0,b'old contents',12), node(2,0,b'NEW',5)]), b'NEW c')

    def test_jffs_deleted_directory_entry(self):
        entries={(1,b'kept'):(1,2,8,0), (1,b'deleted'):(2,0,8,4)}
        self.assertEqual([p[0] for p in jffs.live_paths(entries)], [b'/kept'])

    def test_jffs_compression_and_unsupported_input(self):
        text=b'hello'*20
        self.assertEqual(jffs.decompress(6,zlib.compress(text),len(text)),text)
        self.assertEqual(jffs.decompress(1,b'',7),b'\0'*7)
        self.assertEqual(jffs.rtime_decompress(b'a\0b\0',2),b'ab')
        with self.assertRaises(ValueError):jffs.decompress(99,b'',0)

    def test_oob_preservation_and_short_page(self):
        with tempfile.TemporaryDirectory() as d:
            source,target=Path(d)/'raw',Path(d)/'data'
            raw=b'abcdXYefghZZ';source.write_bytes(raw)
            jffs.strip_oob(source,target,page=4,oob=2)
            self.assertEqual(target.read_bytes(),b'abcdefgh')
            self.assertEqual(source.read_bytes(),raw)
            source.write_bytes(b'abc')
            with self.assertRaises(ValueError):jffs.strip_oob(source,target,page=4,oob=2)

if __name__=='__main__':unittest.main()
