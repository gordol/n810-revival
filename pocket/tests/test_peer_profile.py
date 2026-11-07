# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from peer_profile import create_profile
from app_registry import saved_reticulum_selection
from native_peer_setup import PeerSetup

class PeerProfiles(unittest.TestCase):
    def test_stable_private_profiles_and_independent_identities(self):
        with tempfile.TemporaryDirectory() as root:
            a=create_profile(root,'listen','0.0.0.0','4242','nokia-one')
            self.assertEqual(a,create_profile(root,'listen','0.0.0.0','4242','nokia-one'))
            b=create_profile(root,'connect','192.168.1.2','4242','nokia-two')
            self.assertNotEqual(saved_reticulum_selection(a)['state'],saved_reticulum_selection(b)['state'])
            self.assertEqual(a.stat().st_mode&0o777,0o700)
            self.assertEqual(saved_reticulum_selection(a)['carriers'][0]['type'],'tcp-server')
            for mode,host,port,name in [('connect','0.0.0.0',4242,'n'),('listen','example.com',4242,'n'),('listen','0.0.0.0',0,'n'),('listen','0.0.0.0',4242,'bad name')]:
                with self.assertRaises(ValueError):create_profile(root,mode,host,port,name)
    def test_setup_uses_selected_profile_without_activating_radio(self):
        with tempfile.TemporaryDirectory() as root:
            calls=[];closed=[]
            form=PeerSetup(SimpleNamespace(state_directory=root,connect=lambda *args:calls.append(args) or True),lambda *args:closed.append(True))
            form.focus=4;form.key('\r')
            self.assertEqual(calls[0][0],'local');self.assertTrue(closed)
            self.assertEqual(saved_reticulum_selection(calls[0][1])['station'],'n810')
            form=PeerSetup(SimpleNamespace(state_directory=root),lambda *args:closed.append(True));form.key(' ')
            self.assertEqual(form.mode,'connect');self.assertEqual(form.values[0],'')
            self.assertEqual(len(form.lines(80,20)),20)
    def test_native_navigation_gives_peer_form_keyboard_precedence(self):
        from native_connections import ConnectionsView
        from native_navigation import native_key
        with tempfile.TemporaryDirectory() as root:
            view=object.__new__(ConnectionsView)
            view.peer_setup=PeerSetup(SimpleNamespace(state_directory=root),lambda:None)
            self.assertIsNone(view.navigation_form)
            native_key(view,'\t');self.assertEqual(view.peer_setup.focus,1)
            native_key(view,'\x7f');self.assertEqual(view.peer_setup.values[0],'0.0.0.')
            from app_registry import LazyApplication
            wrapped=object.__new__(LazyApplication);wrapped.owner=view;wrapped.error=''
            native_key(wrapped,'\t');self.assertEqual(view.peer_setup.focus,2)
            self.assertIsNone(wrapped.navigation_form)
if __name__=='__main__':unittest.main()
