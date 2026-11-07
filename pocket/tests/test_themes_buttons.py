# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Hardware/SSH actions and semantic materials use the same public contracts."""
import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from input import Input
from terminal_keys import legacy
from keybindings import compile_bindings
from core import Host, Window
from paint import control_ink
import themes

class Buttons(unittest.TestCase):
    def test_hardware_and_terminal_equivalents(self):
        bindings=compile_bindings({'version':1})['global']
        for raw,alt,action in ((b'\x1b[25~',b'\x1bm','wm-menu'),
                               (b'\x1b[26~',b'\x1b\t','wm-next'),
                               (b'\x1b[28~',b'\x1b\r','wm-maximize')):
            for sequence in (raw,alt):
                parser=Input(passthrough=True)
                self.assertEqual(parser.feed(sequence[:1]),[])
                event=parser.feed(sequence[1:])
                self.assertEqual(bindings[event[0][1]],action)
        self.assertEqual(legacy('\t',2),'alt-tab')
        self.assertEqual(legacy('\r',2),'alt-enter')
    def test_switch_returns_to_previous_window(self):
        host=Host(80,24,[Window('A',0,0,20,10),Window('B',5,0,20,10),Window('C',10,0,20,10)])
        host.select('A');host.select('C');host.previous_window()
        self.assertEqual(host.focus,'A')
        host.previous_window();self.assertEqual(host.focus,'C')

class Controls(unittest.TestCase):
    def test_adjusting_at_limit_does_not_publish_change(self):
        from controls import Slider,Choice
        changes=[]
        Slider('Level',lambda:10,changes.append,0,10,1).adjust(1)
        Choice('Only',lambda:'one',changes.append,['one']).adjust(1)
        self.assertEqual(changes,[])
    def test_text_input_uses_cell_caret_without_inserting_separator(self):
        from app_widgets import TextInput
        field=TextInput('abc');field.cursor=1
        text,spans=field.presentation(6)
        self.assertEqual(text,'abc   ')
        self.assertEqual(spans[-1],(1,1,'caret'))
        self.assertEqual(field.text,'abc')

class Themes(unittest.TestCase):
    def test_context_inheritance_is_immutable_and_shared(self):
        parent=themes.ThemeContext('light')
        self.assertIs(parent.derive(),parent)
        child=parent.derive(input=((1,2,3),(240,241,242)))
        self.assertEqual(parent.material['input'],themes.roles('light')['input'])
        self.assertEqual(child.material['input'],((1,2,3),(240,241,242)))
        self.assertEqual(child.material['panel'],parent.material['panel'])
        with self.assertRaises(TypeError):parent.material['body']=((0,0,0),(0,0,0))
        self.assertNotEqual(control_ink('input',parent),control_ink('input',child))

    def test_roles_are_distinct_and_light_is_light(self):
        for name in themes.PRESETS:
            self.assertNotEqual(control_ink('input',name),control_ink('selected',name))
            self.assertNotEqual(control_ink('body',name),control_ink('panel',name))
        color=control_ink('body','light')
        self.assertGreater(color&255,200)
        self.assertLess((color>>24)&255,100)
    def test_materials_cover_unstyled_rows_without_hiding_overrides(self):
        styles=themes.window_styles('light',{0:((2,5,'selected'),)},20,6)
        self.assertEqual(len(styles),4)
        self.assertEqual(styles[0][-1],(2,5,'selected'))
        self.assertEqual(styles[3],((0,18,'body'),))

if __name__=='__main__':unittest.main()
