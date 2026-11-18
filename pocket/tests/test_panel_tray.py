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
