# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise app focus and scrolling through the shared keyboard entry point."""
from pathlib import Path
from contextlib import closing
import sys
import unittest
import json
import sqlite3
import tempfile
import threading
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shell'))
from native_navigation import native_key, navigation
from native_heard import Heard
from native_nets import Nets
from station_map_tools import StationMapTools
from native_uls import ULSLookup
from uls_directory import lookup
from native_messages import Messages
from native_walk import Walk
from native_documents import ReaderView,LibraryView
from app_widgets import DetailBlock


class MapFixture:
    def __init__(self):
        self.side_overview = False
        self.full_overview = False
        self.pointer_captured = False
        self.context = SimpleNamespace(target=None)
        self.target_box = SimpleNamespace(view=None, revision=0)
        self.center = (47., -122.)
        self.span = 20.
        self.width, self.height = 100, 30
        self.keys = []
    def key(self, key):
        self.keys.append(key)
        if key == 's': self.side_overview = not self.side_overview
        return True
    def locator_hit(self, x, y): return False
    def pointer_event(self, event, width): return True
    def entities_at(self, x, y): return ()
    def open_directory(self): self.keys.append('directory')


class AppFocusTests(unittest.TestCase):
    def test_messages_unavailable_send_and_connect_explain_without_requests(self):
        for protocol in ('reticulum','meshcore'):
            with self.subTest(protocol=protocol):
                requests=[]
                state=dict(local_identity='fixture',peers=[],channels=[],messages=[],capabilities=['send','connect'])
                provider=SimpleNamespace(snapshot=lambda:state,request=lambda *args:requests.append(args))
                form=Messages('N0CALL',services={protocol:provider});form.protocol=protocol
                form.lines();navigation(form).select('action:s');native_key(form,'\r')
                self.assertIn('Select a contact or channel first.', '\n'.join(form.lines()))
                state['peers']=[dict(identity='a'*64,label='Example peer',pinned=True)]
                form.lines();navigation(form).select('action:s');native_key(form,'\r')
                self.assertIn('Type a message before sending.', '\n'.join(form.lines()))
                if protocol=='reticulum':
                    navigation(form).select('action:o');native_key(form,'\r')
                    self.assertIn('No radio available. Open Reticulum.', '\n'.join(form.lines()))
                self.assertEqual(requests,[])

    def test_walk_reader_and_library_details_support_home_end(self):
        walk=Walk(lambda:{})
        walk.details=lambda:['A long retained history detail '*60]
        forms=[walk,ReaderView(lambda *args:None),LibraryView(lambda *args:None)]
        for form in forms:
            with self.subTest(app=type(form).__name__):
                form.width,form.height=40,12
                if not isinstance(form,Walk):
                    def body(width):
                        result=DetailBlock(width);result.text('A long saved article '*80);return result
                    form.body=body
                form.layout.select('details' if isinstance(form,Walk) else 'detail')
                form.lines()
                native_key(form,'end');form.lines()
                self.assertGreater(form.scroll,0)
                native_key(form,'home')
                self.assertEqual(form.scroll,0)

    def test_uls_download_is_explicit_and_adopts_user_database_after_success(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ', {'XDG_DATA_HOME': folder+'/data', 'XDG_CACHE_HOME': folder+'/cache'}):
            bundled = Path(folder)/'bundle'/'uls.sqlite'
            bundled.parent.mkdir();bundled.write_bytes(b'previous bundled snapshot')
            calls = []
            def update(destination, cache, progress, cancelled):
                calls.append((destination, cache))
                progress('Importing FCC records')
                destination.parent.mkdir(parents=True)
                destination.write_bytes(b'new user snapshot')
                return {'stations': 500001}
            with patch('data_paths.data_root', return_value=bundled.parent):
                form = ULSLookup(database=bundled, updater=update)
                self.addCleanup(form.close)
                form.lines();native_key(form, '\t');native_key(form, '\r')
                self.assertTrue(form.settings);self.assertEqual(calls, [])
                native_key(form, '\t');native_key(form, '\r')
                form.pending.result(3);form.poll()
            expected = Path(folder)/'data/pocket/uls.sqlite'
            self.assertEqual(Path(form.path.text), expected)
            self.assertEqual(calls[0][0], expected)
            self.assertEqual(bundled.read_bytes(), b'previous bundled snapshot')
            self.assertIn('FCC data updated', form.status)

    def test_uls_cancel_update_preserves_existing_database(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'uls.sqlite';path.write_bytes(b'previous snapshot')
            started = threading.Event()
            def update(destination, cache, progress, cancelled):
                started.set()
                if not cancelled.wait(3):raise TimeoutError('cancel intent not received')
                raise InterruptedError('Cancelled')
            form = ULSLookup(database=path, updater=update)
            self.addCleanup(form.close)
            native_key(form, '\t');native_key(form, '\r');native_key(form, '\t');native_key(form, '\r')
            self.assertTrue(started.wait(1))
            self.assertIn('Cancel FCC update', '\n'.join(form.lines()))
            native_key(form, '\r')
            try:form.pending.result(3)
            except InterruptedError:pass
            form.poll()
            self.assertEqual(path.read_bytes(), b'previous snapshot')
            self.assertEqual(Path(form.path.text), path)
            self.assertIn('cancelled', form.status)
            self.assertEqual(form.error, '')

    def test_uls_query_failure_closes_read_connection(self):
        import uls_directory
        closed=[];connect=sqlite3.connect
        class Tracked(sqlite3.Connection):
            def close(self):closed.append(True);super().close()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'invalid.sqlite';path.touch()
            with patch.object(uls_directory.sqlite3,'connect',side_effect=lambda *a,**kw:connect(*a,**kw,factory=Tracked)):
                with self.assertRaises(sqlite3.OperationalError):lookup(path,'TEST')
            self.assertEqual(closed,[True])

    def test_uls_preserves_new_import_fields_and_distinguishes_old_snapshot(self):
        with tempfile.TemporaryDirectory() as folder:
            for extended in (False, True):
                path = Path(folder) / ('new.sqlite' if extended else 'old.sqlite')
                with closing(sqlite3.connect(path)) as db, db:
                    db.execute('CREATE TABLE stations(callsign TEXT PRIMARY KEY,name TEXT,city TEXT,region TEXT,country TEXT,license_class TEXT,status TEXT,source TEXT,updated_at TEXT)')
                    db.execute('CREATE TABLE license_details(callsign TEXT PRIMARY KEY,usid INTEGER,service TEXT,granted TEXT,expires TEXT,action_date TEXT,postal_code TEXT)')
                    db.execute('CREATE TABLE fcc_meta(key TEXT PRIMARY KEY,value TEXT)')
                    db.execute('INSERT INTO stations VALUES(?,?,?,?,?,?,?,?,?)', ('TEST','Example Licensee','Example City','WA','US','E','A','FCC ULS','2026-11-05'))
                    db.execute('INSERT INTO license_details VALUES(?,?,?,?,?,?,?)', ('TEST',12345,'HA','2020-01-01','2030-01-01','2026-11-01','00000'))
                    if extended:
                        for field, value in (('street_address','123 Example Road'),('po_box',''),('attention_line','Example Club'),('frn','0000123456'),('entity_type','L'),('applicant_type','C')):
                            db.execute('ALTER TABLE license_details ADD COLUMN '+field+' TEXT')
                            db.execute('UPDATE license_details SET '+field+'=?',(value,))
                    db.executemany('INSERT INTO fcc_meta VALUES(?,?)', ((key,json.dumps(value)) for key,value in dict(source_data_date='2026-11-05',source_url='https://example.test/fcc',imported_at='2026-11-05T12:00:00Z').items()))
                result = lookup(path, 'TEST')
                form = ULSLookup(database=path)
                self.addCleanup(form.close)
                form.width, form.height = 100, 80
                form.result = result
                text = '\n'.join(form.lines())
                self.assertIn('Radio service: HA', text)
                self.assertIn('License ID (USID): 12345', text)
                if extended:
                    for expected in ('Street address: 123 Example Road','Attention: Example Club','PO Box: Not supplied','FCC registration number (FRN): 0000123456','Applicant type: C'):
                        self.assertIn(expected, text)
                    self.assertNotIn('Address not included', text)
                else:
                    self.assertIn('Address not included in this snapshot; update FCC data', text)

    def test_uls_focus_cycle_does_not_lookup_and_results_scroll(self):
        calls = []
        form = ULSLookup(query=lambda *args: calls.append(args))
        self.addCleanup(form.close)
        form.width, form.height = 40, 12
        form.result = dict(source_data_date='2026-11-05', source_age_days=0,
                           record={'callsign': 'TEST', 'name': 'A long license holder name ' * 30})
        form.lines()
        self.assertEqual(navigation(form).current().key, 'call')
        for target in ('settings', 'lookup', 'results', 'call'):
            native_key(form, '\t')
            self.assertEqual(navigation(form).current().key, target)
        self.assertEqual(calls, [])
        native_key(form, 'backtab')
        self.assertEqual(navigation(form).current().key, 'results')
        native_key(form, 'end');form.lines()
        self.assertGreater(form.scroll, 0)
        native_key(form, 'home')
        self.assertEqual(form.scroll, 0)
        native_key(form, '\x1b')
        self.assertEqual(navigation(form).current().key, 'window')
        self.assertIsNotNone(form.result)

    def test_uls_enter_looks_up_literal_input_and_keeps_feedback_visible(self):
        calls = []
        def lookup(path, call):
            calls.append(call)
            return dict(record=None, source_data_date='2026-11-05', source_age_days=0,
                        base_callsign=call)
        form = ULSLookup(query=lookup)
        self.addCleanup(form.close)
        for key in 'TEST':native_key(form, key)
        native_key(form, '\r')
        form.pending.result(3);form.poll()
        self.assertEqual(calls, ['TEST'])
        self.assertIn('No FCC license found', '\n'.join(form.lines()))
        native_key(form, '\t');native_key(form, '\r')
        self.assertTrue(form.settings)
        original = form.path.text
        native_key(form, 'x');native_key(form, '\x1b')
        self.assertFalse(form.settings)
        self.assertEqual(form.path.text, original)
        self.assertIsNotNone(form.result)

    def test_map_and_sidebar_have_reversible_focus_and_own_arrow_scope(self):
        base = MapFixture()
        form = StationMapTools(base)
        form._sidebar_max_scroll = 20
        native_key(form, 's')
        self.assertEqual(navigation(form).current().key, 'sidebar')
        native_key(form, 'down')
        self.assertEqual(form.sidebar_scroll, 1)
        native_key(form, '\t')
        self.assertEqual(navigation(form).current().key, 'map')
        native_key(form, 'down')
        self.assertEqual(form.sidebar_scroll, 1)
        self.assertEqual(base.keys[-1], 'down')
        native_key(form, 'backtab')
        self.assertEqual(navigation(form).current().key, 'sidebar')
        native_key(form, '\x1b')
        self.assertEqual(navigation(form).current().key, 'map')
        self.assertTrue(base.side_overview)

    def test_pointer_focus_and_preview_arrow_precedence(self):
        base = MapFixture()
        form = StationMapTools(base)
        native_key(form, 's')
        form.pointer_event(('mouse', 0, 20, 10, False), 100)
        self.assertEqual(navigation(form).current().key, 'map')
        form.pointer_event(('mouse', 0, 80, 10, False), 100)
        self.assertEqual(navigation(form).current().key, 'sidebar')
        form.sidebar_scroll = 3
        base.target_box.view = ((47., -122.), 10.)
        native_key(form, 'up')
        self.assertEqual(base.keys[-1], 'up')
        self.assertEqual(form.sidebar_scroll, 3)
        native_key(form, '\t')
        self.assertEqual(navigation(form).current().key, 'map')

    def test_heard_and_nets_detail_home_end_do_not_change_selection(self):
        heard = Heard(lambda: dict(revision=1, attached=True, connected=True, events=[dict(
            type='directory.observation_added', id='one', call='TEST', captured_at='2026-11-05T00:00:00Z',
            summary='A long received observation ' * 20, source={}, facts=[])]))
        nets = Nets(lambda: {})
        nets.update = lambda: None
        nets.rows = ({'id': 'one'},)
        nets.details = lambda row: ['A long scheduled net detail ' * 30]
        for form in (heard, nets):
            with self.subTest(app=type(form).__name__):
                form.width, form.height = 40, 12
                form.layout.select('details')
                form.lines()
                selected = form.list.index
                native_key(form, 'end')
                form.lines()
                self.assertGreater(form.scroll, 0)
                self.assertEqual(form.list.index, selected)
                native_key(form, 'home')
                self.assertEqual(form.scroll, 0)


if __name__ == '__main__':
    unittest.main()
