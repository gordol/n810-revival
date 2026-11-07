# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Existing app views follow session attachment changes through one binding."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from service_selection import Selection
from chat_view import ChatView


class Owner:
    def __init__(self,identity):self.identity=identity;self.requests=[];self.closed=False
    def snapshot(self):return dict(local_identity=self.identity,peers=[],messages=[])
    def request(self,action,payload):self.requests.append((action,payload));return self.identity
    def drain(self):pass
    def close(self):self.closed=True


class AppSessionServicesTests(unittest.TestCase):
    def test_existing_view_follows_attachment_and_disconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            first,second=Owner('first'),Owner('second')
            binding=Selection(None,directory,initial=first)
            self.addCleanup(binding.close)
            view=ChatView(binding,'reticulum')
            view.refresh();self.assertEqual(view.state['local_identity'],'first')
            binding.adopt(second,'Other device')
            view.refresh();self.assertEqual(view.state['local_identity'],'second')
            self.assertIs(view.provider,binding)
            self.assertEqual(view.provider.request('snapshot',{}),'second')
            self.assertEqual(first.requests,[])
            self.assertEqual(second.requests,[('snapshot',{})])
            binding.disconnect();view.refresh()
            self.assertFalse(view.state['owner_online'])
            with self.assertRaisesRegex(ValueError,'Select a reticulum owner'):
                view.provider.request('send',{})
            self.assertEqual(len(second.requests),1)


if __name__=='__main__':unittest.main()
