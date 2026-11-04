from pathlib import Path
import importlib
import subprocess
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SHELL=Path(__file__).resolve().parents[1]/'shell'
sys.path.insert(0,str(SHELL))
from app_registry import Registry
from connections import Connections
from service_selection import Selection
from device_connection import AttachedDevice

class DeviceTests(unittest.TestCase):
    def wait(self,condition):
        deadline=time.monotonic()+8
        while not condition():
            if time.monotonic()>deadline:self.fail('Device publication timed out')
            time.sleep(.01)
    def test_group_attachment_telemetry_and_owner_use_binary_subscription(self):
        with tempfile.TemporaryDirectory(dir='/tmp',prefix='pd-') as temp:
            root=Path(temp);registry=Registry(SHELL)
            script='''import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from owner import Owner,serve
class Device(Owner):
 def snapshot(self):return dict(version=1,owner_online=True,device='test-device',services=[dict(id='system',available=True),dict(id='reticulum',available=True)],telemetry=dict(system=dict(source='test-device',observed_at=1,memory_bytes=dict(total=128))))
serve(Path(sys.argv[2])/'system.sock',Path(sys.argv[2])/'state','test',owner_factory=Device)
'''
            process=subprocess.Popen([sys.executable,'-c',script,str(SHELL/'vendor/apps/domains/reticulum'),str(root)])
            self.addCleanup(lambda:process.poll() is None and (process.terminate(),process.wait(5)))
            self.wait(lambda:(root/'system.sock').exists())
            receive=SimpleNamespace(bind_wakeup=lambda cb:None,refresh=lambda:None,close=lambda:None,
                read=lambda now:dict(live=dict(data=dict(receive_connected=False)),connector={}))
            source=AttachedDevice(receive,registry,{'system':root/'system.sock','reticulum':root/'system.sock'},dict(device='test-device'),'test')
            connection=Connections(root/'db',SHELL/'vendor/packet-console',root/'runtime',lambda *_:(source,'test-device'))
            selection=Selection(registry,root);connection.reticulum=selection
            self.addCleanup(selection.close);self.addCleanup(connection.close)
            connection.connect('ssh','test')
            self.wait(lambda:connection.source is source and connection.read(0)['connector'].get('device',{}).get('connected'))
            payload=connection.read(0)
            self.assertEqual(payload['live']['data']['system']['source'],'test-device')
            self.assertTrue(payload['connector']['attachment']['connected'])
            self.assertFalse(payload['live']['data']['receive_connected'])
            self.wait(lambda:selection.snapshot().get('owner_online'))
            self.assertEqual(selection.label,'test-device')
            connection.disconnect();self.assertIsNone(selection.provider)
            connection.close();selection.close()
            process.terminate();process.wait(5)

    def test_local_telemetry_uses_private_binary_directory_without_owner_start(self):
        import socket,threading
        from device_connection import local_telemetry
        registry=Registry(SHELL);registry.configure_reticulum(register=False)
        package='_pocket_reticulum_'+str(abs(hash(str((SHELL/'vendor/apps/domains/reticulum').resolve()))))
        wire=importlib.import_module(package+'.wire')
        with tempfile.TemporaryDirectory(dir='/tmp',prefix='pt-') as temp:
            root=Path(temp);seen=[]
            with socket.socket(socket.AF_UNIX) as server:
                server.bind(str(root/'owner.sock'));server.listen(1);server.settimeout(3)
                def respond():
                    with server.accept()[0] as peer:
                        seen.append(wire.read_socket(peer))
                        peer.sendall(wire.encode(dict(version=1,owner_online=True,telemetry=dict(system=dict(source='fixture',observed_at=123)))))
                worker=threading.Thread(target=respond);worker.start()
                collect=local_telemetry(registry,root)
                self.assertEqual(collect(),dict(system=dict(source='fixture',observed_at=123)))
                worker.join(3);self.assertFalse(worker.is_alive())
            self.assertEqual(seen,[dict(version=1,action='snapshot',scope='directory')])
            root.chmod(0o755)
            with self.assertRaisesRegex(ValueError,'Unsafe'):collect()

    def test_ssh_attachment_forwards_starting_service_before_radio_readiness(self):
        from device_connection import attach
        from device_services import encode
        with tempfile.TemporaryDirectory(dir='/tmp',prefix='pd-') as temp:
            directory=Path(temp);registry=Registry(SHELL)
            catalogue=dict(version=1,socket='/tmp/device/owner.sock',services=[
                dict(id='system',available=True,state='ready'),
                dict(id='reticulum',available=False,state='starting',socket='/tmp/rns/owner.sock'),
                dict(id='unregistered',available=True,socket='/tmp/other.sock')])
            calls=[]
            def run(command,timeout):
                calls.append(command)
                return SimpleNamespace(returncode=0,stdout=encode(catalogue) if '--ensure' in command[-1] else b'',stderr=b'')
            class Bundle:
                def __init__(self,receive,registry,endpoints,catalogue,target):self.endpoints=endpoints
            with patch('receive_bridge._run',side_effect=run),patch('device_connection.AttachedDevice',Bundle):
                bundle=attach(directory,'selected-host',registry,lambda:None)
            self.assertEqual(set(bundle.endpoints),{'system','reticulum','radio-control'})
            forwards=[call for call in calls if 'forward' in call]
            self.assertEqual(len(forwards),3)
            self.assertTrue(any('/tmp/rns/owner.sock' in part for call in forwards for part in call))

    def test_ssh_reattachment_reuses_forwarded_directory_without_remote_helper(self):
        from device_connection import attach
        import socket
        with tempfile.TemporaryDirectory(dir='/tmp',prefix='pd-') as temp:
            directory=Path(temp);registry=Registry(SHELL)
            registry.configure_reticulum(register=False)
            package='_pocket_reticulum_'+str(abs(hash(str((registry.root/'vendor/apps/domains/reticulum').resolve()))))
            protocol=importlib.import_module(package+'.owner')
            from receive_bridge import _write
            _write(directory/'services.json',{'system':'/tmp/device/owner.sock','radio-control':'/dev/shm/n810-radio-read/control.sock'})
            with socket.socket(socket.AF_UNIX) as listener:
                listener.bind(str(directory/'system.sock'))
                (directory/'system.sock').chmod(0o600)
                extra=socket.socket(socket.AF_UNIX);extra.bind(str(directory/'radio-control.sock'));extra.close()
                (directory/'radio-control.sock').chmod(0o600)
                class Bundle:
                    def __init__(self,*args):pass
                reply=dict(version=1,owner_online=True,services=[dict(id='system',state='ready')])
                with patch.object(protocol,'exchange',return_value=reply) as exchange,patch('receive_bridge._run') as run,patch('device_connection.AttachedDevice',Bundle):
                    attach(directory,'selected-host',registry,lambda:None)
                    run.assert_not_called()
                    self.assertEqual(exchange.call_args.args[1]['scope'],'directory')

    def test_late_feed_notification_after_catalogue_close_is_harmless(self):
        source=AttachedDevice.__new__(AttachedDevice)
        def closed():raise OSError('descriptor closed')
        source.catalogue_provider=SimpleNamespace(drain=closed)
        source._wake=lambda:self.fail('Woke a closed connection')
        source.notify()

    def test_disconnect_preserves_independently_selected_owner(self):
        with tempfile.TemporaryDirectory() as temp:
            connection=Connections(Path(temp)/'db',SHELL/'vendor/packet-console',Path(temp)/'runtime')
            first=object();replacement=object()
            selection=SimpleNamespace(provider=replacement,disconnect=lambda:self.fail('Detached independently selected owner'))
            connection.reticulum=selection
            connection._detach_bindings(SimpleNamespace(adopted={'reticulum':first}))
            connection.close()
