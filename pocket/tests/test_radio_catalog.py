# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import sys,json,tempfile,unittest,threading,time
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from radio_catalog import load,pack,page,fetch,PAGE
from device_connection import AttachedDevice

class CatalogTests(unittest.TestCase):
    def test_paged_complete_revision_and_corruption(self):
        catalog=dict(radio_snapshot=dict(complete=True,banks=[dict(index=1,channels=[dict(index=i,name='channel '+str(i),raw='ab'*100) for i in range(400)])]))
        raw,manifest=pack(catalog);seen=[]
        def exchange(request):
            seen.append(request);return page(raw,manifest,request['payload'])
        result=fetch(exchange,manifest)
        self.assertEqual(result['radio_snapshot'],catalog['radio_snapshot'])
        self.assertGreater(len(seen),1)
        self.assertTrue(all(len(page(raw,manifest,r['payload'])['chunk'])<=PAGE for r in seen))
        with self.assertRaisesRegex(ValueError,'checksum'):
            fetch(lambda request:dict(page(raw,manifest,request['payload']),chunk=b' '*len(page(raw,manifest,request['payload'])['chunk'])),manifest)
        with self.assertRaisesRegex(ValueError,'changed'):page(raw,manifest,dict(offset=0,revision='old'))

    def test_incomplete_backup_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name,data in [('2025',dict(complete=True,banks=[])),('2026',dict(complete=False))]:
                path=root/'backups'/name/'backup.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(data))
            def cached(path):return json.loads(path.read_text()) if path.exists() else None
            self.assertTrue(load(root,cached)['radio_snapshot']['complete'])

    def test_attachment_sync_async_and_only_on_revision_change(self):
        raw,manifest=pack(dict(radio_snapshot=dict(complete=True,banks=[dict(index=0,channels=[])])))
        calls=[];woke=threading.Event()
        def exchange(request):calls.append(request);return page(raw,manifest,request['payload'])
        source=AttachedDevice.__new__(AttachedDevice);source._init_saved_radio();source._wake=woke.set
        source.catalogue_provider=SimpleNamespace(transport=SimpleNamespace(exchange=exchange))
        try:
            self.assertEqual(source._saved_radio(dict(radio_catalog=manifest),time.time()),{})
            self.assertTrue(woke.wait(3))
            result=source._saved_radio(dict(radio_catalog=manifest),time.time())
            self.assertTrue(result['radio_snapshot']['complete'])
            count=len(calls)
            for _ in range(4):source._saved_radio(dict(radio_catalog=manifest),time.time())
            self.assertEqual(len(calls),count)
        finally:source._radio_pool.shutdown()

if __name__=='__main__':unittest.main()
