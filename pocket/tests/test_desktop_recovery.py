from pathlib import Path
import contextlib,io,json,sys,tempfile,unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from app_registry import LazyApplication
from desktop_recovery import Recovery
from session import Store,capture
from core import Host,Window
from panel import Panels
from runtime_codec import pack

class RecoveryTests(unittest.TestCase):
    def test_restoring_saved_panels_requests_layout_before_render(self):
        import ast
        tree=ast.parse((Path(__file__).resolve().parents[1]/'shell/desktop.py').read_text())
        callback=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='restore_recovery')
        wrapper=ast.parse('def factory():\n resized=False\n def state():return resized\n return restore_recovery,state\n')
        wrapper.body[0].body.insert(1,callback)
        with tempfile.TemporaryDirectory() as folder:
            host=Host(100,29,[Window('Station Map',0,0,60,20)])
            host.app_forms={};panels=Panels('top');panels.layout(100,30)
            path=Path(folder)/'desktop.msgpack';path.write_bytes(pack(capture(host,panels)))
            namespace=dict(store=Store(path,enabled=False),host=host,panel=panels,restore_pending=[],registered_apps=SimpleNamespace(forms={}))
            exec(compile(ast.fix_missing_locations(wrapper),'<recovery callback>','exec'),namespace)
            restore,resized=namespace['factory']();restore('Station Map')
            self.assertTrue(resized())
            panels.layout(100,30);panels.render({})

    def test_recovery_choices_do_not_modify_saved_session(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'desktop.msgpack'
            host=Host(100,29,[Window('Surface room',1,1,40,15),Window('Closed app',2,2,40,15,opened=False)])
            raw=pack(capture(host,Panels('top')));path.write_bytes(raw)
            report=root/'failure.json';report.write_text(json.dumps({'message':'scene failed','log':'/var/log/pocket/failure.log'}))
            calls=[];form=Recovery(report,Store(path,enabled=False),lambda name:calls.append(name) or 'restored')
            self.assertEqual(form.apps,['Surface room'])
            form.key('s');self.assertEqual(calls,[])
            form.key('\n');form.key('a');self.assertEqual(calls,['Surface room',None])
            self.assertEqual(path.read_bytes(),raw)
            self.assertIn('scene failed','\n'.join(form.lines()))
    def test_callback_failures_are_contained_and_release_the_owner(self):
        for method,args in [('key',('x',)),('lines',()),('layer',()),('pointer',(1,1,20)),('presentation_interval',()),('presented',(0,)),('close',())]:
            with self.subTest(method=method):
                class Broken:
                    closed=False
                    def close(self):self.closed=True
                owner=Broken()
                def fail(*args,**kwargs):raise ValueError('fixture failure')
                setattr(owner,method,fail)
                entry=SimpleNamespace(id='broken',title='Broken',preferred_size=(40,15))
                form=LazyApplication(None,entry,None);form.owner=owner;form.saved={'keep':'state'}
                errors=io.StringIO()
                with contextlib.redirect_stderr(errors):getattr(form,method)(*args)
                self.assertIsNone(form.owner);self.assertIn('fixture failure',form.error)
                self.assertIn('POCKET_APP_ERROR app=broken',errors.getvalue())
                self.assertEqual(form.session_state(),{'keep':'state'})
                self.assertIn('could not open',' '.join(form.lines()))
    def test_app_status_uses_the_same_failure_boundary_as_rendering(self):
        from desktop_actions import dispatch
        class Broken:
            def lines(self):raise ValueError('status rendering failed')
            def close(self):pass
        host=Host(100,29,[Window('Broken',1,1,40,15)])
        entry=SimpleNamespace(id='broken',title='Broken',preferred_size=(40,15))
        form=LazyApplication(None,entry,host);form.owner=Broken();host.app_forms={'Broken':form}
        with contextlib.redirect_stderr(io.StringIO()):
            result=dispatch(host,lambda action:None,{},dict(command='app-status',name='Broken'))
        self.assertIn('status rendering failed',result['error'])
        self.assertIsNone(form.owner)
        self.assertEqual(result['bounds'],[1,1,40,15])
        self.assertTrue(result['lines'])
    def test_native_navigation_callbacks_are_isolated(self):
        import native_navigation as nav
        from unittest.mock import patch
        cases=[('native_key',('x',)),('native_pointer',(1,1,40)),
               ('native_presentation',([],[],40,15)),('native_escape_allowed',(True,))]
        for method,args in cases:
            with self.subTest(method=method):
                entry=SimpleNamespace(id='broken',title='Broken',preferred_size=(40,15))
                owner=SimpleNamespace(close=lambda:None)
                form=LazyApplication(None,entry,None);form.owner=owner
                with patch.object(nav,'_'+method,side_effect=ValueError('navigation failed')),contextlib.redirect_stderr(io.StringIO()):
                    getattr(nav,method)(form,*args)
                self.assertIsNone(form.owner)
                self.assertIn('navigation failed',form.error)

    def test_system_exit_is_not_swallowed(self):
        entry=SimpleNamespace(id='stop',title='Stop',preferred_size=(40,15))
        form=LazyApplication(None,entry,None)
        class Stop:
            def key(self,key):raise SystemExit(5)
        form.owner=Stop()
        with self.assertRaises(SystemExit):form.key('x')
if __name__=='__main__':unittest.main()
