import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell'))
from app_registry import Registry,validate_reticulum_selection
spec=importlib.util.spec_from_file_location('carrier_config_test',ROOT/'shell/vendor/apps/domains/reticulum/carriers.py')
carriers=importlib.util.module_from_spec(spec);spec.loader.exec_module(carriers)

class CarriersTests(unittest.TestCase):
    def test_all_carriers_render_and_no_automatic_connections(self):
        specs=[{'type':'tcp-client','host':'example.test','port':4242},
               {'type':'tcp-server','host':'127.0.0.1','port':4242},
               {'type':'lan','devices':['en0']},
               *[dict(type=kind,port='/dev/ttyUSB0') for kind in ('serial','usb','bluetooth','kiss')],
               dict(type='ax25',port='/dev/ttyUSB0',callsign='N0CALL')]
        config=carriers.configuration(specs)
        for kind in set(carriers.TYPES.values()):self.assertIn('type = '+kind,config)
        for key in ('enable_transport','share_instance','discover_interfaces','enable_remote_management'):
            self.assertIn(key+' = No',config)
        self.assertNotIn('Plain',config)
    def test_malformed_profiles_and_injection_fail_closed(self):
        for specs in ([],[{'type':'tcp-client','host':'host\n[interfaces]','port':1}],
                      [{'type':'serial','port':'/dev/../tmp/device'}],
                      [{'type':'serial','port':'/dev/ttyUSB0','speed':True}],
                      [{'type':'lan','devices':[]}],
                      [{'type':'ax25','port':'/dev/ttyUSB0','callsign':'bad call'}],
                      [{'type':'tcp-client','host':'host','port':1,'encryption':False}]):
            with self.subTest(specs=specs),self.assertRaises(ValueError):carriers.configuration(specs)
    def test_carrier_selection_reaches_existing_provider_framework(self):
        selection=validate_reticulum_selection(dict(mode='local',state='/tmp/state',interpreter=sys.executable,
                  station='test',carriers=[dict(type='serial',port='/dev/ttyUSB0')]))
        registry=Registry();registry.configure_reticulum()
        package='_pocket_reticulum_'+str(abs(hash(str((ROOT/'shell/vendor/apps/domains/reticulum').resolve()))))
        import importlib
        provider=importlib.import_module(package+'.provider')
        with patch.object(provider,'CarrierProvider') as factory:
            result=registry.configure_reticulum(local_state=selection['state'],local_options={k:v for k,v in selection.items() if k not in ('mode','state')},register=False)
            self.assertIs(result,factory.return_value)
            self.assertEqual(factory.call_args.kwargs['carriers'],selection['carriers'])

    def test_native_carrier_capabilities_do_not_silently_ignore_routing(self):
        for kind in ('tcp-client','tcp-server','serial','usb','bluetooth','kiss'):
            carriers.validate_native([dict(type=kind)])
        for specs,relay in (([dict(type='kiss')],True),([dict(type='lan')],False),
                            ([dict(type='ax25')],False),([dict(type='serial')]*2,False)):
            with self.assertRaises(ValueError):carriers.validate_native(specs,relay)

if __name__=='__main__':unittest.main()
