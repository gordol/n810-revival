"""Help focus and scrolling through the desktop navigation dispatcher."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'shell'))
from on_device_manual import ManualBrowser
from native_navigation import native_key, native_presentation, navigation


class HelpFocusTests(unittest.TestCase):
    def test_context_help_tab_selection_reading_and_back(self):
        for width in (45, 110):
            with self.subTest(width=width):
                form = ManualBrowser(pages=[], forms={}, global_pages=(('Second topic', tuple('Line %s' % i for i in range(40))),))
                form.width, form.height = width, 14
                form.open_context('Desktop')

                def draw():
                    rows, _ = native_presentation(form, form.lines(), form.spans(), width, form.height)
                    return rows

                draw()
                self.assertEqual(navigation(form).current().key, 'pane:reading')
                native_key(form, 'down')
                self.assertEqual(form.scroll, 1)
                self.assertEqual(form.items.index, 0)
                native_key(form, '\t')
                self.assertEqual(form.layout.focus, 'topics')
                self.assertEqual(navigation(form).current().key, 'pane:topics')
                self.assertIn('Topics', draw()[-1])
                native_key(form, 'down')
                self.assertEqual(form.items.index, 1)
                native_key(form, '\r')
                self.assertEqual(form.layout.focus, 'reading')
                draw()
                native_key(form, 'j')
                self.assertEqual(form.scroll, 1)
                native_key(form, 'k')
                self.assertEqual(form.scroll, 0)
                for key, focus in (('backtab', 'topics'), ('backtab', 'reading'), ('\t', 'topics'), ('\t', 'reading')):
                    native_key(form, key)
                    self.assertEqual(form.layout.focus, focus)
                    draw()
                native_key(form, '\x1b')
                self.assertEqual(form.layout.focus, 'topics')
                native_key(form, '\x1b')
                self.assertIsNone(form.group)
                native_key(form, '\x06')
                self.assertTrue(form.search_edit)
                for key in 'test query':
                    native_key(form, key)
                self.assertEqual(form.query, 'test query')
                self.assertIn('test query', draw()[-1])
                native_key(form, '\t')
                self.assertFalse(form.search_edit)
                self.assertEqual(form.layout.focus, 'topics')

    def test_app_help_loaded_after_browser_creation(self):
        class DeferredApp:
            ready = False
            def help_pages(self):
                return (('Browse records', ('Tab changes panes.',)),) if self.ready else ()
        app = DeferredApp()
        form = ManualBrowser(pages=[], forms={'Later app': app})
        form.open_context('Desktop')
        app.ready = True
        self.assertTrue(form.open_context('Later app'))
        self.assertEqual(form.group, 'Later app')
        self.assertEqual(form.page()[0], 'Browse records')
        self.assertEqual(form.layout.focus, 'reading')

    def test_search_focus_and_resize_hint(self):
        form = ManualBrowser(pages=[], forms={})
        form.width = 110
        form.open_context('Desktop')
        form.lines()
        native_key(form, '\x06')
        for key in 'query':
            native_key(form, key)
        native_key(form, 'backtab')
        self.assertFalse(form.search_edit)
        self.assertEqual(form.layout.focus, 'reading')
        native_key(form, '\x06')
        native_key(form, '\x1b')
        native_key(form, '\x12')
        rows, _ = native_presentation(form, form.lines(), form.spans(), 110, form.height)
        self.assertIn('Left/Right resize', rows[-1])
        self.assertNotIn('Search:', rows[-1])
        native_key(form, '\x1b')
        self.assertFalse(form.resizing)


if __name__ == '__main__':
    unittest.main()
