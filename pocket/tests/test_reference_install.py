# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util,json,tempfile,unittest,hashlib
from pathlib import Path
spec=importlib.util.spec_from_file_location('reference_install',Path(__file__).resolve().parents[1]/'tools/install_reference_data.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ReferenceInstallTests(unittest.TestCase):
 def test_selected_files_verified_and_install_reuses_unchanged_files(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'source';source.mkdir();target=root/'target'
   for name in ('geography','hydrography','maps','fine'): (source/name).mkdir()
   for name in ('geography','hydrography'):(source/name/'index.json').write_text('{"tiles":{}}')
   (source/'maps/walk-layers.n8w').write_bytes(b'N8W1-fixture')
   raw=b'fictional-height-tile';(source/'fine/0-0.i16.zlib').write_bytes(raw)
   (source/'fine/index.json').write_text(json.dumps(dict(units='meters',tile_size=256,tiles={'0,0':dict(file='0-0.i16.zlib',sha256=hashlib.sha256(raw).hexdigest())})))
   (source/'elevation.json').write_text('{"version":1,"packs":["fine/index.json"]}')
   (source/'personal-key').write_text('excluded')
   files=m.inventory(source);m.install(files,target)
   self.assertFalse((target/'personal-key').exists())
   before=(target/'fine/0-0.i16.zlib').stat().st_mtime_ns
   m.install(files,target);self.assertEqual(before,(target/'fine/0-0.i16.zlib').stat().st_mtime_ns)
   (source/'fine/0-0.i16.zlib').write_bytes(b'corrupted')
   with self.assertRaisesRegex(ValueError,'checksum'):m.inventory(source)
   (target/'fine/0-0.i16.zlib').write_bytes(b'corrupted')
   with self.assertRaisesRegex(ValueError,'differs'):m.verify(target)
 def test_install_rejects_destination_symlink_escape(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);target=root/'target';target.mkdir();outside=root/'outside';outside.mkdir();(target/'maps').symlink_to(outside)
   src=root/'file';src.write_bytes(b'fixture')
   with self.assertRaisesRegex(ValueError,'escapes'):m.install({'maps/test':(src,dict(size=7,sha256=m.digest(src)))},target)
if __name__=='__main__':unittest.main()
