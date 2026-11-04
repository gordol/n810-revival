from pathlib import Path
import importlib.util
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
path=Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum/manager.py'
spec=importlib.util.spec_from_file_location('reticulum_controls',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ControlsTests(unittest.TestCase):
    def test_data_controls_use_selected_peer_without_granting_on_read(self):
        calls=[]
        peer=dict(identity='ab'*16,public_key='cd'*64,pinned=True,label='peer')
        state=dict(version=1,peers=[peer],capabilities=['service_share','data_bridge_disconnect'],data_bridge={})
        provider=SimpleNamespace(snapshot=lambda:state,request=lambda action,payload:calls.append((action,payload)),connect=lambda kind,peer:calls.append((kind,peer)))
        view=module.Manager(app_context=SimpleNamespace(services={'reticulum':provider}));view.poll();view.tab=8
        for width,height in ((40,12),(88,26)):
            view.width,view.height=width,height
            rows=view.lines();self.assertLessEqual(len(rows),height);self.assertTrue(all(len(r)<=width for r in rows))
            hit=next(h for h in view.hits if h[3:] == ('key','u'))
            self.assertTrue(view.pointer(hit[1],hit[0],width,0,False))
            self.assertEqual(calls[-1],('peer',peer['identity']));view.tab=8
            self.assertTrue(view.key('d'));self.assertEqual(calls[-1],('data_bridge_disconnect',dict(peer=peer['identity'])))
    def test_service_grant_discloses_scope_and_requires_confirmation(self):
        calls=[];peer=dict(identity='ab'*16,public_key='cd'*64,pinned=True,label='peer')
        provider=SimpleNamespace(snapshot=lambda:dict(version=1,peers=[peer],capabilities=['service_share']),request=lambda a,p:calls.append((a,p)) or 'id')
        view=module.Manager(app_context=SimpleNamespace(services={'reticulum':provider}));view.poll();view.tab=8
        view.key('w');self.assertTrue(view.modal());self.assertIn('messages',' '.join(view.lines()));view.key('\x1b');self.assertFalse(calls)
        view.key('w');view.key('y');self.assertEqual(calls[0][1]['operations'],['snapshot','subscribe','send'])

    def test_device_read_and_grouped_use_peer_are_explicit(self):
        calls=[];peer=dict(identity='ab'*16,public_key='cd'*64,pinned=True,label='peer')
        connection=SimpleNamespace(connect=lambda kind,peer:calls.append((kind,peer)))
        provider=SimpleNamespace(snapshot=lambda:dict(version=1,peers=[peer],capabilities=['service_share']),
            request=lambda a,p:calls.append((a,p)) or 'id',connect=lambda *_:self.fail('Owner-only attachment'),
            registry=SimpleNamespace(providers={'connections':connection}))
        view=module.Manager(app_context=SimpleNamespace(services={'reticulum':provider}));view.poll();view.tab=8
        view.key('g');self.assertFalse(calls);self.assertIn('telemetry',' '.join(view.lines()))
        view.key('y');self.assertEqual(calls[-1][1]['service'],'device')
        self.assertEqual(calls[-1][1]['operations'],['snapshot','subscribe'])
        view.key('u');self.assertEqual(calls[-1],('peer',peer['identity']))

    def test_revoke_requires_confirmation_and_cancel_sends_nothing(self):
        calls=[];peer=dict(identity='ab'*16,pinned=True)
        provider=SimpleNamespace(snapshot=lambda:dict(version=1,peers=[peer],capabilities=['revoke_peer']),request=lambda a,p:calls.append((a,p)))
        view=module.Manager(app_context=SimpleNamespace(services={'reticulum':provider}));view.poll();view.tab=2
        view.key('x');self.assertTrue(view.modal());view.key('\x1b');self.assertFalse(calls)
        view.key('x');view.key('y');self.assertEqual(calls,[('revoke_peer',dict(peer=peer['identity']))])

if __name__=='__main__':unittest.main()
