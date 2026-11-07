# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Explicit panel count reduction preserves widgets and preferred top placement."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from panel import Panels


class PanelRemovalTests(unittest.TestCase):
    def test_default_top_menu_removes_bottom_launcher_even_when_locked(self):
        for mode,width in (('auto',200),('auto',100),('dock',200),('sidebar',100)):
            with self.subTest(mode=mode,width=width):
                panels=Panels('top',mode=mode)
                panels.layout(width,30)
                top=panels.panels[0]
                self.assertEqual(panels.selected,top)
                self.assertTrue(panels.locked)
                expected={widget for panel in panels.panels for widget in panel.widgets}
                self.assertTrue(panels.remove(prefer_bottom=True))
                self.assertEqual(panels.panels,[top])
                self.assertEqual(top.dock,'top')
                self.assertEqual(set(top.widgets),expected)
                self.assertEqual(panels.mode,'bar')
                for width in (100,200,100):
                    panels.layout(width,30)
                    self.assertEqual(panels.panels,[top])
                    self.assertEqual(top.rect[1],0)
                self.assertFalse(panels.remove(prefer_bottom=True))

    def test_selected_populated_panel_moves_widgets_and_publishes_once(self):
        panels=Panels('top')
        top=panels.panels[0]
        self.assertTrue(panels.add())
        bottom=panels.selected
        top.widgets.remove('clock');bottom.widgets=['clock']
        changes=[];panels.bind_session(lambda:changes.append(True))
        panels.pending_drag=('clock',bottom,0,0)
        self.assertTrue(panels.remove())
        self.assertEqual(panels.panels,[top])
        self.assertEqual(top.widgets.count('clock'),1)
        self.assertIs(panels.selected,top)
        self.assertIsNone(panels.pending_drag)
        self.assertEqual(changes,[True])

    def test_non_primary_selection_is_removed_instead_of_bottom(self):
        panels=Panels('top')
        top=panels.panels[0]
        panels.add();bottom=panels.selected;bottom.widgets=['custom']
        panels.add();left=panels.selected;left.widgets=['apps']
        self.assertTrue(panels.remove(prefer_bottom=True))
        self.assertNotIn(left,panels.panels)
        self.assertIn(bottom,panels.panels)
        self.assertIn('apps',top.widgets)

    def test_legacy_remove_entry_point_does_not_refuse_populated_panel(self):
        panels=Panels('top',mode='auto')
        panels.selected=next(panel for panel in panels.panels if panel.widgets==['apps'])
        self.assertTrue(panels.remove_empty())
        self.assertEqual(len(panels.panels),1)
        self.assertIn('apps',panels.panels[0].widgets)


if __name__=='__main__':unittest.main()
