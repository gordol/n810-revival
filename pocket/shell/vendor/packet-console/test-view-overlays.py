"""APRS overlay acceptance checks with synthetic geography; no device or radio."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('overlay_view', ROOT / 'n810-aprs-view.py')
view = importlib.util.module_from_spec(spec)
spec.loader.exec_module(view)


class Window:
    def __init__(self):
        self.cells = {}
        self.calls = []
        self.erases = 0
        self.size = (30, 100)

    def getmaxyx(self):
        return self.size

    def erase(self):
        self.erases += 1
        self.cells.clear()

    def addnstr(self, y, x, text, count, attr):
        self.calls.append((y, x, text[:count]))
        for offset, char in enumerate(text[:count]):
            self.cells[x + offset, y] = char, attr


class Atlas:
    packs = []
    errors = []

    def __init__(self, kind='road'):
        self.kind = kind
        self.requests = []

    def background(self, center, span, width, height, roads):
        self.requests.append((tuple(center), span, width, height, roads))
        return ({(x, y): ('#', self.kind)
                 for y in range(height) for x in range(width)}, ['fixture'])

    def project(self, lon, lat, center, span, width, height):
        return 12, 5


class OverlayTests(unittest.TestCase):
    def setUp(self):
        self.colors = patch.object(view, 'ink', side_effect=lambda n: n << 8)
        self.background = patch.object(view.map_style, 'cell_attr', return_value=19)
        self.colors.start()
        self.background.start()
        self.addCleanup(self.colors.stop)
        self.addCleanup(self.background.stop)

    def state(self, kind='road'):
        state = view.State()
        state.atlas = Atlas(kind)
        state.center = [5.5355, 5.5655]
        state.roads = True
        state.selected = 0
        state.add('17:35:23 BALDI>APRS ctl=03 pid=f0 !4713.13N/12150.61W_test')
        return state

    def test_selected_marker_and_label_cover_every_background(self):
        for kind in ('road', 'water', 'tone00', 'tone77', 'relief00', 'relief77'):
            with self.subTest(kind=kind):
                state = self.state(kind)
                win = Window()
                view.map_panel(win, state, 40, 2, 3, 55, 18)
                selected_attr = (7 << 8) | view.curses.A_BOLD
                self.assertEqual(win.cells[14, 8], ('@', selected_attr))
                label = [win.cells[x, 8] for x in range(16, 21)]
                self.assertEqual(''.join(char for char, _ in label), 'BALDI')
                self.assertTrue(all(attr == selected_attr for _, attr in label))

    def test_selected_station_wins_shared_cell_over_own_station(self):
        state = self.state()
        state.stations['N0CALL'] = dict(call='N0CALL', lat=5.5355, lon=5.5655)
        win = Window()
        view.map_panel(win, state, 40, 0, 0, 55, 18)
        self.assertEqual(win.cells[12, 5][0], '@')

    def test_overlay_change_reuses_base_and_resize_invalidates_it(self):
        state = self.state()
        view.map_panel(Window(), state, 40, 0, 0, 55, 18)
        state.add('17:36:23 SECOND>APRS ctl=03 pid=f0 !4720.00N/12220.00W_test')
        view.map_panel(Window(), state, 40, 0, 0, 55, 18)
        self.assertEqual(len(state.atlas.requests), 1)
        view.map_panel(Window(), state, 40, 0, 0, 60, 18)
        self.assertEqual(len(state.atlas.requests), 2)
        state.roads = False
        view.map_panel(Window(), state, 40, 0, 0, 60, 18)
        self.assertEqual(len(state.atlas.requests), 3)

    def test_new_packet_preserves_browsed_packet_identity(self):
        state = self.state()
        state.add('17:36:23 SECOND>APRS ctl=03 pid=f0 >status')
        state.selected = 1
        selected = state.packets[state.selected]['raw']
        state.add('17:37:23 THIRD>APRS ctl=03 pid=f0 >status')
        self.assertEqual(state.packets[state.selected]['raw'], selected)

    def test_default_map_initialization_does_not_import_next_engine(self):
        state = view.State()
        with patch.object(view._map, 'Atlas', return_value=Atlas()), \
                patch.object(view.importlib.util, 'spec_from_file_location') as load:
            view.init_map(state, str(ROOT / 'maps'))
        load.assert_not_called()
        self.assertIsNone(state.map_engine)
        self.assertEqual(state.map_engine_name, 'legacy')

    def test_next_engine_ansi_adapter_resize_and_inspector_return(self):
        state = self.state()
        view.init_map(state, str(ROOT / 'maps'), 'next')
        state.center = [state.stations['BALDI']['lat'], state.stations['BALDI']['lon']]
        self.assertEqual(state.map_engine.style, 'ansi')
        win = Window()
        for width, height in ((55, 18), (60, 20), (55, 18)):
            view.erase_view(win, state)
            self.assertIsNone(state.map_engine.surface.previous)
            view.map_panel(win, state, 40, 2, 3, width, height)
            self.assertEqual(state.map_engine.view.width, width)
            marks = [cell for cell in win.cells.values() if cell[0] == '@']
            self.assertEqual(len(marks), 1)
        view.erase_view(win, state)
        self.assertIsNone(state.map_engine.surface.previous)
        view.map_panel(win, state, 40, 2, 3, 55, 18)
        self.assertEqual(state.map_engine.stats['cache'], 'ram')

    def trial_state(self):
        state = self.state()
        view.init_map(state, str(ROOT / 'maps'), 'next')
        state.center = [state.stations['BALDI']['lat'], state.stations['BALDI']['lon']]
        state.help = state.debug = state.auto_fit = False
        state.map_dir = str(ROOT / 'maps')
        state.socket_path = '/nonexistent'
        state.debug_key = state.debug_record = None
        state.debug_scroll = 0
        return state

    def test_header_update_keeps_map_surface_and_modal_return_repaints(self):
        state = self.trial_state()
        win = Window()
        view.draw(win, state, 40)
        first_erases = win.erases
        win.calls.clear()
        state.status = 'Feed unavailable'
        view.draw(win, state, 40)
        self.assertEqual(win.erases, first_erases)
        map_calls = [(y, x, text) for y, x, text in win.calls
                     if 6 <= y < 22 and x < 98 and x + len(text) > 42]
        self.assertEqual(map_calls, [])
        state.help = True
        view.draw(win, state, 40)
        state.help = False
        view.draw(win, state, 40)
        self.assertGreater(win.erases, first_erases)
        self.assertTrue(any(char == '@' for char, _ in win.cells.values()))
        state.debug = True
        with patch.object(view, 'raw_record', return_value=None):
            view.draw(win, state, 40)
        state.debug = False
        view.draw(win, state, 40)
        self.assertTrue(any(char == '@' for char, _ in win.cells.values()))
        before_resize = win.erases
        win.size = (28, 90)
        view.draw(win, state, 40)
        self.assertGreater(win.erases, before_resize)

    def test_removed_marker_and_shortened_label_restore_background(self):
        state = self.trial_state()
        win = Window()
        view.map_panel(win, state, 40, 0, 0, 55, 18)
        before = dict(win.cells)
        self.assertTrue(any(char == '@' for char, _ in before.values()))
        station = state.stations.pop('BALDI')
        station['call'] = 'B'
        state.stations['B'] = station
        state.packets[0]['call'] = 'B'
        view.map_panel(win, state, 40, 0, 0, 55, 18)
        shorter = dict(win.cells)
        state.stations.clear()
        view.map_panel(win, state, 40, 0, 0, 55, 18)
        self.assertFalse(any(char == '@' for char, _ in win.cells.values()))
        self.assertNotEqual(shorter, before)
        expected = view.map_overlays(state, 40, 55, 18, state.map_engine.view)
        frame = state.map_engine.frame
        for (x, y), cell in win.cells.items():
            self.assertEqual(cell, expected.get((x, y), frame[y * 55 + x]))

    def test_legacy_frame_still_erases_on_each_redraw(self):
        state = self.state()
        win = Window()
        view.begin_frame(win, state, (2, 3, 55, 18))
        view.begin_frame(win, state, (2, 3, 55, 18))
        self.assertEqual(win.erases, 2)

    def test_rgb_trial_paints_one_map_after_refresh_and_suppresses_modal(self):
        state = self.trial_state()
        state.map_engine.style = 'rgb'
        events = []
        win = Window()
        win.refresh = lambda: events.append('refresh')
        with patch.object(state.map_engine, 'draw', side_effect=lambda *a, **k: events.append('map')) as paint, \
                patch.object(view._map.Atlas, 'background', side_effect=AssertionError('Legacy geography used')):
            view.draw(win, state, 40)
            paint.assert_not_called()
            # Curses has written only surrounding UI, never an ANSI map underneath.
            self.assertFalse(any(6 <= y < 22 and x < 98 and x + len(text) > 42
                                 for y, x, text in win.calls))
            view.finish_frame(win, state)
            self.assertEqual(events, ['refresh', 'map'])
            paint.assert_called_once()
            self.assertEqual(paint.call_args.kwargs,dict(x0=0,y0=0))
            events.clear()
            state.help = True
            view.draw(win, state, 40)
            view.finish_frame(win, state)
            self.assertEqual(events, ['refresh'])

    def test_full_map_preserves_view_selection_and_has_ascii_controls(self):
        state = self.trial_state()
        state.center = [5.5355, 5.5655]
        center = list(state.center)
        selected = state.selected
        normal = view.map_dimensions(state, 100, 30)
        view.trial_panel_key(state, ord('p'))
        self.assertEqual(view.map_dimensions(state, 100, 30), normal)
        self.assertEqual(normal[0], 99)
        self.assertEqual(state.center, center)
        self.assertEqual(state.selected, selected)
        win = Window()
        view.draw(win, state, 240)
        footer = ''.join(win.cells.get((x, 29), (' ', 0))[0] for x in range(100))
        self.assertTrue(footer.isascii())
        self.assertIn('p/x windows', footer)
        rendered = '\n'.join(''.join(win.cells.get((x, y), (' ', 0))[0]
                                     for x in range(100)) for y in range(30))
        self.assertIn('Rainier', rendered)
        view.trial_panel_key(state, ord('v'))
        self.assertFalse(view.trial_panels(state).visible)
        self.assertEqual(state.focus, 'detail')
        self.assertEqual(state.center, center)

    def test_trial_selection_uses_light_backplate_without_bold_black(self):
        state = self.trial_state()
        attr = view.selected_attr(state)
        self.assertTrue(attr & view.curses.A_REVERSE)
        self.assertFalse(attr & view.curses.A_BOLD)
        self.assertEqual(attr & ~view.curses.A_REVERSE, 72 << 8)
        win = Window()
        view.draw(win, state, 40)
        footer = ''.join(win.cells.get((x, 29), (' ', 0))[0] for x in range(100))
        self.assertTrue(footer.isascii())
        self.assertIn('p/x windows', footer)

    def test_floating_panel_controls_preserve_camera_and_selection(self):
        state = self.trial_state()
        center = list(state.center)
        selected = state.selected
        for key, expected in (('p', 'packets'), ('x', 'inspector'), ('v', None)):
            self.assertTrue(view.trial_panel_key(state, ord(key)))
            self.assertEqual(view.trial_panels(state).focus, expected or 'map')
            self.assertEqual(state.center, center)
            self.assertEqual(state.selected, selected)
        view.trial_panel_key(state, ord('p'))
        view.trial_panel_key(state, 10)
        self.assertEqual(state.focus, 'detail')
        view.trial_panel_key(state, 10)
        self.assertEqual(state.focus, 'list')
        self.assertFalse(view.trial_panel_key(state, ord('q')))

    def test_panel_content_is_bounded_and_inspector_has_single_title(self):
        state = self.trial_state()
        view.trial_panel_key(state, ord('p'))
        rows = view.floating_panel_rows(state, 38, 12)
        self.assertTrue(all(0 <= y < 12 and len(text) <= 38 for y, text, _ in rows))

        self.assertTrue(any(attr == view.selected_attr(state) for _, _, attr in rows))
        view.trial_panel_key(state, ord('x'))
        with patch.object(view, 'raw_record', return_value=None):
            rows = view.floating_panel_rows(state, 38, 12)
        self.assertEqual(sum('INSPECTOR' in text for _, text, _ in rows), 1)
        self.assertTrue(all(0 <= y < 12 and len(text) <= 38 for y, text, _ in rows))

    def test_floating_rgb_panel_uses_one_view_and_tinted_text_background(self):
        state = self.trial_state()
        state.map_engine.style = 'rgb'
        win = Window()
        win.refresh = lambda: None
        view.trial_panel_key(state, ord('p'))
        engine = state.map_engine
        with patch.object(engine, 'prepare', wraps=engine.prepare) as prepare, \
                patch.object(engine, 'draw') as paint:
            view.draw(win, state, 160)
            prepare.assert_called_once()
            frame = tuple(engine.frame)
            panel = engine.panel((1, 3, 44, 20), tint=(14, 21, 18), opacity=.65)
            # Panel heading's ordinary text inherits the tinted background.
            overlays = state.pending_map[0]
            self.assertEqual(overlays[2, 4][2], panel[2, 4][2])
            self.assertEqual(tuple(engine.frame), frame)
            view.finish_frame(win, state)
            paint.assert_called_once()
            view.trial_panel_key(state, ord('v'))
            view.draw(win, state, 160)
            self.assertNotEqual(state.pending_map[0], overlays)
            self.assertEqual(state.map_engine.view.width, 99)

    def run_queued_trial(self, keys):
        win = Window()
        queued = iter(keys)
        win.getch = lambda: next(queued)
        win.timeout = win.keypad = lambda value: None
        win.refresh = lambda: None
        selector = MagicMock()
        selector.select.return_value = []
        connection = MagicMock()
        connection.connect.side_effect = OSError('offline test')
        frames = []
        def init(state, directory, engine, theme='current'):
            state.map_engine_name = 'next'
            state.map_engine = None
            state.atlas = SimpleNamespace(packs=[], errors=[])
        def capture(win, state, span):
            frames.append((list(state.center), view.trial_panels(state).focus))
        with tempfile.NamedTemporaryFile() as history, \
                patch.object(view.curses, 'curs_set'), \
                patch.object(view.map_style, 'init_screen'), \
                patch.object(view, 'init_map', side_effect=init), \
                patch.object(view.ui_state, 'load', return_value={}), \
                patch.object(view.ui_state, 'save'), \
                patch.object(view.visibility, 'visible', return_value=True), \
                patch.object(view.selectors, 'DefaultSelector', return_value=selector), \
                patch.object(view.socket, 'socket', return_value=connection), \
                patch.object(view, 'draw', side_effect=capture):
            args = SimpleNamespace(maps='unused', map_engine='next', history=history.name,
                                   socket='/nonexistent', log=None, map_only=False)
            view.run(win, args)
        return frames

    def test_queued_pan_keys_apply_before_single_render(self):
        frames = self.run_queued_trial([view.curses.KEY_RIGHT, view.curses.KEY_RIGHT,
                                        view.curses.KEY_LEFT, -1, ord('q')])
        self.assertEqual(len(frames), 1)
        self.assertGreater(frames[0][0][1], -122.52)
        self.assertAlmostEqual(frames[0][0][0], 47.38)

    def test_queued_panel_actions_keep_order_without_intermediate_render(self):
        frames = self.run_queued_trial([ord('p'), ord('x'), -1, ord('q')])
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0][1], 'inspector')

    def test_next_labels_and_autofit_consume_canonical_engine_places(self):
        state=self.state()
        state.map_engine_name='next'
        canonical=(dict(name='Mt Rainier',lat=46.85,lon=-121.75,kind='peak'),)
        state.atlas.places=MagicMock(return_value=canonical)
        # Raw pack labels must not be traversed by the next consumer.
        class RawPacks:
            def __iter__(self):raise AssertionError('Consumer rebuilt raw geography')
        state.atlas.packs=RawPacks()
        viewport=object()
        self.assertIs(view.place_labels(state,viewport),canonical)
        state.atlas.places.assert_called_with(viewport)
        state.auto_fit=True
        view.fitted_span(state,55,18,160)
        state.atlas.places.assert_called_with(None)
        self.assertIn('BALDI',state.stations)

    def test_legacy_labels_keep_raw_source_behavior(self):
        state=self.state()
        label=dict(name='Seattle',lat=47.6,lon=-122.3,kind='city')
        state.atlas.packs=[dict(labels=[label]),dict(labels=[label])]
        self.assertEqual(view.place_labels(state),(label,label))



if __name__ == '__main__':
    unittest.main()
