"""Exercise alternate application modes through the shell's common dispatch."""
import sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from native_navigation import native_key,native_pointer,native_presentation,navigation

class NavigationAudit(unittest.TestCase):
    def messages(self,protocol):
        from native_messages import Messages
        state={'peers':[{'identity':'a','label':'Alpha','pinned':True},{'identity':'b','label':'Bravo','pinned':True}], 'capabilities':['send','send_channel','connect','disconnect','verify_peer','message_discovery']}
        provider=SimpleNamespace(label='Owner',snapshot=lambda:state,request=Mock(return_value='job'))
        form=Messages('N0DEM',services={protocol:provider});form.protocol=protocol;form.lines()
        return form,form.chats[protocol],provider
    def test_both_chat_protocols_navigate_the_active_conversations_and_actions(self):
        for protocol in ('reticulum','meshcore'):
            with self.subTest(protocol=protocol):
                form,chat,provider=self.messages(protocol);state=navigation(form)
                self.assertIs(state.layout(),chat.layout)
                native_key(form,'down');self.assertEqual(chat.selected,('peer','b'))
                native_key(form,'/');[native_key(form,k) for k in 'Al[]'];self.assertEqual(chat.list.query,'Al[]')
                native_key(form,'\x1b');native_key(form,'\t');self.assertEqual(chat.layout.focus,'chat')
                initial=state.current().key
                for _ in state.targets():native_key(form,'\t')
                self.assertEqual(state.current().key,initial);provider.request.assert_not_called()
                for _ in state.targets():native_key(form,'backtab')
                self.assertEqual(state.current().key,initial)
                state.select('action:c');native_key(form,'\r');self.assertTrue(chat.editing)
                for k in 'p[]/s':native_key(form,k)
                self.assertEqual(chat.editor().text,'p[]/s');self.assertEqual(form.protocol,protocol)
                native_key(form,'\t');self.assertFalse(chat.editing);provider.request.assert_not_called()
                state.select('action:s');native_key(form,'\r');provider.request.assert_called_once()
    def test_confirmation_focus_cannot_publish_or_verify(self):
        form,chat,provider=self.messages('reticulum');native_key(form,'a');self.assertTrue(chat.discovery)
        for key in ('\t','backtab','left','right','\r'):native_key(form,key)
        self.assertTrue(chat.discovery);provider.request.assert_not_called()
        rows,_=native_presentation(form,form.lines(),form.spans(),form.width,form.height)
        self.assertIn('Y confirm',rows[-1]);self.assertNotIn('Enter accept',rows[-1])
        native_key(form,'\x1b');self.assertFalse(chat.discovery)
    def test_station_map_filter_owns_tab_and_literal_input(self):
        from station_workspace import Context,StationMap
        form=StationMap(Context(),Path(__file__).resolve().parents[1]/'shell/vendor/packet-console',Mock())
        native_key(form,'g');self.assertTrue(form.filter_open)
        native_key(form,'\t');self.assertEqual(form.filter_focus,1)
        for key in 'g[]/':native_key(form,key)
        self.assertEqual(form.filter_query.text,'g[]/');native_key(form,'backtab');self.assertEqual(form.filter_focus,0)
        native_key(form,'\x1b');self.assertFalse(form.filter_open);form.close()
    def test_services_split_resize_keeps_arrows_and_cancel(self):
        from native_services import Services
        form=Services(lambda:{});form.width=120;form.lines();before=form.layout.ratio
        native_key(form,'\x12');self.assertTrue(form.layout.resizing)
        native_key(form,'right');self.assertNotEqual(form.layout.ratio,before);self.assertEqual(form.tab,0)
        native_key(form,'\x1b');self.assertEqual(form.layout.ratio,before);self.assertFalse(form.layout.resizing)
    def test_reticulum_visible_actions_are_reachable_without_requesting(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell/vendor/apps/domains/reticulum'))
        from manager import Manager
        provider=SimpleNamespace(request=Mock());form=Manager(app_context=SimpleNamespace(services={'reticulum':provider}))
        form.state={'capabilities':['connect','disconnect','pair','save_profile','select_profile','delete_profile','import_peer','verify_peer','rename_peer','send','revoke_peer','service_share','service_discovery','data_bridge_disconnect']}
        for page in range(len(form.tabs)):
            form.tab=page;form.lines();state=navigation(form);state.target=None
            keys={t.action for t in state.targets() if t.kind=='action'}
            self.assertTrue({v for y,x,end,kind,v in form.hits if kind=='key'}<=keys)
            for _ in state.targets():native_key(form,'\t')
            self.assertEqual(form.tab,page)
        provider.request.assert_not_called()
        form.tab=0;form.lines();navigation(form).select('action:c');native_key(form,'\r')
        # No configured radio: focus activation cannot invent one.
        provider.request.assert_not_called()
    def test_system_connection_action_and_read_only_pointer_fallback(self):
        from system_view import System,State
        from radio_manager import State as Radio
        opened=Mock();form=System(State(Radio()),opened)
        navigation(form).select('action:c');native_key(form,'\r');opened.assert_called_once()
        self.assertFalse(native_pointer(SimpleNamespace(key=lambda k:False),0,0,40))
    def test_last_heard_controls_remain_visible_above_framework_footer(self):
        from last_heard_view import LastHeard
        form=LastHeard(lambda:SimpleNamespace(selected=None,observations=(),status='Offline',source='local',scope='Retained'))
        rows,spans=native_presentation(form,form.lines(),form.spans(),form.width,form.height)
        self.assertIn('Selected station',rows[-2]);navigation(form).select('action:s');native_key(form,'\r');self.assertEqual(form.mode,'selected')
        native_pointer(form,2,form.height-2,form.width);self.assertEqual(form.mode,'last')

    def test_scenery_escape_and_control_toggle_use_the_actual_owner(self):
        from scenery_app import SceneryApp
        from settings import SettingsManager
        form=SceneryApp.__new__(SceneryApp);closed=Mock()
        form.manager=SettingsManager([('Scenery',(),'Scene',[('Scene',[('Value',lambda:'0',lambda d:None)])])],close=closed)
        form.manager.category='Scenery';form.controls_visible=True
        navigation(form).select('action:\x0f');native_key(form,'\r');self.assertFalse(form.controls_visible)
        native_key(form,'\x1b');closed.assert_called_once()

    def test_help_search_back_and_close_use_real_help_navigation(self):
        from help_browser import HelpBrowser
        closed=Mock();form=HelpBrowser({},(),close=closed)
        form.lines();self.assertEqual(navigation(form).current().kind,'list')
        native_key(form,'/');native_key(form,'D');self.assertEqual(form.items.query,'D')
        native_key(form,'\x1b');native_key(form,'\r');self.assertEqual(form.group,'Desktop')
        native_key(form,'\r');self.assertEqual(form.layout.focus,'reading')
        native_key(form,'\x1b');self.assertEqual(form.layout.focus,'topics')
        native_key(form,'\x1b');self.assertIsNone(form.group)
        native_key(form,'\x1b');closed.assert_called_once()
    def test_station_self_address_editor_keeps_literal_shortcuts(self):
        from station_workspace import Context,Stations
        directory=SimpleNamespace(rows=(),counts={},context=Context(),error=None,update=lambda:None,self_calls=())
        form=Stations(directory,Mock());form.edit_self_calls()
        for key in 'N0CALL/[]':native_key(form,key)
        self.assertEqual(form.self_editor.text,'N0CALL/[]')
        native_key(form,'\t');self.assertIsNotNone(form.self_editor)
        native_key(form,'\x1b');self.assertIsNone(form.self_editor)

    def test_actual_manual_search_owns_shortcuts_and_escape(self):
        from on_device_manual import ManualBrowser
        form=ManualBrowser(forms={});form.lines()
        native_key(form,'\x06');self.assertTrue(form.search_edit)
        for key in 'radio[]/':native_key(form,key)
        self.assertEqual(form.query,'radio[]/');self.assertFalse(form.items.searching)
        rows,_=native_presentation(form,form.lines(),form.spans(),form.width,form.height)
        self.assertIn('radio[]/',rows[-1])
        native_key(form,'\t');self.assertFalse(form.search_edit)
        self.assertEqual(form.layout.focus,'topics')
        native_key(form,'\x06');native_key(form,'\x1b');self.assertFalse(form.search_edit)
