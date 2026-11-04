import ast
from pathlib import Path
import struct
import types
import unittest
from unittest import mock
from control_changes import ControlChanges


def telemetry_type():
    tree=ast.parse(Path(__file__).with_name('n810-radio-live.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Telemetry')
    scope={'STATE':Path('state'),'CONTROL':Path('control'),'GPS_CONTROL':Path('gps'),
           'time':types.SimpleNamespace(monotonic=lambda:100, time=lambda:1000),
           'read':lambda path: {},'request':lambda command,payload=b'':(command,payload)}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual telemetry scheduling>','exec'),scope)
    return scope['Telemetry'],scope


class TelemetryEventTests(unittest.TestCase):
    def owner(self):
        cls,scope=telemetry_type();owner=cls.__new__(cls)
        owner.read_session=None;owner.bandwidth=None;owner.bandwidth_requested=False
        owner.control=Path('control');owner.gps_control=Path('gps');owner.gps_until=None
        owner.pending={};owner.due={};owner.subscribed=False
        owner.state={'enabled':False,'gps_enabled':False,'requests':0}
        owner.send=mock.Mock();owner.publish=mock.Mock()
        return owner,scope

    def test_idle_has_no_deadline_or_file_reads(self):
        owner,scope=self.owner();scope['read']=mock.Mock(side_effect=AssertionError('idle file poll'))
        self.assertIsNone(owner.next_deadline(100))
        owner.tick(100)
        owner.send.assert_not_called();scope['read'].assert_not_called()
        self.assertIsNone(owner.next_deadline(100))

    def test_explicit_control_event_arms_real_schedules(self):
        owner,scope=self.owner();scope['read']=mock.Mock(return_value={'enabled':True})
        owner.refresh_controls({owner.control},100,1000)
        scope['read'].assert_called_once_with(owner.control)
        self.assertEqual(owner.next_deadline(100),0)
        owner.tick(100)
        self.assertEqual(owner.due,{20:110,10:130,33:160})
        self.assertEqual(owner.next_deadline(100),105)
        owner.tick(105)
        self.assertEqual(owner.next_deadline(105),110)
        self.assertEqual(scope['read'].call_count,1)

    def test_gps_lease_expiry_disarms_sends(self):
        owner,scope=self.owner();scope['read']=lambda _: {'until':1012}
        owner.refresh_controls({owner.gps_control},100,1000);owner.tick(100)
        self.assertEqual(owner.gps_until,112)
        owner.tick(112)
        self.assertFalse(owner.state['gps_enabled'])
        self.assertIsNone(owner.next_deadline(112))

    def test_explicit_read_waits_for_reply_or_its_timeout(self):
        owner,_=self.owner()
        owner.read_session=types.SimpleNamespace(state='reading',pending=20,sent=99,started=98)
        self.assertEqual(owner.next_deadline(100),104)
        owner.read_session.state='cancelled'
        owner.read_session.next=lambda now:None
        owner.tick(104)
        self.assertIsNone(owner.read_session.pending)
        self.assertIsNone(owner.next_deadline(104))

    def test_bandwidth_only_arms_while_requested_or_active(self):
        owner,_=self.owner()
        owner.bandwidth=types.SimpleNamespace(active=False,waiting=None)
        self.assertIsNone(owner.next_deadline(100))
        owner.bandwidth_requested=True
        self.assertEqual(owner.next_deadline(100),100)
        owner.bandwidth_requested=False;owner.bandwidth.active=True;owner.bandwidth.quiet_until=102
        self.assertEqual(owner.next_deadline(100),102)
        owner.bandwidth.waiting=('status',20);owner.bandwidth.deadline=106
        self.assertAlmostEqual(owner.next_deadline(100),106.000001)

    def test_inotify_overflow_rescans_controls_and_watch_loss_fails(self):
        watch=ControlChanges.__new__(ControlChanges)
        watch.paths={Path('/dev/shm/control')};watch.directories={1:Path('/dev/shm')};watch.fd=3
        with mock.patch('control_changes.os.read',side_effect=[struct.pack('iIII',-1,0x4000,0,0),BlockingIOError]):
            self.assertEqual(watch.drain(),watch.paths)
        with mock.patch('control_changes.os.read',return_value=struct.pack('iIII',1,0x8000,0,0)):
            with self.assertRaisesRegex(OSError,'watch lost'):watch.drain()


if __name__=='__main__':unittest.main()
