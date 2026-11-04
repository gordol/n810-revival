"""Start the existing HTIT attachment worker before importing the radio SDK."""
import asyncio,importlib.util,sys,threading,types,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]/'shell'
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('overlap_serial_client',ROOT/'vendor/apps/domains/meshcore/serial_client.py')
serial=importlib.util.module_from_spec(spec);spec.loader.exec_module(serial)

class OverlapTests(unittest.TestCase):
 def check(self,failed):
  started=threading.Event();closed=[]
  class Connection:
   class MCSerialClientProtocol:pass
   def __init__(self,*args):self.transport=None
   async def disconnect(self):pass
  class Client:
   def __init__(self,connection,**options):self.connection=connection
   async def connect(self):return True
   async def disconnect(self):await self.connection.disconnect()
  def sdk_attribute(name):
   if name!='MeshCore':raise AttributeError(name)
   self.assertTrue(started.wait(2),'SDK import blocked hub attachment from starting')
   if failed:raise ImportError('SDK fixture failure')
   return Client
  sdk=types.ModuleType('meshcore');sdk.__getattr__=sdk_attribute
  cx=types.ModuleType('meshcore.serial_cx');cx.SerialConnection=Connection
  attachment=types.SimpleNamespace(port='/dev/pts/99',closed=False,provider=types.SimpleNamespace(bind_wakeup=lambda callback:None),
   snapshot=lambda:dict(connection_state='online',hub_id='test',generation=1,attachments=[]),close=lambda:closed.append(True))
  hub=types.ModuleType('vendor.apps.domains.meshcore.hub_provider')
  def attach(*args,**kwargs):started.set();return attachment
  hub.attach_hub=attach
  async def exercise():
   if failed:
    with self.assertRaisesRegex(ImportError,'SDK fixture failure'):
     await serial.create_serial_client('htit://2C:BC:BB:9F:DF:72/1/FB:91:48:2D:AA:14/1')
   else:
    client=await serial.create_serial_client('htit://2C:BC:BB:9F:DF:72/1/FB:91:48:2D:AA:14/1')
    await client.disconnect()
  with patch.dict(sys.modules,{'meshcore':sdk,'meshcore.serial_cx':cx,'vendor.apps.domains.meshcore.hub_provider':hub}):asyncio.run(exercise())
  self.assertEqual(closed,[True])
 def test_hub_starts_while_sdk_imports(self):self.check(False)
 def test_sdk_import_failure_releases_attachment(self):self.check(True)

if __name__=='__main__':unittest.main()
