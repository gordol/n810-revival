# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""User bindings stay explicit, bounded, conflict checked, and outside literal editors."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import keybindings
from keybindings import Bindings, compile_bindings, UNBOUND


class BindingTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'keys.json'
        self.bindings=Bindings(self.path)

    def configure(self, document):
        self.path.write_text(json.dumps(document))
        self.assertTrue(self.bindings.reload(),self.bindings.error)

    def test_defaults_do_not_create_files_or_read_during_routing(self):
        self.assertFalse(self.path.exists())
        with patch.object(Path,'open',side_effect=AssertionError('I/O in hot path')):
            self.assertEqual(self.bindings.resolve('navigation','\t'),'\t')
            self.assertEqual(self.bindings.global_key('\x1d','\x1d'),'window-commands')

    def test_custom_keys_replace_defaults_and_labels_follow(self):
        self.configure({'version':1,'bindings':{'navigation':{'focus.next':['ctrl-n'],'focus.previous':['ctrl-p']}}})
        self.assertEqual(self.bindings.resolve('navigation','\x0e'),'\t')
        self.assertEqual(self.bindings.resolve('navigation','\t'),UNBOUND)
        self.assertEqual(self.bindings.label('navigation','focus.next'),'ctrl-n')
        self.assertEqual(self.bindings.resolve('navigation','x'),'x')

    def test_bad_file_preserves_last_good_config(self):
        self.configure({'version':1,'double_escape':True})
        for document in ({'version':True},{'version':1,'bindings':{'unknown':{}}},
                         {'version':1,'bindings':{'navigation':{'focus.next':['up']}}},
                         {'version':1,'bindings':{'navigation':{'focus.next':['ctrl-]']}}}):
            self.path.write_text(json.dumps(document))
            self.assertFalse(self.bindings.reload())
            self.assertTrue(self.bindings.double_escape)
            self.assertTrue(self.bindings.error)
        self.path.write_text('not json')
        self.assertFalse(self.bindings.reload());self.assertTrue(self.bindings.double_escape)
        self.path.write_text('{"version":1,"version":1}')
        self.assertFalse(self.bindings.reload());self.assertIn('Duplicate',self.bindings.error)

    def test_settings_save_preserves_custom_bindings(self):
        self.configure({'version':1,'bindings':{'global':{'windows.select':['ctrl-w']}}})
        self.assertTrue(self.bindings.set_double_escape(True))
        self.assertEqual(Bindings(self.path).global_key('\x17','\x1d'),'window-select')
        self.assertTrue(Bindings(self.path).double_escape)
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)

    def test_legacy_prefix_preference_and_explicit_override(self):
        self.assertEqual(self.bindings.global_key('\x1c','\x1c'),'window-commands')
        self.assertEqual(self.bindings.global_key('\x1d','\x1c'),'\x1d')
        self.configure({'version':1,'bindings':{'global':{'windows.commands':['ctrl-_']}}})
        self.assertEqual(self.bindings.global_key('\x1f','\x1c'),'window-commands')
        self.assertEqual(self.bindings.global_key('\x1c','\x1c'),'\x1c')

    def test_native_wrapper_uses_bindings_but_editor_text_stays_literal(self):
        from app_widgets import TextInput
        from native_navigation import native_key, navigation, Target
        class Form:
            def __init__(self):self.editor=TextInput('');self.keys=[]
            def navigation_targets(self):return [Target('action','Action','action'),Target('input:editor','Name','input')]
            def key(self,key):self.keys.append(key);return True
        self.configure({'version':1,'bindings':{'navigation':{'focus.next':['n']}}})
        form=Form()
        with patch.object(keybindings,'_current',self.bindings):
            self.assertTrue(native_key(form,'n'))
            self.assertEqual(navigation(form).current().key,'input:editor')
            # The shared form input uses a navigation-owned editor. Remapping
            # must not turn literal n into another focus movement.
            native_key(form,'n')
            self.assertEqual(navigation(form).current().key,'input:editor')
            self.assertEqual(form.editor.text,'n')
        self.configure({'version':1,'bindings':{'navigation':{'focus.next':['ctrl-n']}}})
        with patch.object(keybindings,'_current',self.bindings):
            native_key(form,'\x0e')
            self.assertEqual(navigation(form).current().key,'action')
            self.assertEqual(form.editor.text,'n')

    def test_application_remaps_preserve_editing_buttons_and_focused_enter(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from native_connections import ConnectionsView
        from native_navigation import native_key, navigation
        service=SimpleNamespace(suggested_address='',source=None,label='Disconnected',
                                busy=False,error='',connect=Mock(),disconnect=Mock())
        view=ConnectionsView(None,app_context=SimpleNamespace(services={'connections':service}))
        self.configure({'version':1,'bindings':{'connections':{
            'address.edit':['ctrl-e'],'detach':[],'attach.remote':['k']}}})
        with patch.object(keybindings,'_current',self.bindings):
            native_key(view,'e');self.assertFalse(view.editing)
            native_key(view,'\x05');self.assertTrue(view.editing)
            native_key(view,'k');self.assertEqual(view.address,'k')
            service.connect.assert_not_called()
            native_key(view,'\x1b');self.assertEqual(view.address,'')
            view.address='test-host'
            native_key(view,'c');service.connect.assert_not_called()
            native_key(view,'k');service.connect.assert_called_once_with('ssh','test-host')
            lines=view.lines()
            self.assertIn('[ctrl-e Address]',' '.join(lines))
            self.assertIn('[K Connect SSH]',' '.join(lines))
            self.assertIn('[Disconnect]',' '.join(lines))
            help_text=str(view.help_pages())
            self.assertIn('ctrl-e: enter',help_text)
            self.assertIn('K: attach',help_text)
            native_key(view,'d');service.disconnect.assert_not_called()
            navigation(view).select('action:d')
            native_key(view,'\r');service.disconnect.assert_called_once_with()
            service.disconnect.reset_mock()
            view.lines()
            x,y,_,_=next(hit for hit in view._hits if hit[3]=='d')
            view.pointer(x,y,view.width,0,False)
            service.disconnect.assert_called_once_with()

    def test_long_binding_labels_are_clipped_to_their_own_button(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        from native_connections import ConnectionsView
        owner=SimpleNamespace(label='Local owner',busy=False,error='',provider=None,
                              snapshot=lambda:{},connect=Mock())
        service=SimpleNamespace(suggested_address='',reticulum=owner)
        view=ConnectionsView(None,app_context=SimpleNamespace(services={'connections':service}))
        view.selected_service='reticulum';view.address='example';view.width=40
        self.configure({'version':1,'bindings':{'connections':{'attach.local':['ctrl-l']}}})
        with patch.object(keybindings,'_current',self.bindings):
            view.lines()
            hits=[hit for hit in view._hits if hit[1]==7]
            self.assertEqual(len(hits),2)
            self.assertLessEqual(hits[0][0]+hits[0][2],hits[1][0])
            view.pointer(hits[1][0],7,40,0,False)
            owner.connect.assert_called_once_with('socket','example')

    def test_connections_focus_highlight_matches_the_drawn_tab_strip(self):
        from types import SimpleNamespace
        from native_connections import ConnectionsView
        from native_navigation import navigation,native_presentation
        service=SimpleNamespace(suggested_address='',source=None,label='Disconnected',busy=False,error='')
        view=ConnectionsView(None,app_context=SimpleNamespace(services={'connections':service}))
        navigation(view).select('tabs')
        rows=view.lines()
        _,spans=native_presentation(view,rows,view.spans(),view.width,view.height)
        self.assertTrue(rows[0].startswith('[*Device]'))
        self.assertIn((0,0,view.width,'input'),spans)
        self.assertNotIn((1,0,view.width,'input'),spans)

    def test_application_conflicts_reject_entire_publication(self):
        for key in ('enter','tab','ctrl-]'):
            self.path.write_text(json.dumps({'version':1,'bindings':{
                'connections':{'address.edit':[key]}}}))
            self.assertFalse(self.bindings.reload())
            self.assertIn('conflict',self.bindings.error.lower())
            self.assertEqual(self.bindings.resolve('connections','e'),'e')

    def test_existing_navigation_override_shadows_default_application_binding(self):
        self.configure({'version':1,'bindings':{'navigation':{'focus.next':['e']}}})
        self.assertEqual(self.bindings.resolve('navigation','e'),'\t')
        self.assertEqual(self.bindings.label('connections','address.edit'),'unbound')
        self.assertEqual(self.bindings.resolve('connections','e'),UNBOUND)
        # An explicit conflicting app assignment is still an error.
        self.path.write_text(json.dumps({'version':1,'bindings':{
            'navigation':{'focus.next':['e']},'connections':{'address.edit':['e']}}}))
        self.assertFalse(self.bindings.reload())
        self.assertEqual(self.bindings.resolve('navigation','e'),'\t')

    def test_application_command_routing_does_not_read_configuration(self):
        self.configure({'version':1,'bindings':{'connections':{'address.edit':['ctrl-e']}}})
        with patch.object(Path,'open',side_effect=AssertionError('I/O in hot path')):
            self.assertEqual(self.bindings.resolve('connections','\x05'),'e')
            self.assertEqual(self.bindings.label('connections','address.edit'),'ctrl-e')


if __name__=='__main__':unittest.main()
