from pathlib import Path
import sys
import unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from service_catalog import OWNER_IDS,owner_factory
from app_registry import Registry

class ServiceCatalogTests(unittest.TestCase):
    def test_remote_names_cannot_choose_arbitrary_factories(self):
        registry=SimpleNamespace(configure_reticulum=object(),configure_meshcore=object())
        self.assertIs(owner_factory(registry,'reticulum'),registry.configure_reticulum)
        self.assertIs(owner_factory(registry,'meshcore'),registry.configure_meshcore)
        for name in ('__dict__','open','system','unknown'):
            with self.assertRaises(ValueError):owner_factory(registry,name)

    def test_app_dependency_action_opens_matching_owner_controls(self):
        registry=Registry();opened=[];selected=[]
        registry.entries['connections']=SimpleNamespace(title='Connections')
        registry.forms['Connections']=SimpleNamespace(owner=SimpleNamespace(select_service=lambda name:selected.append(name) or True))
        registry.open=opened.append
        for service in (*OWNER_IDS,'receive'):self.assertTrue(registry.open_service(service))
        self.assertEqual(selected,['reticulum','meshcore','receive'])
        self.assertEqual(opened,['connections']*3)
        self.assertFalse(registry.open_service('map-open'))
        self.assertEqual(len(opened),3)

if __name__=='__main__':unittest.main()
