import copy
import json
from pathlib import Path
import unittest
from feed_control import Intent
from test_telemetry_events import telemetry_type


def producer_fixture():
    cls, scope = telemetry_type()
    writes = []
    scope.update(copy=copy, atomic=lambda path,value:writes.append(copy.deepcopy(value)))
    owner = cls.__new__(cls)
    owner.path = Path('unused-fixture')
    owner._published = None
    owner.read_session = None
    owner.state = {'version':2,'connected':True,'connection_observed_at':100,
                   'fields':{'status':100},'status':{'sample':42}}
    owner.publish()
    return owner, scope, writes


def compatibility_fixtures():
    telemetry, _scope, writes = producer_fixture()
    owner = Intent()
    owner.observe_controller({'available':True,'powered':True,'devices':[],'error':None})
    owner.observe_radio(True, observed_at=100)
    live = owner.snapshot()
    disconnected = copy.deepcopy(live)
    owner.observe_radio(False, observed_at=1100)
    disconnected = owner.snapshot()
    return [
        {'name':'quiet_connected','now':1000,'transport_connected':True,'subscribed_on_this_stream':True,
         'live_state':live,'disk_telemetry':writes[0],'expected_owner':'available','expected_radio':True},
        {'name':'disconnected','now':1100,'transport_connected':True,'subscribed_on_this_stream':True,
         'live_state':disconnected,'disk_telemetry':writes[0],'expected_owner':'available','expected_radio':False},
        {'name':'dead_owner','now':1100,'transport_connected':False,'subscribed_on_this_stream':False,
         'live_state':live,'disk_telemetry':writes[0],'expected_owner':'unavailable','expected_radio':None},
        {'name':'retained_only','now':1100,'transport_connected':False,'subscribed_on_this_stream':False,
         'live_state':None,'retained_state':live,'disk_telemetry':writes[0],
         'expected_owner':'unknown','expected_radio':None},
    ]


class ObservationContractTests(unittest.TestCase):
    def test_quiet_publication_does_not_retimestamp_facts(self):
        owner, scope, writes = producer_fixture()
        self.assertEqual(writes[0]['version'],2)
        self.assertNotIn('heartbeat',writes[0])
        self.assertEqual(writes[0]['published_at'],1000)
        self.assertEqual(writes[0]['fields']['status'],100)
        scope['time'].time=lambda:2000
        owner.publish()
        self.assertEqual(len(writes),1)
        self.assertEqual(owner.state['connection_observed_at'],100)

    def test_owner_identity_and_radio_observation_are_separate(self):
        owner=Intent();owner.observe_radio(True,observed_at=100)
        first=owner.snapshot()
        owner.action('receive_stop');owner.stopping=True
        second=owner.snapshot()
        self.assertEqual(first['owner'],second['owner'])
        self.assertEqual(second['owner']['context'],'live_owner')
        self.assertEqual(second['radio']['observed_at'],100)
        self.assertTrue(second['radio']['connected'])
        owner.observe_radio(False,observed_at=1100)
        self.assertEqual(owner.snapshot()['radio']['observed_at'],1100)
        self.assertNotEqual(owner.instance_id,Intent().instance_id)

    def test_four_consumer_fixture_cases_are_produced(self):
        cases=compatibility_fixtures()
        self.assertEqual([c['name'] for c in cases],['quiet_connected','disconnected','dead_owner','retained_only'])
        self.assertEqual(cases[0]['live_state']['radio']['observed_at'],100)
        self.assertEqual(cases[0]['disk_telemetry']['fields']['status'],100)
        self.assertFalse(cases[1]['live_state']['radio']['connected'])
        self.assertFalse(cases[2]['transport_connected'])
        self.assertIsNone(cases[3]['live_state'])


if __name__=='__main__':
    Path(__file__).with_name('COMPATIBILITY-FIXTURES.json').write_text(json.dumps(compatibility_fixtures(),indent=2)+'\n')
    unittest.main()
