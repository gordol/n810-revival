# Retained navigation regressions from explorations/current-world/test_native_navigation.py.
import sys
from pathlib import Path
SHELL=Path(__file__).resolve().parents[1]/'shell'
sys.path.insert(0,str(SHELL))
import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from native_navigation import native_key,native_presentation,navigation
from app_widgets import Canvas,TextInput
from settings import SettingsManager
from radio_manager import State,RadioManager
from native_feed import RadioFeed
from native_documents import ReaderView,LibraryView
from native_cw import CW
from native_workbench import WorkbenchView


class NavigationTests(unittest.TestCase):
    def test_map_escape_cancels_captured_drag_before_directory_navigation(self):
        from station_workspace import Context,StationMap
        sources=SHELL/'vendor/packet-console'
        directory=Mock();form=StationMap(Context(),sources,directory);form.preview=False
        before=form.center
        self.assertTrue(form.pointer(10,5,form.width,0,False))
        self.assertTrue(form.pointer(15,7,form.width,32,False))
        self.assertNotEqual(form.center,before);self.assertTrue(form.pointer_captured)
        self.assertTrue(native_key(form,'\x1b'))
        self.assertFalse(form.pointer_captured);self.assertEqual(form.center,before);directory.assert_not_called()
        self.assertFalse(form.pointer(15,7,form.width,0,True));self.assertEqual(form.center,before)
        self.assertTrue(native_key(form,'\x1b'));directory.assert_called_once()

    def test_settings_tabbar_is_focusable_and_arrows_only_change_its_tabs(self):
        value=[0];closed=[]
        def row(label):return label,lambda:str(value[0]),lambda d:value.__setitem__(0,value[0]+d)
        settings=SettingsManager([('Window',('x',),'Window controls',[('Style',[row('Frame'),row('Opacity')]),('Motion',[row('Speed')])])],close=lambda:closed.append(True))
        native_key(settings,'\r');self.assertEqual(settings.category,'Window')
        self.assertEqual(navigation(settings).current().key,'item:0')
        native_key(settings,'right');self.assertEqual(value[0],1)
        native_key(settings,'backtab');self.assertEqual(navigation(settings).current().key,'tabs')
        native_key(settings,'right');self.assertEqual(settings.pages['Window'].section,1);self.assertEqual(value[0],1)
        lines,spans=native_presentation(settings,settings.lines(),settings.spans(),64,18)
        self.assertIn('Tabs',lines[-1]);self.assertIn((2,0,64,'input'),spans)
        native_key(settings,'\t');native_key(settings,'right');self.assertEqual(value[0],2)
        native_key(settings,'\x1b');self.assertIsNone(settings.category);self.assertEqual(closed,[])
        native_key(settings,'\x1b');self.assertEqual(closed,[True]) # Dismisses Settings, never desktop quit.

    def test_radio_read_control_enter_is_explicit_and_tabs_do_not_change_page(self):
        client=SimpleNamespace(publication={'state':'idle','request_id':None},active=False,start=Mock(return_value=True),check=Mock(return_value=False),cancel=Mock(return_value=False))
        form=RadioManager(State(read_client=client));form.lines()
        self.assertEqual(navigation(form).current().key,'action:r')
        native_key(form,'\t');self.assertEqual(form.page,0);self.assertEqual(client.start.call_count,0)
        native_key(form,'backtab');native_key(form,'\r');self.assertEqual(client.start.call_count,1)
        native_key(form,']');self.assertEqual(form.page,1);self.assertEqual(navigation(form).current().key,'tabs')
        native_key(form,'\t');self.assertEqual(form.memory_layout.focus,'groups')
        native_key(form,'right');self.assertEqual(form.page,1)
        native_key(form,'\x1b');self.assertEqual(form.page,0)

    def test_feed_compact_status_and_history_controls(self):
        data={'revision':1,'connected':True,'snapshot_observation':{'label':'Feed transport connected'},
              'radio_link':{'last_reported_connected':False,'current_known':True,'freshness':'current'},
              'evidence':[{'time':'2026-10-18T00:00:00+00:00','direction':'radio_to_host','raw':'ALPHA>APRS packet'}]}
        for width in (48,96):
            form=RadioFeed(lambda:data);form.width=width;form.height=16
            lines=form.lines();text=' '.join(lines)
            self.assertEqual(len(lines),16)
            self.assertIn('Radio: disconnected',lines[0])
            for clutter in ('Radio Feed','retained','Snapshot:','Feed transport connected'):
                self.assertNotIn(clutter,text)
            self.assertEqual(form._rects['feed'][1],3 if form.layout.tabbed else 2)
            self.assertNotIn('Freeze',text)
            for action in ('feed.older','feed.latest'):
                x,y,w,_=next(hit for hit in form._actions if hit[3]==action)
                self.assertLess(x,width)
                self.assertTrue(form.pointer(x,y,width))
            self.assertTrue(data['connected'])

    def test_feed_search_captures_shortcuts_and_enter_before_inspector(self):
        form=RadioFeed(lambda:{'revision':1,'connected':True,'evidence':[{'time':'2026-10-18T00:00:00+00:00','direction':'radio_to_host','raw':'ALPHA>APRS ctl=03 pid=f0 payload'}]})
        form.lines();native_key(form,'/')
        for key in 'payload':native_key(form,key)
        self.assertEqual(form.list.query,'payload')
        native_key(form,'\r');self.assertEqual(form.layout.focus,'feed')
        native_key(form,'\t');self.assertEqual(form.layout.focus,'inspect')
        native_key(form,'\x1b');self.assertEqual(form.layout.focus,'feed')
        native_key(form,'\x1b');self.assertEqual(form.list.query,'')

    def test_document_search_and_explicit_filter_remain_separate(self):
        for view_class in (ReaderView,LibraryView):
            with self.subTest(view=view_class.__name__):
                command=Mock();view=view_class(command)
                rows=(SimpleNamespace(id='a',title='ALPHA',relative_path='ALPHA',saved=False,read=False),SimpleNamespace(id='b',title='BRAVO',relative_path='BRAVO',saved=False,read=False))
                view.update(SimpleNamespace(revision=1),rows)
                native_key(view,'/')
                for key in 'bravo':native_key(view,key)
                self.assertEqual(view.items.index,1);self.assertIsNone(view.entry);self.assertEqual(command.call_count,0)
                native_key(view,'\r');self.assertEqual(view.layout.focus,'items')
                native_key(view,'\t');self.assertEqual(view.layout.focus,'detail')
                native_key(view,'\x1b');self.assertEqual(view.layout.focus,'items')
                native_key(view,'\x1b');native_key(view,'F');self.assertIsNotNone(view.entry)
                native_key(view,'/');self.assertEqual(view.entry.text,'/')
                native_key(view,'\x1b');self.assertIsNone(view.entry);self.assertEqual(command.call_count,0)

    def test_inline_inputs_keep_literal_keys_and_tab_never_runs_jobs(self):
        cw=CW(decoder=SimpleNamespace());cw.decode=Mock(return_value=True)
        self.assertEqual(navigation(cw).current().key,'input:path')
        for key in 'q/[]n':native_key(cw,key)
        self.assertEqual(cw.path.text,'q/[]n');self.assertEqual(cw.fields.query,'')
        native_key(cw,'\x1b');self.assertEqual(cw.path.text,'')
        for _ in range(3):native_key(cw,'\t')
        self.assertEqual(cw.decode.call_count,0);native_key(cw,'\r');cw.decode.assert_called_once()
        commands=Mock();workbench=WorkbenchView(commands)
        for key in '/tmp/example':native_key(workbench,key)
        self.assertEqual(workbench.path.text,'/tmp/example')
        native_key(workbench,'\t');self.assertEqual(commands.call_count,0)
        native_key(workbench,'\r');commands.assert_called_once_with('select','/tmp/example')

    def test_station_selection_details_map_and_explicit_filter(self):
        from station_workspace import Context,Stations
        context=Context();context.select({'lines':['ALPHA']},{'call':'ALPHA','position':[47.,-122.]})
        class Directory:
            counts={}
            rows=({'call':'ALPHA','name':'First'},{'call':'BRAVO','name':'Second'});error=None
            def __init__(self):self.context=context
            def update(self):pass
            def select(self,call):context.select({'lines':[call]},{'call':call,'position':[47.,-122.]});return True
        opened=[];view=Stations(Directory(),lambda:opened.append(context.target['call']));view.lines()
        native_key(view,'/');[native_key(view,key) for key in 'bravo'];native_key(view,'\r')
        self.assertEqual(context.target['call'],'BRAVO');self.assertEqual(opened,[])
        native_key(view,'\r');self.assertEqual(opened,['BRAVO'])
        native_key(view,'\t');self.assertEqual(view.focus,1)
        native_key(view,'\x1b');self.assertEqual(view.focus,0)
        # Shared context changes from another view must move the actual list highlight.
        context.select({'lines':['ALPHA']},{'call':'ALPHA'});view.lines();self.assertEqual(view.list.index,0)
        native_key(view,'backtab');self.assertEqual(navigation(view).current().key,'filter')
        native_key(view,'S');self.assertEqual(view.query,'S')
        native_key(view,'\x1b');self.assertEqual(view.query,'');self.assertEqual(view.focus,0)

    def test_empty_settings_and_lists_have_safe_focus_cycles(self):
        forms=(SettingsManager([]),RadioManager(State()),RadioFeed(lambda:{}),ReaderView(Mock()),LibraryView(Mock()))
        for form in forms:
            with self.subTest(form=type(form).__name__):
                for key in ('\t','backtab','up','down','left','right','\x1b'):
                    native_key(form,key)
                lines,spans=native_presentation(form,('',),(),60,16)
                self.assertEqual(len(lines),16);self.assertTrue(lines[-1]);self.assertTrue(spans)

class NativeCatalogTests(unittest.TestCase):
    def test_actual_native_catalog_and_preview_focus_roundtrips(self):
        import app_gallery,time
        from core import Host
        from native_messages import Messages
        from native_services import Services
        from native_nets import Nets
        from native_walk import Walk
        from native_heard import Heard
        from radio_manager import RadioQuick
        from system_view import System,State as SystemState
        from font_preview import FontPreview
        import draw_metrics
        from widgets import CalendarView
        from controls import SplitPane,TextPanel
        from settings import SettingsWindow
        host=Host(100,30,[])
        radio=State();system=SystemState(radio)
        forms=[Messages('N0CALL'),Services(lambda:{}),Nets(lambda:{}),Walk(lambda:{}),Heard(lambda:{}),RadioFeed(lambda:{}),CW(decoder=SimpleNamespace()),WorkbenchView(Mock()),ReaderView(Mock()),LibraryView(Mock()),RadioManager(radio),RadioQuick(radio,RadioManager(radio),Mock()),System(system),FontPreview(host),CalendarView()]
        from station_workspace import Context,Stations,StationMap
        from audio_monitor import AudioMonitor
        context=Context()
        directory=SimpleNamespace(rows=(),counts={},context=context,error=None,update=lambda:None)
        sources=SHELL/'vendor/packet-console'
        if not sources.is_dir():sources=SHELL/'vendor/packet-console'
        forms.extend([Stations(directory,Mock()),StationMap(context,sources,Mock()),AudioMonitor(path='/tmp/native-navigation-fixture-missing.sock')])
        if hasattr(draw_metrics,'RenderDebug'):forms.append(draw_metrics.RenderDebug(lambda:None,lambda:True,lambda:()))
        previews=app_gallery.forms();forms.extend(previews.values())
        forms.append(SplitPane(TextPanel(('One','Two')),SettingsWindow([('One',[('Value',lambda:'1',lambda d:None)])])))
        for form in forms:
            with self.subTest(view=type(form).__name__,name=getattr(form,'name','')):
                if hasattr(form,'width'):form.width=80
                if hasattr(form,'height'):form.height=24
                lines=form.lines(time.time()) if isinstance(form,CalendarView) else form.lines()
                state=navigation(form);keys=[t.key for t in state.targets()];self.assertTrue(keys)
                initial=state.current().key
                for _ in keys:native_key(form,'\t')
                self.assertEqual(state.current().key,initial)
                for _ in keys:native_key(form,'backtab')
                self.assertEqual(state.current().key,initial)
                rows,spans=native_presentation(form,lines,form.spans() if hasattr(form,'spans') else (),80,24)
                self.assertEqual(len(rows),24);self.assertTrue(rows[-1])
                native_key(form,'\x1b')
                for target in tuple(state.targets()):
                    if target.kind!='list':continue
                    state.select(target.key);listing,_=state.listing()
                    if listing is None:continue
                    native_key(form,'/')
                    for key in 'n[]/q':native_key(form,key)
                    self.assertEqual(listing.query,'n[]/q')
                    native_key(form,'\r');self.assertFalse(listing.searching)
                    native_key(form,'\x1b');self.assertEqual(listing.query,'')
        for form in forms:
            if hasattr(form,'close'):form.close()

    def test_radio_memory_wheel_scrolls_without_changing_selection(self):
        from native_navigation import native_pointer
        form=RadioManager(State());form.page=1;form.width=120;form.height=20
        form.lines();form.sync_memory=lambda:None
        form.memory_channels.rows=tuple('Memory '+str(i) for i in range(50))
        form.memory_channels.index=0
        x,y,w,h=form.memory_layout.rects['channels']
        native_pointer(form,x+1,y+5,120,65)
        self.assertEqual(form.memory_channels.index,0)
        self.assertGreater(form.memory_channels.offset,0)

class RegisteredNavigationTests(unittest.TestCase):
    def test_lazy_connections_uses_real_view_focus_and_visible_tab_strip(self):
        from app_registry import Registry
        from native_connections import descriptor
        from core import Host
        registry=Registry(providers={'connections':SimpleNamespace(suggested_address='',reticulum=SimpleNamespace(),meshcore=SimpleNamespace())})
        registry.register(descriptor())
        host=Host(80,30,registry.windows(80,30));host.app_forms={};host.minimum_sizes={};registry.bind(host)
        self.assertTrue(registry.open('connections'))
        wrapper=registry.forms['Connections'];view=wrapper.owner
        native_key(wrapper,'backtab');self.assertEqual(navigation(view).current().key,'tabs')
        native_key(wrapper,'right');self.assertEqual(view.selected_service,'reticulum')
        native_key(wrapper,'\t');self.assertEqual(view.selected_service,'reticulum')
        native_key(wrapper,'backtab');native_key(wrapper,'left');self.assertEqual(view.selected_service,'receive')
        rows,spans=native_presentation(wrapper,('',),(),40,16)
        self.assertIn((0,0,40,'input'),spans);self.assertIn('Tabs',rows[-1])

    def test_reticulum_tab_order_and_modal_input_survive_shared_navigation(self):
        from app_registry import Registry
        from core import Host
        registry=Registry();registry.configure_reticulum()
        host=Host(80,30,registry.windows(80,30));host.app_forms={};host.minimum_sizes={};registry.bind(host)
        self.assertTrue(registry.open('reticulum'))
        wrapper=registry.forms['Reticulum'];view=wrapper.owner
        native_key(wrapper,'backtab');native_key(wrapper,'right')
        self.assertEqual(view.tab,2)  # Peers follows Radio in the displayed strip.
        native_key(wrapper,'\t');self.assertEqual(view.tab,2)
        view.compose='';view.compose_peer='fixture'
        for key in 'q/[]n':native_key(wrapper,key)
        self.assertEqual(view.compose,'q/[]n')
        native_key(wrapper,'\x1b');self.assertIsNone(view.compose)

    def test_interactive_canvas_retains_application_keys_and_pixels(self):
        form=SimpleNamespace(layer_only=True,key=Mock(return_value=True))
        self.assertTrue(native_key(form,'\t'));form.key.assert_called_once_with('\t')
        self.assertEqual(native_presentation(form,('canvas',),(),40,16),(('canvas',),()))

    def test_bluetooth_focus_does_not_operate_hardware_until_enter(self):
        from bluetooth_view import Bluetooth
        state=SimpleNamespace(request=Mock())
        form=Bluetooth(state)
        native_key(form,'\t');self.assertEqual(form.focus,1);state.request.assert_not_called()
        native_key(form,'\r');state.request.assert_called_once_with('controller_off')

    def test_system_profile_review_tab_does_not_switch_page(self):
        from system_view import System,State as SystemState
        from radio_manager import State
        form=System(SystemState(State()));form.page=1;form.links.choosing=True
        native_key(form,'\t');native_key(form,'backtab')
        self.assertEqual(form.page,1);self.assertTrue(form.links.choosing)
