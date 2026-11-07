"""A renamed application must not reject the rest of an operator's desktop."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window
from panel import Panels
from session import Store,capture,restore
class DesktopMigrationTests(unittest.TestCase):
    def models(self):
        return Host(100,29,[Window('Connections',1,1,40,15),Window('RNode connections',2,3,44,19)]),Panels('top')
    def legacy(self,host,panels):
        data=capture(host,panels)
        data['windows']['RNode Bluetooth']=data['windows'].pop('RNode connections')
        data['stack']=['Connections','RNode Bluetooth'];data['focus']='RNode Bluetooth'
        data['app_views']={'RNode Bluetooth':{'selected':'usb'}}
        data['maximized']={'RNode Bluetooth':[2,3,44,19]}
        return data
    def test_rename_retains_geometry_stack_focus_maximized_and_view_without_mutating_file(self):
        host,panels=self.models();data=self.legacy(host,panels);original=copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'desktop.json';raw=json.dumps(data);path.write_text(raw)
            store=Store(path);store.load(host,panels)
            self.assertTrue(store.loaded,store.error);self.assertTrue(store.enabled)
            self.assertEqual(path.read_text(),raw)
        self.assertEqual(data,original)
        self.assertEqual(host.focus,'RNode connections')
        self.assertEqual([w.name for w in host.windows],['Connections','RNode connections'])
        self.assertEqual(host.window('RNode connections').rect,(2,3,44,19))
        self.assertEqual(host.maximized,{'RNode connections':(2,3,44,19)})
        self.assertEqual(host.app_view_state,{'RNode connections':{'selected':'usb'}})
    def test_binary_default_migrates_legacy_without_changing_original(self):
        from runtime_codec import unpack
        host,panels=self.models();data=capture(host,panels)
        with tempfile.TemporaryDirectory() as tmp:
            legacy=Path(tmp)/'session.json';raw=json.dumps(data).encode();legacy.write_bytes(raw)
            target=Path(tmp)/'session.msgpack';store=Store(target);store.load(host,panels)
            self.assertTrue(store.loaded,store.error)
            store.bind(host,panels,now=0);store.save(1,force=True)
            self.assertEqual(legacy.read_bytes(),raw)
            self.assertEqual(unpack(target.read_bytes()),data)
            again=Store(target);again.load(host,panels)
            self.assertTrue(again.loaded,again.error)
            self.assertLess(target.stat().st_size,len(raw))

    def test_alias_collision_is_rejected_before_host_mutation(self):
        host,panels=self.models();data=self.legacy(host,panels)
        data['windows']['RNode connections']=dict(data['windows']['RNode Bluetooth'])
        before=capture(host,panels)
        with self.assertRaisesRegex(ValueError,'conflicting saved windows'):restore(data,host,panels)
        self.assertEqual(capture(host,panels),before)
    def test_genuinely_unavailable_app_is_named_and_original_preserved(self):
        host,panels=self.models();data=capture(host,panels);data['windows']['Missing app']=data['windows'].pop('RNode connections')
        with self.assertRaisesRegex(ValueError,'saved applications unavailable: Missing app'):restore(data,host,panels)
    def test_window_manager_typing_does_not_change_frame_style(self):
        import ast
        from core import STYLES
        source=Path(__file__).resolve().parents[1]/'shell/desktop.py'
        tree=ast.parse(source.read_text())
        branch=next(node for node in ast.walk(tree) if isinstance(node,ast.If)
            and isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Name)
            and node.test.left.id=='char' and len(node.test.comparators)==1
            and isinstance(node.test.comparators[0],ast.Constant) and node.test.comparators[0].value=='q')
        code=compile(ast.Module(body=[branch],type_ignores=[]),str(source),'exec')
        host,panels=self.models()
        for style in STYLES:
            host.set_style(style)
            for char in 'tt':
                exec(code,{'host':host,'char':char,'STYLES':STYLES})
                self.assertEqual(host.style,style)
        host.set_style('double')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'desktop.msgpack';store=Store(path);store.bind(host,panels);store.audit(0)
            restored,other_panels=self.models();other=Store(path);other.load(restored,other_panels)
            self.assertTrue(other.loaded);self.assertEqual(restored.style,'double')
            self.assertEqual(capture(host,panels)['preferences'],capture(restored,other_panels)['preferences'])

    def test_retired_terminal_apps_do_not_reset_panel_or_preferences(self):
        host,panels=self.models();panels.panels[0].dock='bottom';host.set_palette('amber')
        state=capture(host,panels)
        name='Directory (terminal)'
        state['windows'][name]=dict(next(iter(state['windows'].values())))
        state['stack'].append(name);state['focus']=name
        state['maximized'][name]=[0,0,40,20]
        state['app_views'][name]={'selection':1}
        other,other_panels=self.models();restore(state,other,other_panels)
        self.assertEqual(other_panels.panels[0].dock,'bottom')
        self.assertEqual(capture(other,other_panels)['preferences']['palette'],'amber')
        self.assertNotIn(name,other.focus_order)

    def test_walk_rename_and_profile_retirement_preserve_desktop(self):
        host=Host(100,29,[Window('Walk',2,3,44,19),Window('Terrain Profile',1,1,50,20)])
        panels=Panels('top');host.set_palette('amber');state=capture(host,panels)
        state['focus']='Walk';state['app_views']={'Walk':{'selected':'trip'}}
        other=Host(100,29,[Window('APRS Walk Logs',0,0,40,15)])
        other_panels=Panels('top');restore(state,other,other_panels)
        self.assertEqual(other.focus,'APRS Walk Logs')
        self.assertEqual(other.window('APRS Walk Logs').rect,(2,3,44,19))
        self.assertEqual(other.app_view_state,{'APRS Walk Logs':{'selected':'trip'}})
        self.assertEqual(other.palette,'amber')
        self.assertNotIn('Terrain Profile',other.focus_order)

    def test_connections_shortcut_uses_registered_rnode_title(self):
        from native_connections import ConnectionsView
        from rnode_ble_view import descriptor
        form=ConnectionsView(SimpleNamespace(),app_context=SimpleNamespace(services={'connections':SimpleNamespace(suggested_address='')}))
        form.selected_service='reticulum';form.open_app=Mock(return_value=True)
        self.assertTrue(form.key('h'));form.open_app.assert_called_once_with(descriptor()['title'])
if __name__=='__main__':unittest.main()
