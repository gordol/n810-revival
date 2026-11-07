from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from chat_view import ChatView
from native_messages import Messages

class ChatTests(unittest.TestCase):
    def make(self,protocol='reticulum'):
        self.sent=[];self.state=dict(version=1,local_identity='owner',capabilities=['send','send_channel','verify_peer'],
            peers=[dict(identity='a'*64,label='Alice',pinned=True)],messages=[])
        provider=SimpleNamespace(snapshot=lambda:self.state,request=lambda a,p:self.sent.append((a,p)))
        view=ChatView(provider,protocol);view.refresh();return view
    def test_enter_does_not_send_explicit_send_and_owner_switch_isolate_drafts(self):
        view=self.make();view.key('c')
        for letter in 'hello':view.key(letter)
        view.key('\r');self.assertFalse(self.sent)
        view.key('\x13');self.assertEqual(self.sent,[('send',dict(peer='a'*64,text='hello'))])
        self.assertEqual(view.editor().text,'')
        view.key('c');view.key('x');self.state['local_identity']='another';view.refresh();self.assertEqual(view.editor().text,'')
        self.state['local_identity']='owner';view.refresh();self.assertEqual(view.editor().text,'x')
    def test_typing_action_letters_does_not_trigger_controls(self):
        view=self.make();view.key('c')
        for letter in 'abcopsv':view.key(letter)
        self.assertEqual(view.editor().text,'abcopsv')
        self.assertFalse(view.discovery);self.assertFalse(self.sent)

    def test_failed_owner_submission_restores_draft_without_replay(self):
        view=self.make();view.provider.request=lambda a,p:'pending-id'
        view.editor().text='keep this';view.send();self.assertEqual(view.editor().text,'')
        self.state['last_job']=dict(id='pending-id',state='failed',error='disconnected')
        view.refresh();self.assertEqual(view.editor().text,'keep this');self.assertFalse(self.sent)

    def test_unverified_peer_cannot_send_and_channel_is_labelled_public(self):
        view=self.make('meshcore');self.state['peers'][0]['pinned']=False
        view.editor().text='hello';view.key('s');self.assertFalse(self.sent)
        self.state['channels']=[dict(index=0,label='Public',privacy='public')];view.refresh();view.selected=('channel',0)
        view.editor().text='group';view.key('s');self.assertEqual(self.sent[-1],('send_channel',dict(channel=0,text='group')))
        for width,height in ((40,12),(84,26)):
            view.width,view.height=width,height;lines=view.lines()
            self.assertEqual(len(lines),height);self.assertTrue(all(len(line)<=width for line in lines));self.assertIn('public',' '.join(lines))
    def test_meshcore_contact_pages_keep_channels_visible(self):
        view=self.make('meshcore');self.state.update(peers_total=350,peers_offset=0,peers_page_size=32,
            channels=[dict(index=0,label='Public',privacy='public')])
        self.state['capabilities'].append('contacts_page');view.refresh()
        self.assertEqual(view.rows[0]['key'],('channel',0))
        view.key(']');self.assertEqual(self.sent[-1],('contacts_page',dict(offset=32)))
        self.state['peers_offset']=320;view.key(']')
        self.assertEqual(self.sent[-1],('contacts_page',dict(offset=320)))
        view.key('[');self.assertEqual(self.sent[-1],('contacts_page',dict(offset=288)))

    def test_messages_protocol_switch_preserves_receive_view_and_drafts(self):
        view=Messages('N0DEM');view.key('p');self.assertEqual(view.protocol,'reticulum')
        view.key('p');self.assertEqual(view.protocol,'meshcore');view.key('p');self.assertEqual(view.protocol,'aprs')
        for protocol in ('aprs','reticulum','meshcore'):
            view.protocol=protocol;view.width=40;view.height=12
            self.assertEqual(len(view.lines()),12)

if __name__=='__main__':unittest.main()
