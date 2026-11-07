"""Disk retention, bounded keyset pages and asynchronous Feed browsing."""
from pathlib import Path
import sys,tempfile,unittest,time,threading,sqlite3
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from device_retained import owner
from native_feed import RadioFeed
h=owner('n810-frame-history.py')
def record(i):
 return dict(time='2026-10-29T12:%02d:%02d+00:00'%(i//60,i%60),direction='radio_to_host',frame=(b'\0packet'+str(i).encode()).hex())
class ArchiveTests(unittest.TestCase):
 def test_scroll_requests_beyond_live_buffer_and_catalogue_changes_device(self):
  from native_catalog import Catalog
  from types import SimpleNamespace
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'archive.sqlite3';archive=h.Archive(path)
   for i in range(320):archive.add(record(i))
   archive.close()
   calls=[]
   def page(before=None,anchor=None):
    calls.append((before,anchor));return h.page(before,path=path,anchor=anchor)
   connection=SimpleNamespace(source=object(),history_page=page)
   state=SimpleNamespace(source=connection,payload={'live':{'raw_records':[record(i) for i in range(120,320)]}},error=None)
   catalog=Catalog(state);catalog.update()
   form=RadioFeed(catalog.feed_view);self.addCleanup(form.close);form.update()
   self.assertEqual(len(form.rows),200)
   form.list.index=len(form.rows)-1;form.choose();form.action('list.next')
   form._history_pending.result(3);form.update()
   self.assertGreater(len(form.rows),200);self.assertEqual(calls[0][1],record(120))
   for _ in range(10):
    if not form._history_more:break
    form.action('feed.older');form._history_pending.result(3);form.update()
   self.assertEqual(len(form.rows),320);self.assertFalse(form._history_more)
   connection.source=object();catalog.update();form.update()
   self.assertEqual(len(form.rows),200);self.assertIsNone(form._history_cursor)

 def test_pages_survive_restart_preserve_bytes_and_dont_overlap(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'packets.sqlite3'
   with patch.dict('os.environ',{'POCKET_RX_HISTORY_RECORDS':'3','POCKET_RX_ARCHIVE_RECORDS':'20','POCKET_RX_PAGE_RECORDS':'4'}):
    archive=h.Archive(path);history=h.History();history.archive=archive
    rows=[record(i) for i in range(12)]
    rows[3].update(origin='vendor_reassembled',wire_frames=['ff01000000020039'])
    for row in rows:history.add(row)
    self.assertEqual(list(history.records),rows[-3:]);archive.close()
    first=h.page(path=path,anchor=rows[-3]);self.assertEqual(first['records'],list(reversed(rows[5:9])))
    second=h.page(first['before'],path=path);third=h.page(second['before'],path=path)
    self.assertEqual(first['records']+second['records']+third['records'],list(reversed(rows[:9])))
    self.assertFalse(third['more']);self.assertEqual(path.stat().st_mode&0o777,0o600)
    archive=h.Archive(path);archive.add(record(12));archive.close()
    self.assertEqual(h.page(path=path)['records'][0],record(12))
 def test_retention_and_bad_settings(self):
  with tempfile.TemporaryDirectory() as root,patch.dict('os.environ',{'POCKET_RX_ARCHIVE_RECORDS':'5','POCKET_RX_PAGE_RECORDS':'3'}):
   path=Path(root)/'packets.sqlite3';archive=h.Archive(path)
   for i in range(20):archive.add(record(i))
   archive.close();first=h.page(path=path);second=h.page(first['before'],path=path)
   self.assertEqual(first['records']+second['records'],[record(i) for i in range(19,14,-1)])
   self.assertFalse(second['more'])
   for bad in ('0','-1','wat','10001'):
    with patch.dict('os.environ',{'POCKET_RX_HISTORY_RECORDS':bad}),self.assertRaises(ValueError):h.History()
 def test_live_byte_limit_and_archive_byte_retention(self):
  with tempfile.TemporaryDirectory() as root,patch.dict('os.environ',{'POCKET_RX_HISTORY_BYTES':'20','POCKET_RX_ARCHIVE_BYTES':'500'}):
   history=h.History();archive=h.Archive(Path(root)/'packets.sqlite3');history.archive=archive
   for i in range(20):history.add(record(i))
   self.assertLessEqual(history.size,20);archive.close()
   page=h.page(path=Path(root)/'packets.sqlite3')
   self.assertLessEqual(len(page['records']),3);self.assertEqual(page['records'][0],record(19))
 def test_archive_seed_is_once_and_storage_is_binary(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'archive.sqlite3';archive=h.Archive(path)
   archive.seed([record(0),record(1)]);archive.close()
   archive=h.Archive(path);archive.seed([record(0),record(1)]);archive.close()
   self.assertEqual(len(h.page(path=path)['records']),2)
   db=sqlite3.connect(path)
   try:
    self.assertEqual(db.execute('SELECT DISTINCT typeof(frame),typeof(wire) FROM packets').fetchall(),[('blob','blob')])
    plan=db.execute('EXPLAIN QUERY PLAN SELECT id FROM packets WHERE id<? ORDER BY id DESC LIMIT ?',(10,5)).fetchall()
    self.assertIn('SEARCH',' '.join(str(row) for row in plan))
   finally:db.close()
   path.chmod(0o644)
   with self.assertRaises(ValueError):h.page(path=path)

 def test_read_does_not_create_missing_archive(self):
  with tempfile.TemporaryDirectory() as root:
   path=Path(root)/'absent.sqlite3';self.assertEqual(h.page(path=path)['records'],[]);self.assertFalse(path.exists())
 def test_device_history_uses_existing_binary_service_transport(self):
  import subprocess
  from types import SimpleNamespace
  from device_connection import AttachedDevice
  with tempfile.TemporaryDirectory(dir='/tmp',prefix='rx-') as root:
   root=Path(root);root.chmod(0o700);path=root/'archive.sqlite3'
   archive=h.Archive(path)
   for i in range(7):archive.add(record(i))
   archive.close()
   script="""import sys
sys.path.insert(0,sys.argv[1])
from device_services import DeviceOwner
from owner import ServiceOwner,serve
class Device(ServiceOwner):
 dispatch=DeviceOwner.dispatch
 def snapshot(self,directory=False):return dict(version=1,owner_online=True)
serve(sys.argv[2],sys.argv[3],'fixture',owner_factory=Device)
"""
   import os
   env=dict(os.environ,POCKET_RX_ARCHIVE=str(path),POCKET_RX_PAGE_RECORDS='3')
   process=subprocess.Popen([sys.executable,'-c',script,str(Path(__file__).resolve().parents[1]/'shell'),str(root/'owner.sock'),str(root/'state')],env=env)
   try:
    deadline=time.monotonic()+5
    while not (root/'owner.sock').exists():
     if process.poll() is not None or time.monotonic()>deadline:self.fail('History service did not start')
     time.sleep(.01)
    from device_services import exchange
    # The same snapshot operation remains covered by existing device read grants.
    from service_transport import SocketTransport
    device=AttachedDevice.__new__(AttachedDevice)
    device.catalogue_provider=SimpleNamespace(transport=SocketTransport(str(root/'owner.sock')))
    first=device.history_page(anchor=record(6));second=device.history_page(first['before'])
    self.assertEqual(first['records']+second['records'],[record(i) for i in range(5,-1,-1)])
    self.assertFalse(second['more'])
   finally:
    process.terminate();process.wait(5)

 def test_feed_fetches_in_background_keeps_selection_and_rejects_old_device(self):
  started=threading.Event();release=threading.Event()
  def load(before,anchor=None):started.set();release.wait(3);return dict(records=[record(0)],before=1,more=False)
  data=dict(revision=1,records=[record(1),record(2)],history_page=load,history_device='one')
  form=RadioFeed(lambda:data);self.addCleanup(form.close);form.update();form.list.index=1;form.choose();selected=form.selected
  start=time.monotonic();form.action('feed.older');self.assertLess(time.monotonic()-start,.1)
  self.assertTrue(started.wait(1));self.assertEqual(form.selected,selected)
  release.set();form._history_pending.result(3);form.update()
  self.assertEqual(len(form.rows),3);self.assertEqual(form.selected,selected);self.assertFalse(form._history_more)
  form.action('feed.latest');self.assertEqual(len(form.rows),2);self.assertEqual(form.list.index,0)
  form.action('feed.older');pending=form._history_pending
  data.update(history_device='two',records=[record(9)],revision=2);form.update();pending.result(3);form.update()
  self.assertEqual(form._all_records,(record(9),))
