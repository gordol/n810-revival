"""Read-only select/inspect/map/filter workflow through the TUI adapter."""
import hashlib
import importlib.util
import json
import datetime
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('workspace_tui', ROOT / 'n810-aprs-view.py')
view = importlib.util.module_from_spec(spec)
spec.loader.exec_module(view)


class Window:
    def __init__(self, width=100, height=30):
        self.size = height, width

    def getmaxyx(self):
        return self.size

    def erase(self):
        pass

    def addnstr(self, y, x, text, count, attr):
        assert 0 <= y < self.size[0] and 0 <= x < self.size[1]
        assert x + count <= self.size[1]

    def refresh(self):
        pass


class WorkspaceTests(unittest.TestCase):
    def state(self):
        state = view.State()
        view.init_map(state, str(ROOT / 'maps'), 'next', 'color')
        state.map_engine.style = 'rgb'
        state.center = [47.38, -122.52]
        state.auto_fit = state.help = state.debug = False
        state.roads = False
        state.terrain = True
        state.debug_key = state.debug_record = None
        state.debug_scroll = 0
        state.socket_path = '/nonexistent'
        for line in ('09:00:01 N0CALL>APRS ctl=03 pid=f0 !4710.00N/12231.00W[test',
                     '09:00:02 BALDI>APRS ctl=03 pid=f0 !4713.13N/12150.61W_test',
                     '09:00:03 N0CALL>APRS ctl=03 pid=f0 >operator status'):
            state.add(line, historical=True)
        return state

    def test_select_inspect_map_filter_clear_and_back_share_selection(self):
        state = self.state()
        selected = view.selected_row(state)['raw']
        camera = tuple(state.center)
        for key in ('p', 'x'):
            view.trial_panel_key(state, ord(key))
        panels = view.trial_panels(state)
        self.assertEqual(panels.visible, {'packets', 'inspector'})
        state.add('09:00:04 OTHER>APRS ctl=03 pid=f0 >new traffic')
        self.assertEqual(view.selected_row(state)['raw'], selected)
        view.trial_panel_key(state, ord('c'))
        self.assertEqual(state.call_filter, 'N0CALL')
        self.assertEqual(len(view.packet_rows(state)), 2)
        view.move_selection(state, 1)
        self.assertNotEqual(view.selected_row(state)['raw'], selected)
        self.assertEqual(view.selected_row(state)['call'], 'N0CALL')
        view.trial_panel_key(state, ord('z'))
        self.assertEqual(panels.focus, 'map')
        self.assertEqual(panels.visible, {'packets', 'inspector'})
        view.trial_panel_key(state, ord('a'))
        self.assertEqual(len(view.packet_rows(state)), 4)
        view.trial_panel_key(state, 127)
        self.assertEqual(state.call_filter, 'N0CALL')
        self.assertEqual(tuple(state.center), camera)

    def test_capture_identity_matches_native_id_and_missing_bytes_stay_unknown(self):
        packet = view.selected_row(self.state())
        record = dict(time='2026-10-16T09:00:03-07:00', frame='000102030405')
        identity = view.packet_identity(packet, record)
        expected = hashlib.sha256((record['time'] + record['frame']).encode()).hexdigest()
        self.assertEqual(identity['capture_id'], expected)
        missing = view.packet_identity(packet)
        self.assertIsNone(missing['capture_id'])
        self.assertTrue(missing['local_record_key'].startswith('decoded:'))

    def test_both_windows_and_tinted_bars_use_one_full_view_at_wide_and_narrow_sizes(self):
        state = self.state()
        for key in ('p', 'x'):
            view.trial_panel_key(state, ord(key))
        for width, height in ((100, 30), (64, 24), (133, 40)):
            with self.subTest(width=width):
                win = Window(width, height)
                with patch.object(state.map_engine, 'prepare', wraps=state.map_engine.prepare) as prepare, \
                        patch.object(state.map_engine, 'draw') as draw, \
                        patch.object(view, 'raw_record', return_value=None):
                    view.draw(win, state, 212)
                    prepare.assert_called_once()
                    overlays, x, y = state.pending_map
                    self.assertEqual((x, y), (0, 0))
                    self.assertTrue(all(0 <= x < width - 1 and 0 <= y < height
                                        for x, y in overlays))
                    self.assertEqual(state.map_engine.view.height, height)
                    layout = state.panel_module.layout(width - 1, height, state.panel_model.visible)
                    self.assertIn('packets', layout)
                    self.assertIn('inspector', layout)
                    rect = layout['top']
                    shade = state.map_engine.panel(rect, tint=state.tui_theme.PANEL_TINT, opacity=.72)
                    self.assertEqual(overlays[0, 0][2], shade[0, 0][2])
                    view.finish_frame(win, state)
                    draw.assert_called_once()

    def test_empty_filter_never_invents_a_selected_capture(self):
        state = self.state()
        view.filter_station(state, 'UNHEARD')
        self.assertEqual(view.packet_rows(state), [])
        self.assertIsNone(view.selected_row(state))
        self.assertIn('No packets match', view.selection_caption(state))
        self.assertIsNone(view.packet_identity(view.selected_row(state))['capture_id'])

    def test_native_contract_adapter_uses_shared_window_ids_and_honest_freshness(self):
        contract = json.loads((ROOT / 'packet-workspace-contract.json').read_text())
        state = self.state()
        for key in ('p', 'x', 'c'):
            view.trial_panel_key(state, ord(key))
        snapshot = view.workspace_view(state)
        self.assertEqual(set(snapshot['windows']), set(contract['windows']))
        self.assertEqual(snapshot['filter_scope'], contract['filter_scope'])
        self.assertEqual(set(snapshot['filter']), set(contract['filter_default']))
        self.assertEqual(snapshot['filter']['station'], 'N0CALL')
        self.assertIsNone(snapshot['selected_capture_id'])
        self.assertIsNone(snapshot['freshness']['captured'])
        self.assertIsNone(snapshot['freshness']['fetched'])
        self.assertFalse(snapshot['capabilities']['transmit'])
        record = dict(time='2026-10-16T09:00:03-07:00', frame='000102030405')
        with patch.object(view, 'raw_record', return_value=record):
            view.floating_panel_rows(state, 60, 24, 'inspector')
        state.transport_read_time = '2026-10-16T09:20:00-07:00'
        snapshot = view.workspace_view(state)
        self.assertEqual(snapshot['selected_capture_id'],
                         hashlib.sha256((record['time'] + record['frame']).encode()).hexdigest())
        self.assertEqual(snapshot['freshness']['captured'], record['time'])
        self.assertNotEqual(snapshot['freshness']['captured'], snapshot['freshness']['fetched'])

    def test_evicted_inspected_record_does_not_silently_select_another(self):
        state = view.State()
        state.map_engine_name = 'next'
        for i in range(200):
            state.add('10:%02d:%02d N0CALL>APRS ctl=03 pid=f0 >record %d' %
                      (i // 60, i % 60, i))
        state.selected = 199
        view.trial_panel_key(state, ord('x'))
        selected = view.selected_row(state)['raw']
        state.add('10:04:00 BALDI>APRS ctl=03 pid=f0 >new traffic')
        self.assertNotIn(selected, [row['raw'] for row in state.packets])
        self.assertIsNone(view.selected_row(state))
        self.assertIn('left retained history', view.selection_caption(state))
        self.assertIsNone(view.workspace_view(state)['selected_capture_id'])
        rows = view.floating_panel_rows(state, 42, 18, 'packets')
        self.assertFalse(any(attr == view.selected_attr(state) for _, _, attr in rows))
        state.add('10:04:01 BALDI>APRS ctl=03 pid=f0 >more traffic')
        self.assertIsNone(view.selected_row(state))
        view.move_selection(state, -1)
        self.assertIsNotNone(view.selected_row(state))

    def test_window_filter_fixture_matches_existing_contract_without_losing_selection(self):
        fixture = json.loads((ROOT / 'fixtures/tui-window-contract.json').read_text())
        contract = json.loads((ROOT / 'packet-workspace-contract.json').read_text())
        state = self.state()
        spec = importlib.util.spec_from_file_location('fixture_monitor', ROOT / 'n810-packet-monitor.py')
        monitor = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(monitor)
        record = fixture['capture']
        stamp = datetime.datetime.fromisoformat(record['time']).strftime('%H:%M:%S')
        state.add(stamp + ' ' + monitor.describe(bytes.fromhex(record['frame'])))
        with patch.object(view, 'raw_record', return_value=record):
            view.floating_panel_rows(state, 60, 24, 'inspector')
        for step in fixture['steps']:
            with self.subTest(intent=step['intent']):
                self.assertIn(step['intent'], contract['intents'])
                if step['intent'] == 'toggle_window':
                    self.assertIn(step['window'], contract['windows'])
                    key = 'p' if step['window'] == 'list' else 'x'
                elif step['intent'] == 'focus_window':
                    self.assertEqual(step['window'], 'map')
                    key = 'z'
                elif step['intent'] == 'filter_call':
                    self.assertEqual(view.selected_row(state)['call'], step['call'])
                    key = 'c'
                else:
                    self.assertEqual(step['intent'], 'back')
                    key = '\x7f'
                view.trial_panel_key(state, ord(key))
                snapshot = view.workspace_view(state)
                self.assertEqual({name for name, visible in snapshot['windows'].items() if visible},
                                 set(step['visible']))
                self.assertEqual(snapshot['focus'], step['focus'])
                self.assertEqual(snapshot['filter']['station'], step['station'])
                self.assertEqual(snapshot['filter_scope'], contract['filter_scope'])
                self.assertEqual(snapshot['selected_capture_id'], fixture['expected_capture_id'])
                self.assertEqual(snapshot['selected_station'], fixture['expected_station'])


    def test_expired_selection_survives_clean_save_without_record_substitution(self):
        saved = dict(center=[47.38, -122.52], span=212, panels=['packets', 'inspector'],
                     panel_focus='inspector', call_filter='N0CALL', selection_expired=True,
                     selected_raw=None)
        win = Window()
        win.getch = lambda: ord('q')
        win.timeout = win.keypad = lambda value: None
        selector = MagicMock()
        selector.select.return_value = []
        connection = MagicMock()
        connection.connect.side_effect = OSError('offline test')
        def init(state, *args):
            state.map_engine_name = 'next'
            state.map_engine = None
            state.atlas = SimpleNamespace(packs=[], errors=[])
        with tempfile.NamedTemporaryFile() as history, \
                patch.object(view.curses, 'curs_set'), \
                patch.object(view.map_style, 'init_screen'), \
                patch.object(view, 'init_map', side_effect=init), \
                patch.object(view.ui_state, 'load', return_value=saved), \
                patch.object(view.ui_state, 'save') as save, \
                patch.object(view.visibility, 'visible', return_value=True), \
                patch.object(view.selectors, 'DefaultSelector', return_value=selector), \
                patch.object(view.socket, 'socket', return_value=connection):
            args = SimpleNamespace(maps='unused', map_engine='next', tui_theme='color',
                                   history=history.name, socket='/nonexistent', log=None, map_only=False)
            view.run(win, args)
        state_key, persisted = save.call_args.args
        self.assertEqual(state_key, 'map-next')
        self.assertTrue(persisted['selection_expired'])
        self.assertIsNone(persisted['selected_raw'])
        self.assertEqual(persisted['panels'], ['inspector', 'packets'])
        self.assertEqual(persisted['panel_focus'], 'inspector')
        self.assertEqual(persisted['call_filter'], 'N0CALL')
        self.assertEqual(persisted['center'], saved['center'])

    def test_legacy_retention_does_not_gain_trial_expiry_behavior(self):
        state = view.State()
        state.map_engine_name = 'legacy'
        for i in range(200):
            state.add('10:%02d:%02d N0CALL>APRS ctl=03 pid=f0 >record %d' %
                      (i // 60, i % 60, i))
        state.selected = 199
        state.add('10:04:00 BALDI>APRS ctl=03 pid=f0 >new traffic')
        self.assertFalse(state.selection_expired)
        self.assertIsNotNone(view.selected_row(state))

    def test_external_station_handoff_rebinds_filter_record_and_map_then_returns(self):
        state = self.state()
        view.filter_station(state, 'N0CALL')
        previous = view.selected_row(state)['raw']
        camera = list(state.center)
        station_cache = dict(state.stations)
        request = dict(call='BALDI', position=[47.4, -122.3], source='directory', id='fixture')
        view.activate_external_target(state, request)
        self.assertEqual(state.call_filter, 'BALDI')
        self.assertEqual(view.selected_row(state)['call'], 'BALDI')
        snapshot = view.workspace_view(state)
        self.assertEqual(snapshot['selected_station'], 'BALDI')
        self.assertEqual(snapshot['external_target']['source'], 'directory')
        self.assertEqual(view.trial_panels(state).focus, 'map')
        self.assertIn('external last known position', view.selection_caption(state))
        self.assertEqual(view.include_selection(state, 212, 99, 30), 212)
        self.assertEqual(state.center, camera)
        self.assertEqual(state.stations, station_cache)
        view.trial_panel_key(state, 127)
        self.assertIsNone(state.map_target)
        self.assertEqual(state.call_filter, 'N0CALL')
        self.assertEqual(view.selected_row(state)['raw'], previous)
        self.assertEqual(state.center, camera)

    def test_external_without_retained_capture_is_explicit_and_does_not_invent_record(self):
        state = self.state()
        camera = list(state.center)
        view.filter_station(state, 'N0CALL')
        view.activate_external_target(state, dict(call='UNHEARD', source='directory'))
        snapshot = view.workspace_view(state)
        self.assertEqual(snapshot['selected_station'], 'UNHEARD')
        self.assertIsNone(snapshot['selected_capture_id'])
        self.assertIsNone(view.selected_row(state))
        self.assertIn('external location unknown', view.selection_caption(state))
        self.assertEqual(view.include_selection(state, 212, 99, 30), 212)
        self.assertEqual(state.center, camera)
        with patch.object(view, 'raw_record') as raw:
            rows = view.floating_panel_rows(state, 60, 24, 'inspector')
        raw.assert_not_called()
        self.assertTrue(any('external target' in text for _, text, _ in rows))
        self.assertTrue(any('No retained packet' in text for _, text, _ in rows))
        self.assertNotIn('UNHEARD', state.stations)

    def test_manual_record_selection_and_filter_clear_external_target_without_camera_jump(self):
        state = self.state()
        camera = list(state.center)
        view.activate_external_target(state, dict(call='BALDI', position=[48.5, -123], source='directory'))
        view.move_selection(state, 1)
        self.assertIsNone(state.map_target)
        self.assertIsNone(view.workspace_view(state)['external_target'])
        self.assertEqual(state.center, camera)
        view.activate_external_target(state, dict(call='BALDI', position=[48.5, -123], source='directory'))
        view.filter_station(state, 'N0CALL')
        self.assertIsNone(state.map_target)
        self.assertEqual(view.selected_row(state)['call'], 'N0CALL')
        self.assertEqual(state.center, camera)

    def test_cancel_external_target_restores_prior_expiry_not_a_substitute_record(self):
        state = self.state()
        state.call_filter = 'N0CALL'
        state.selection_expired = True
        view.activate_external_target(state, dict(call='BALDI', source='directory'))
        self.assertFalse(state.selection_expired)
        self.assertEqual(view.selected_row(state)['call'], 'BALDI')
        view.cancel_external_target(state)
        self.assertEqual(state.call_filter, 'N0CALL')
        self.assertTrue(state.selection_expired)
        self.assertIsNone(view.selected_row(state))

    def test_external_position_can_be_shown_without_history_and_without_cache_mutation(self):
        state = self.state()
        state.packets.clear()
        state.stations.clear()
        original = list(state.center)
        view.activate_external_target(state, dict(call='UNHEARD', position=[49, -124], source='directory'))
        span = view.include_selection(state, 40, 99, 30)
        self.assertGreater(span, 40)
        viewport = state.map_next.Viewport(state.center, span, 99, 30)
        for lat, lon in (original, [49, -124]):
            x, y = viewport.project(lon, lat)
            self.assertTrue(0 <= x < 99 and 0 <= y < 30)
        overlays = view.map_overlays(state, span, 99, 30, viewport)
        self.assertTrue(any(char == '@' for char, _ in overlays.values()))
        self.assertEqual(state.stations, {})
        self.assertIsNone(view.workspace_view(state)['selected_capture_id'])

    def test_directory_target_keeps_retained_route_visible_and_fits_relays(self):
        state=self.state()
        state.center=[5.5355,5.5655]
        state.add('09:01:00 K7QHQ-12>APRS,RELAY1*,WIDE2-1 ctl=03 pid=f0 >route fixture')
        state.stations.update({
            'K7QHQ-12':dict(call='K7QHQ-12',lat=5.5355,lon=5.5655),
            'RELAY1':dict(call='RELAY1',lat=48.5,lon=-121.5),
            'UNRELATED':dict(call='UNRELATED',lat=5.5655,lon=5.5855)})
        original=list(state.center)
        view.activate_external_target(state,dict(call='K7QHQ-12',position=original,source='directory'))
        span=view.include_selection(state,20,99,30)
        self.assertGreater(span,20)
        self.assertEqual(state.call_filter,'K7QHQ-12')
        self.assertTrue(state.terrain)
        viewport=state.map_next.Viewport(state.center,span,99,30)
        for lat,lon in (original,[48.5,-121.5]):
            x,y=viewport.project(lon,lat)
            self.assertTrue(0<=x<99 and 0<=y<30)
        with patch.object(view,'ink',side_effect=lambda n:n<<8):
            cells=view.map_overlays(state,span,99,30,viewport)
        self.assertTrue(any(char=='·' for char,attr in cells.values()))
        text='\n'.join(''.join(cells.get((x,y),(' ',0))[0] for x in range(99)) for y in range(30))
        self.assertIn('RELAY1',text)
        self.assertNotIn('UNRELATED',text)
        self.assertIn('retained packet route',view.selection_caption(state))

    def test_external_target_without_matching_capture_never_borrows_other_route(self):
        state=self.state()
        state.center=[5.5355,5.5655]
        state.add('09:01:00 OTHER>APRS,RELAY1* ctl=03 pid=f0 >unrelated route')
        state.stations.update({'OTHER':dict(call='OTHER',lat=5.5655,lon=5.5855),
                               'RELAY1':dict(call='RELAY1',lat=48.5,lon=-121.5)})
        view.activate_external_target(state,dict(call='UNHEARD',position=[5.5355,5.5655],source='directory',heard_through=['RELAY1']))
        self.assertIsNone(view.mapped_packet(state))
        self.assertEqual(view.include_selection(state,40,99,30),40)
        viewport=state.map_next.Viewport(state.center,40,99,30)
        with patch.object(view,'ink',side_effect=lambda n:n<<8):
            cells=view.map_overlays(state,40,99,30,viewport)
        self.assertFalse(any(char=='·' for char,attr in cells.values()))
        self.assertNotIn('heard_through',state.map_target)
        # Even a stale/incorrect list selection cannot supply a different route.
        state.call_filter=None;state.selected=0
        self.assertEqual(view.selected_row(state)['call'],'OTHER')
        self.assertIsNone(view.mapped_packet(state))

    def test_saved_external_target_restores_explicit_station_context_without_moving_camera(self):
        state = self.state()
        view.filter_station(state, 'N0CALL')
        previous = view.selected_row(state)['raw']
        camera = list(state.center)
        view.activate_external_target(state, dict(call='BALDI', source='directory'))
        saved_target = json.loads(json.dumps(state.map_target))
        view.filter_station(state, 'N0CALL')
        view.activate_external_target(state, saved_target, remember=False)
        self.assertEqual(state.call_filter, 'BALDI')
        self.assertEqual(view.selected_row(state)['call'], 'BALDI')
        self.assertEqual(state.center, camera)
        view.cancel_external_target(state)
        self.assertEqual(view.selected_row(state)['raw'], previous)
        self.assertEqual(state.call_filter, 'N0CALL')
        self.assertEqual(state.center, camera)


if __name__ == '__main__':
    unittest.main()
