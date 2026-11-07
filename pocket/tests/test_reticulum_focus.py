# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reticulum selection uses list navigation and truthful shared focus hints."""
from pathlib import Path
import importlib.util
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

SHELL=Path(__file__).resolve().parents[1]/'shell'
sys.path.insert(0,str(SHELL))
from native_navigation import native_key,native_presentation,navigation
spec=importlib.util.spec_from_file_location('reticulum_focus_manager',SHELL/'vendor/apps/domains/reticulum/manager.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ReticulumFocusTests(unittest.TestCase):
    def test_peer_selection_and_search_use_list_scope_without_requests(self):
        provider=SimpleNamespace(request=Mock())
        form=module.Manager(app_context=SimpleNamespace(services={'reticulum':provider}))
        form.tab=2
        form.state={'peers':[{'identity':'alpha','label':'Alpha'}, {'identity':'bravo','label':'Bravo'}]}
        lines=form.lines()
        focus=navigation(form)
        self.assertEqual(focus.current().kind,'list')
        rows,_=native_presentation(form,lines,form.spans(),form.width,form.height)
        self.assertIn('select',rows[-1]);self.assertNotIn('scroll',rows[-1])
        native_key(form,'down');self.assertEqual(form.index,1)
        form.lines();native_key(form,'/')
        for key in 'Alpha':native_key(form,key)
        self.assertEqual(form.index,0)
        native_key(form,'\r')
        listing,_=focus.listing();self.assertFalse(listing.searching)
        self.assertEqual(listing.query,'Alpha')
        native_key(form,'\x1b');self.assertEqual(listing.query,'')
        provider.request.assert_not_called()

    def test_profile_editor_uses_shared_cursor_and_cancel_without_request(self):
        provider=SimpleNamespace(request=Mock())
        form=module.Manager(app_context=SimpleNamespace(services={'reticulum':provider}))
        form.edit_profile({'label':'host'})
        for key in ('home','x','right','delete'):native_key(form,key)
        self.assertEqual(form.editing['values'][0],'xhst')
        form.lines();self.assertTrue(any(role=='caret' for _,_,_,role in form.spans()))
        native_key(form,'\x1b');self.assertIsNone(form.editing)
        provider.request.assert_not_called()

    def test_composer_enter_keeps_draft_and_only_explicit_send_requests(self):
        provider=SimpleNamespace(request=Mock(return_value='job'))
        form=module.Manager(app_context=SimpleNamespace(services={'reticulum':provider}))
        form.state={'capabilities':['send']}
        form.compose_peer='peer';form.compose='hello'
        native_key(form,'\r');self.assertEqual(form.compose,'hello');provider.request.assert_not_called()
        self.assertIn('Ctrl-S',form.navigation_modal_hint()[1])
        native_key(form,'\x13')
        provider.request.assert_called_once_with('send',{'peer':'peer','text':'hello'})
        self.assertIsNone(form.compose)

    def test_all_item_pages_declare_list_and_information_pages_do_not(self):
        form=module.Manager()
        for page in range(len(form.tabs)):
            form.tab=page
            content=next(target for target in form.navigation_targets() if target.key=='content')
            self.assertEqual(content.kind,'details' if page in (5,6) else 'list')


if __name__=='__main__':unittest.main()
