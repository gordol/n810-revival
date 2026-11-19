import gzip
import hashlib
import struct
import tempfile
import unittest
from pathlib import Path
from write_macos_internal import CAPACITY, OFFSET, image_blocks, validate_disk


class MacWriterTests(unittest.TestCase):
    def test_refuses_wrong_or_original_usb_port_and_non_n810_disks(self):
        info = dict(DeviceNode='/dev/disk5', MediaName='N810', BusProtocol='USB',
                    Internal=False, WholeDisk=True, TotalSize=CAPACITY,
                    DeviceBlockSize=512, Writable=True, VirtualOrPhysical='Physical',
                    DeviceTreePath='IODeviceTree:/usb/port@02100000')
        validate_disk(info, '/dev/disk5', 0x02100000)
        for key, value in [('DeviceTreePath', 'IODeviceTree:/usb/port@00100000'),
                           ('Internal', True), ('TotalSize', 31 * 1024**3),
                           ('MediaName', 'SD Card'), ('WholeDisk', False),
                           ('VirtualOrPhysical', 'Virtual')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_disk(dict(info, **{key: value}), '/dev/disk5', 0x02100000)

    def test_disk_layout_payload_and_tail_clear(self):
        payload = b'test' * 1024
        manifest = dict(disk_id='12345678', root_bytes=len(payload),
                        root_sha256=hashlib.sha256(payload).hexdigest())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'root.gz'
            path.write_bytes(gzip.compress(payload))
            size = 4 * 1024**2
            image = b''.join(image_blocks(manifest, path, size))
            self.assertEqual(len(image), size)
            self.assertEqual(image[OFFSET:OFFSET + len(payload)], payload)
            self.assertEqual(image[OFFSET + len(payload):], bytes(size - OFFSET - len(payload)))
            self.assertEqual(struct.unpack_from('<I', image, 440)[0], 0x12345678)
            self.assertEqual(struct.unpack_from('<II', image, 454), (2048, size // 512 - 2048))
            self.assertEqual(image[510:512], b'\x55\xaa')
            path.write_bytes(gzip.compress(payload[:-512]))
            with self.assertRaises(ValueError):
                list(image_blocks(manifest, path, size))


if __name__ == '__main__':
    unittest.main()
