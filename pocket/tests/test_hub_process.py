"""Real owner process, subscriptions, attachment EOF and OS PTY isolation."""
import os,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell'))
from vendor.apps.domains.meshcore import hub_provider as hub
from vendor.apps.domains.reticulum.local_owner import ManagedOwner,stop_process

class ProcessTests(unittest.TestCase):
    def wait(self,predicate):
        until=time.monotonic()+8
        while time.monotonic()<until:
            if predicate():return
            time.sleep(.02)
        self.fail('Owner state not reached')
    def test_one_owner_two_services_eof_does_not_close_other_service(self):
        def managed(path,identity,plan):
            def fixture_plan():
                command,validate=plan();command[2]=str(ROOT/'tests/fixtures/hub_owner_fixture.py')
                return command,validate
            return ManagedOwner(path,identity,fixture_plan)
        with tempfile.TemporaryDirectory() as tmp,patch.object(hub,'ManagedOwner',managed):
            a=hub.HubProvider('/dev/fakehub',directory=tmp)
            b=hub.HubProvider('/dev/fakehub',directory=tmp)
            mesh=radio=None
            try:
                a.wait(lambda s:s.get('owner_online'),8)
                self.assertEqual(a.snapshot()['connection_state'],'idle')
                self.assertEqual(a.snapshot()['generation'],0)
                mesh=a.attach(1,ble='11:22:33:44:55:66',address_type=1,timeout=8)
                radio=b.attach(3,timeout=8)
                self.assertEqual(a.snapshot()['instance'],b.snapshot()['instance'])
                instance=radio.instance;generation=radio.generation
                mesh.close();mesh=None
                self.wait(lambda:not any(v['service']==1 for v in b.snapshot()['attachments']))
                self.assertEqual(radio.snapshot()['connection_state'],'online')
                self.assertEqual(radio.generation,generation)
                self.assertEqual(radio.instance,instance)
                self.assertTrue(os.path.exists(radio.port))
                c=hub.HubProvider('/dev/fakehub',directory=tmp)
                mesh=c.attach(1,ble='11:22:33:44:55:66',address_type=1,timeout=8)
                self.assertEqual(mesh.instance,instance)
                self.assertEqual(mesh.generation,generation)
                radio.close();radio=None
                self.wait(lambda:not any(v['service']==3 for v in c.snapshot()['attachments']))
                self.assertEqual(mesh.snapshot()['connection_state'],'online')
            finally:
                for attachment in (mesh,radio):
                    if attachment:attachment.close()
                for provider in (a,b):provider.close()
                # Managed owners intentionally survive consumers. Stop only this fixture.
                for provider in (a,b):
                    if provider.transport.process is not None:stop_process(provider.transport.process)

if __name__=='__main__':unittest.main()
