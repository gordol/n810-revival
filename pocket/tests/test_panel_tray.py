import sys
from pathlib import Path
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from panel_tray import menu,handles
from bluetooth_view import State

class TrayTests(unittest.TestCase):
    def test_snapshot_does_not_send_and_only_owner_capabilities_are_offered(self):
        calls=[]
        snapshot=dict(version=1,type='state',controller=dict(available=True,powered=True,devices=[]),
                      capabilities=['controller_off','receive_start'])
        bluetooth=State(lambda:snapshot,lambda:True,lambda action:calls.append(action))
        title,entries=menu('bluetooth:open',bluetooth=bluetooth)
        self.assertIn('on',title)
        self.assertEqual([action for _,action in entries],['bt:controller_off','bt:receive_start','submenu:Airplane','window:Bluetooth'])
        self.assertEqual(calls,[])
    def test_offline_does_not_offer_hardware_commands(self):
        title,entries=menu('bluetooth:open',bluetooth=State())
        self.assertIn('unavailable',title)
        self.assertEqual(entries,[('Airplane mode…','submenu:Airplane'),('Open Bluetooth…','window:Bluetooth')])
    def test_battery_has_charge_state_and_staleness(self):
        system=SimpleNamespace(update=lambda:None,current={},result=dict(batteries=[dict(capacity_percent=71,status='Charging')],freshness='stale'))
        title,entries=menu('system:Battery',system=system)
        self.assertIn('71%',title);self.assertIn('Charging',title);self.assertIn('stale',title)
        self.assertIn(('Refresh status','system:refresh'),entries)
    def test_battery_and_power_offer_matching_policy_controls(self):
        for action in ('system:open','system:Battery','system:Power'):
            intents = {intent for _,intent in menu(action)[1]}
            self.assertTrue({'charge:topoff','charge:longevity','cpu:performance','cpu:balanced',
                             'cpu:save','submenu:Display'} <= intents)

    def test_repeat_adjustments_in_open_display_menu(self):
        import ast
        from unittest.mock import Mock,patch
        from launcher import Launcher
        from panel_tray import CONTROL_ACTIONS
        shell=Path(__file__).resolve().parents[1]/'shell'
        desktop=ast.parse((shell/'desktop.py').read_text())
        opener=next(n for n in ast.walk(desktop) if isinstance(n,ast.FunctionDef) and n.name=='open_tray')
        launcher=Launcher([])
        env=dict(launcher=launcher,context_commands={},panel=Mock(),args=SimpleNamespace(device_radio=False),
                 ox=0,oy=0,system_state=None,bluetooth_state=None,radio=None,
                 open_launcher=Mock(side_effect=lambda *_:launcher.open()))
        exec(compile(ast.Module(body=[opener],type_ignores=[]),'desktop.py','exec'),env)
        env['open_tray']('system:Display',(8,0))
        with patch('subprocess.run') as run:
            run.return_value.returncode=0
            for idx,(_,intent) in enumerate(menu('system:Display')[1]):
                env['context_commands'][launcher.pointer(idx,20)]()
                env['context_commands'][launcher.key('\r')]()
                self.assertEqual(run.call_args.args[0],CONTROL_ACTIONS[intent][0])
                self.assertTrue(launcher.active)
                self.assertEqual(launcher.index,idx)
            run.return_value.returncode=1
            run.return_value.stderr='Mixer unavailable'
            env['context_commands'][launcher.key('\r')]()
            self.assertIn('Mixer unavailable',launcher.lines()[0])
            self.assertTrue(launcher.active)
            launcher.key('\x1b')
            self.assertFalse(launcher.active)
            env['open_launcher'].assert_called_once()

    def test_network_menus_link_to_shared_airplane_control(self):
        for action in ('system:WiFi','bluetooth:open','radio:Radio'):
            self.assertIn(('Airplane mode…','submenu:Airplane'),menu(action)[1])

    def test_application_hits_do_not_become_tray_menus(self):
        for action in (None,'launch:window:Stations','key:,'):
            self.assertFalse(handles(action));self.assertIsNone(menu(action))
    def test_radio_read_commands_and_feedback(self):
        radio=SimpleNamespace(result={'statusbar':{'radio':{'state':'live'}}},read_message='Read accepted')
        title,entries=menu('radio:Radio',radio=radio)
        self.assertIn('Read accepted',title)
        self.assertIn(('Check read progress','radio:check'),entries)

if __name__=='__main__':unittest.main()
