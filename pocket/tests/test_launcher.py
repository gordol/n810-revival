"""Application grouping preserves real actions and keyboard navigation."""
from pathlib import Path
from types import SimpleNamespace
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from launcher import Launcher,application_menu

class LauncherTests(unittest.TestCase):
    def test_grouping_keeps_every_supplied_action_once(self):
        entries=[('Terminal','terminal:new'),('Help','window:Help'),('Calendar','window:Calendar'),
                 ('Reticulum','app:reticulum'),('Reader','app:reader'),('Custom','app:custom')]
        registrations=[SimpleNamespace(title='Reticulum',category='Radio'),
                       SimpleNamespace(title='Reader',category='Applications')]
        legacy=[('APRS (terminal)','window:APRS (terminal)')]
        menu=application_menu(entries,registrations,legacy)
        flattened=menu.entries+[row for rows in menu.groups.values() for row in rows]
        self.assertCountEqual(flattened,entries+legacy)
        self.assertEqual(menu.entries,[('Help','window:Help')])
        self.assertEqual(menu.groups['Radio'],[('Reticulum','app:reticulum')])
        self.assertEqual(menu.groups['Utilities'],[('Calendar','window:Calendar'),('Reader','app:reader')])
        self.assertEqual(menu.groups['Applications'],[('Custom','app:custom')])

    def test_shell_windows_have_one_launcher_but_keep_new_window_action(self):
        menu=application_menu([('Terminal','terminal:new'),('Terminal 2','window:Terminal 2'),
                               ('Terminal 3','window:Terminal 3'),('Terminal','window:Terminal')])
        self.assertEqual(menu.matches(),[('Terminal','terminal:new')])
        menu.open();self.assertEqual(menu.key('\r'),'terminal:new')
        menu.open();self.assertEqual(menu.key('\r'),'terminal:new')

    def test_sorted_submenus_search_and_back(self):
        menu=Launcher([('Help','help')],{'System':[('Terminal','terminal:new'),('Bluetooth','window:Bluetooth')],
                                       'Radio':[('Reticulum','app:reticulum'),('Audio Monitor','app:audio')]})
        menu.open()
        self.assertEqual([r[0] for r in menu.matches()],['Help','Radio ›','System ›'])
        menu.key('down');menu.key('right')
        self.assertEqual([r[0] for r in menu.matches()],['‹ Back to Applications','Audio Monitor','Reticulum'])
        self.assertEqual(menu.key('\r'),'app:audio')
        menu.open();menu.key('down');menu.key('\r');menu.key('left')
        self.assertIsNone(menu.group)
        for key in 'terminal':menu.key(key)
        self.assertEqual(menu.matches(),[('System / Terminal','terminal:new')])
        self.assertEqual(menu.key('\r'),'terminal:new')

    def test_pointer_back_row_is_visible_and_works_with_no_search_results(self):
        menu=Launcher([],{'Radio':[('Reticulum','app:reticulum')]})
        menu.open();menu.key('\r')
        self.assertIn('  ‹ Back to Applications',menu.lines())
        for key in 'missing':menu.key(key)
        self.assertEqual(menu.matches(),[('‹ Back to Applications','menu:back')])
        # The desktop pointer handler selects the clicked row and sends Enter.
        menu.index=0
        self.assertIsNone(menu.key('\r'))
        self.assertTrue(menu.active)
        self.assertIsNone(menu.group)
        self.assertEqual(menu.query,'')
        self.assertEqual(menu.matches(),[('Radio ›','group:Radio')])

    def test_empty_submenu_can_return_with_pointer(self):
        menu=Launcher([],{'Empty':[]});menu.open();menu.key('\r')
        self.assertEqual(menu.index,0)
        self.assertIsNone(menu.key('\r'))
        self.assertTrue(menu.active);self.assertIsNone(menu.group)

    def test_flat_default_and_categories_contain_identical_actions(self):
        menu=application_menu([('Terminal','terminal:new'),('Help','window:Help'),('Reader','app:reader')],
                              legacy=[('Old terminal','window:Old terminal')])
        menu.open();flat=menu.matches()
        self.assertEqual([r[0] for r in flat],['Help','Old terminal','Reader','Terminal'])
        menu.set_mode('Categories')
        self.assertCountEqual([r for r in menu.entries]+[r for rows in menu.groups.values() for r in rows],flat)
        menu.key('down');menu.key('right');menu.set_mode('Alphabetical')
        self.assertIsNone(menu.group);self.assertEqual(menu.matches(),flat)

    def test_touch_pagination_reaches_last_app_and_previous_page(self):
        menu=application_menu([(f'App {i:02}',f'app:{i}') for i in range(40)])
        menu.open()
        self.assertLessEqual(len(menu.lines(15)),15)
        rows=menu.display_rows(15)
        menu.pointer(len(rows)-1,15)
        self.assertEqual(menu.display_rows(15)[0],('‹ Previous','menu:previous'))
        menu.pointer(0,15);self.assertEqual(menu.index,0)
        while menu.display_rows(15)[-1][1]=='menu:next':menu.pointer(len(menu.display_rows(15))-1,15)
        rows=menu.display_rows(15)
        self.assertEqual(menu.pointer(len(rows)-1,15),'app:39')
        self.assertFalse(menu.active)

    def test_saved_menu_mode_roundtrip_and_legacy_default(self):
        from core import Host,Window
        from panel import Panels
        from session import capture,restore
        host=Host(80,24,[Window('Terminal',0,0,40,15)],background_async=False)
        panels=Panels('top')
        host.set_preference('application_menu_mode','Categories')
        data=capture(host,panels)
        other=Host(80,24,[Window('Terminal',0,0,40,15)],background_async=False)
        restore(data,other,Panels('top'))
        self.assertEqual(other.application_menu_mode,'Categories')
        del data['preferences']['application_menu_mode']
        restore(data,other,Panels('top'))
        self.assertEqual(other.application_menu_mode,'Alphabetical')
        data['preferences']['application_menu_mode']='bad'
        with self.assertRaisesRegex(ValueError,'application menu mode'):restore(data,other,Panels('top'))

    def test_desktop_wiring_omits_settings_surface_and_includes_new_registration(self):
        import ast
        from app_registry import Registry
        from core import Window
        registry=Registry()
        registry.register(dict(id='scenery',title='Scenery',factory=lambda host:None))
        registry.register(dict(id='new-app',title='New app',category='Utilities',factory=lambda host:None))
        source=Path(__file__).resolve().parents[1]/'shell/desktop.py'
        tree=ast.parse(source.read_text())
        assignment=next(node for node in ast.walk(tree) if isinstance(node,ast.Assign)
                        and any(isinstance(t,ast.Name) and t.id=='launcher' for t in node.targets))
        namespace=dict(application_menu=application_menu,windows=[Window('Help',0,0,40,15),Window('Scenery',0,0,40,15)],
                       registered_apps=registry,legacy_names=set(),shadow_names=set(),legacy_entries=[],
                       host=SimpleNamespace(application_menu_mode='Alphabetical'))
        exec(compile(ast.Module(body=[assignment],type_ignores=[]),str(source),'exec'),namespace)
        menu=namespace['launcher']
        self.assertEqual(menu.matches(),[('Help','window:Help'),('New app','app:new-app')])
        callback=next(node for node in ast.walk(tree) if isinstance(node,ast.FunctionDef) and node.name=='set_application_menu_mode')
        host=namespace['host']
        host.set_preference=lambda name,value:setattr(host,name,value)
        exec(compile(ast.Module(body=[callback],type_ignores=[]),str(source),'exec'),namespace)
        namespace['set_application_menu_mode']('Categories')
        self.assertEqual(host.application_menu_mode,'Categories')
        self.assertEqual(menu.mode,'Categories')
        self.assertEqual(menu.matches(),[('Help','window:Help'),('Utilities ›','group:Utilities')])

    def test_context_actions_keep_provider_order(self):
        menu=Launcher([]);menu.open_context('Station',[('Show map','map'),('Inspect','inspect')])
        self.assertEqual(menu.matches(),[('Show map','map'),('Inspect','inspect')])

if __name__=='__main__':unittest.main()
