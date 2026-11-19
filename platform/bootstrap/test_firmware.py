"""Firmware acquisition and raw backup extraction, using fictional payloads."""
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zlib
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('firmware',HERE/'firmware.py');fw=importlib.util.module_from_spec(spec);spec.loader.exec_module(fw)

def crc(data):return (zlib.crc32(data,0xffffffff)^0xffffffff)&0xffffffff

def dirent(parent,ino,name,kind):
 name=name.encode();prefix=struct.pack('<HHI',0x1985,0xe001,40+len(name));header=prefix+struct.pack('<I',crc(prefix))
 body=header+struct.pack('<IIII4B',parent,1,ino,0,len(name),kind,0,0)
 return body+struct.pack('<II',crc(body),crc(name))+name

def inode(ino,data):
 prefix=struct.pack('<HHI',0x1985,0xe002,68+len(data));header=prefix+struct.pack('<I',crc(prefix))
 body=header+struct.pack('<IIIHHIIIIIIIBBH',ino,1,0o100644,0,0,len(data),0,0,0,0,len(data),len(data),0,0,0)
 return body+struct.pack('<II',crc(data),crc(body))+data

def fixture(payloads):
 nodes=[];ino=2
 for name,data in payloads.items():nodes.extend([dirent(1,ino,name,8),inode(ino,data)]);ino+=1
 return b''.join(n+b'\xff'*((-len(n))%4) for n in nodes)

class FirmwareTests(unittest.TestCase):
 def records(self):return {n:dict(sha256=fw.digest(v),url='https://example.invalid/'+n) for n,v in [('3826.arm',b'fictional wifi'),('bc4fw.bin',b'fictional bluetooth')]}
 def test_jffs2_backup_extracts_only_selected_files_without_network(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);backup=root/'backup';backup.mkdir()
   image=backup/'initfs.jffs2';image.write_bytes(fixture({'3826.arm':b'fictional wifi','bc4fw.bin':b'fictional bluetooth','private-message':b'secret fixture'}));before=image.read_bytes()
   with patch.object(fw.urllib.request,'urlopen',side_effect=AssertionError('network used')):
    report=fw.acquire(root/'out',root/'cache',backup,True,self.records())
   self.assertEqual(set(p.name for p in (root/'out').iterdir()),{'3826.arm','bc4fw.bin','FIRMWARE.json'})
   self.assertTrue(all(v['acquired_from']=='owner-backup' for v in report.values()));self.assertEqual(image.read_bytes(),before)
 def test_actual_maemo_directory_layout(self):
  with tempfile.TemporaryDirectory() as tmp:
   nodes=[dirent(1,2,'usr',4),dirent(2,3,'lib',4),dirent(3,4,'hotplug',4),dirent(4,5,'firmware',4),dirent(5,6,'3826.arm',8),inode(6,b'fictional wifi')]
   image=Path(tmp)/'initfs.jffs2';image.write_bytes(b''.join(n+b'\xff'*((-len(n))%4) for n in nodes))
   self.assertEqual(fw.from_jffs(image,['3826.arm']),{'3826.arm':b'fictional wifi'})

 def test_deleted_or_corrupt_jffs2_firmware_cannot_pass_pin(self):
  with tempfile.TemporaryDirectory() as tmp:
   image=Path(tmp)/'initfs.jffs2';raw=bytearray(fixture({'3826.arm':b'fictional wifi'}));raw[-4]^=1;image.write_bytes(raw)
   with self.assertRaises(ValueError):fw.from_jffs(image,['3826.arm'])
 def test_download_is_verified_cached_and_reused_offline(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);records=self.records();records={k:v for k,v in records.items() if k=='3826.arm'}
   class Response:
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def geturl(self):return 'https://example.invalid/3826.arm'
    def read(self,limit):return b'fictional wifi'
   with patch.object(fw.urllib.request,'urlopen',return_value=Response()) as download:
    fw.acquire(root/'first',root/'cache',records=records);download.assert_called_once()
   with patch.object(fw.urllib.request,'urlopen',side_effect=AssertionError('network used')):
    result=fw.acquire(root/'second',root/'cache',offline=True,records=records)
   self.assertEqual(result['3826.arm']['acquired_from'],'verified-cache')
 def test_truncated_owner_file_and_symlink_escape_are_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);backup=root/'backup';backup.mkdir();path=backup/'3826.arm';path.write_bytes(b'fictional')
   with self.assertRaises(ValueError):fw.acquire(root/'out',root/'cache',backup,True,self.records())
   path.unlink();outside=root/'outside';outside.write_bytes(b'fictional wifi');path.symlink_to(outside)
   with self.assertRaises(ValueError):fw.backup_files(backup)
 def test_missing_backup_fails_offline(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   with self.assertRaisesRegex(ValueError,'lacks required firmware'):fw.acquire(root/'out',root/'cache',offline=True,records=self.records())

if __name__=='__main__':unittest.main()
