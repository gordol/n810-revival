from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from system_view import State,System
from radio_state import State as RadioState,adapter

class AttachmentTests(unittest.TestCase):
    def payload(self,connected=True):
        return dict(live=dict(data=dict(receive_connected=connected)),connector=dict(
            ssh=dict(success=True,observed_at=1),attachment=dict(service='receive',owner='nokia@192.168.10.1',transport='ssh',attached=True,connected=connected)))
    def test_system_shows_feed_connection_without_inventing_host_telemetry(self):
        connector=SimpleNamespace(payload=self.payload());state=State(connector,clock=lambda:100)
        state.update();opened=[];view=System(state,lambda:opened.append(True))
        for page in (0,1):
            view.page=page;lines=view.lines();text=' '.join(lines)
            self.assertIn('nokia@192.168.10.1',text);self.assertIn('SSH · feed connected',text)
            self.assertIn('System telemetry: not attached',text);self.assertNotIn('CPU busy: Unknown',text)
            y,x=view.connection_hit;self.assertTrue(view.pointer(x,y,view.width));self.assertTrue(opened)
        connector.payload=self.payload(False);state.update()
        self.assertIn('feed disconnected',' '.join(view.lines()))
    def test_old_telemetry_does_not_label_live_ssh_feed_stale(self):
        radio=RadioState(clock=lambda:100);radio.payload=self.payload();radio.result=adapter.adapt(radio.payload,100)
        entries,styles=radio.panel(200)
        self.assertEqual(styles['radio:SSH'],'good')
        self.assertNotIn('SSH stale',''.join(label for _,label in entries))
        radio.payload=self.payload(False)
        self.assertEqual(radio.panel(200)[1]['radio:SSH'],'bad')
