# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Window selection focuses existing windows without opening apps and leaves modal Escape alone."""
from pathlib import Path
import sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window
from keybindings import Bindings
from window_selection import WindowSelection,directional_name


class WindowSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.bindings=Bindings(Path(self.temp.name)/'keys.json')
        self.host=Host(100,40,[Window('A',0,0,25,15),Window('B',35,0,25,15),Window('C',0,20,25,15)])
        self.host.animate=False;self.host.focus='A'
        self.selection=WindowSelection(self.host,self.bindings)

    def test_opt_in_double_escape_timeout_and_modal_guard(self):
        self.assertFalse(self.selection.double_escape('\x1b',1))
        self.assertFalse(self.selection.double_escape('\x1b',1.1))
        self.bindings.set_double_escape(True)
        self.selection.reset_sequence()
        self.assertFalse(self.selection.double_escape('\x1b',2,allowed=False))
        self.assertFalse(self.selection.double_escape('\x1b',2.1))
        self.assertFalse(self.selection.double_escape('x',2.2))
        self.assertFalse(self.selection.double_escape('\x1b',3))
        self.assertFalse(self.selection.double_escape('\x1b',4))
        self.assertTrue(self.selection.double_escape('\x1b',4.2))
        self.assertTrue(self.selection.active);self.assertFalse(self.host.overview)

    def test_traversal_highlights_only_and_escape_restores_app(self):
        self.selection.enter();self.assertIsNone(self.selection.key('\t'))
        self.assertEqual(self.host.focus,'B');self.assertFalse(self.host.overview)
        self.selection.key('backtab');self.assertEqual(self.host.focus,'A')
        self.selection.key('q');self.assertTrue(self.selection.active)
        self.selection.key('\x1b')
        self.assertFalse(self.selection.active);self.assertFalse(self.host.overview)
        self.assertEqual(self.host.focus,'A')

    def test_accept_returns_window_for_explicit_activation(self):
        self.selection.enter();self.selection.key('\t')
        self.assertEqual(self.selection.key('\r'),'B')
        self.assertFalse(self.selection.active);self.assertEqual(self.host.focus,'B')

    def test_directional_focus_is_geometric_not_registration_order(self):
        rects={'center':(20,20,10,10),'below':(20,40,10,10),'left':(0,20,10,10),'right':(40,20,10,10),'above':(20,0,10,10)}
        for direction,name in (('up','above'),('down','below'),('left','left'),('right','right')):
            self.assertEqual(directional_name(rects,'center',direction),name)
        self.assertEqual(directional_name(rects,'above','up'),'above')


if __name__=='__main__':unittest.main()
