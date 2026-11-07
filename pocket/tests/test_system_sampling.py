from pathlib import Path
import sys,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from device_radio_source import DeviceSource
from radio_state import State
from connections import Connections
from system_links import project

class SamplingTests(unittest.TestCase):
 def test_idle_local_samples_use_scheduler_without_refreshing_retained_files(self):
  now=[100.];calls=[]
  receive=SimpleNamespace(bind_wakeup=lambda cb:None,refresh=lambda:self.fail('Unnecessary feed refresh'),close=lambda:True,read=lambda now:dict(live=dict(data=dict(captured=None))))
  with tempfile.TemporaryDirectory() as home,patch('console_source.Source',return_value=receive):
   def collect():calls.append(now[0]);return dict(system=dict(observed_at=now[0],source='fixture'))
   source=DeviceSource(home=home,collector=collect);self.addCleanup(source.close)
   connection=Connections(Path(home)/'db',Path(home),Path(home));connection.source=source;source.bind_wakeup(connection.notify)
   state=State(source=connection,clock=lambda:now[0]);state.update()
   source.pending.result(3);source.files_pending.result(3)
   state.update();self.assertEqual(calls,[100.]);self.assertEqual(state.delay(),5.)
   now[0]=104.;state.update();self.assertEqual(calls,[100.])
   now[0]=105.;state.update();source.pending.result(3);state.update()
   self.assertEqual(calls,[100.,105.]);self.assertEqual(state.payload['live']['data']['system']['observed_at'],105.)
   self.assertIsNone(source.files_pending)
 def test_shared_observation_preserves_timestamp_and_fallback_recovers(self):
  source=DeviceSource.__new__(DeviceSource);fallback=[]
  source.collector=lambda:fallback.append(True) or {'local':True}
  publication=[dict(system=dict(source='nokia',observed_at=95))]
  source.shared_telemetry=lambda:publication[0]
  with patch('device_radio_source.time.time',return_value=100):
   self.assertIs(source._collect(),publication[0]);self.assertEqual(fallback,[])
   for bad in ({},[],dict(system=[]),dict(system=dict(source='nokia',observed_at=70)),dict(system=dict(source='nokia',observed_at=float('nan'))),dict(system=dict(source='nokia',observed_at=110))):
    publication[0]=bad;self.assertEqual(source._collect(),{'local':True})
   self.assertEqual(len(fallback),6)
   source.shared_telemetry=lambda:(_ for _ in ()).throw(ConnectionError('directory restarting'))
   self.assertEqual(source._collect(),{'local':True})
   publication[0]=dict(system=dict(source='nokia',observed_at=100))
   source.shared_telemetry=lambda:publication[0]
   self.assertIs(source._collect(),publication[0]);self.assertEqual(len(fallback),7)

 def test_links_use_current_observation_and_label_configured_bridge(self):
  first=project(dict(system=dict(observed_at=10),network=dict(wlan0='up')))
  self.assertTrue(first['links'][0]['connected'])
  second=project(dict(system=dict(observed_at=20),network=dict(wlan0='down')),dict(port='htit://AA:BB/1/CC:DD/1',owner_online=True,connection_state='online'))
  self.assertFalse(second['links'][0]['connected'])
  self.assertEqual(second['links'][2]['peer'],'AA:BB')
  self.assertEqual(second['links'][3]['peer'],'CC:DD')
  self.assertIn('unavailable',second['links'][2]['detail'])
  self.assertIsNone(second['links'][2]['connected'])
 def test_silent_catalogue_subscription_is_reopened_without_radio_reconnect(self):
  from device_connection import AttachedDevice
  closed=[]
  source=AttachedDevice.__new__(AttachedDevice)
  source._init_saved_radio()
  source._sample_due=30;source.catalogue={};source._wake=None
  source.catalogue_provider=SimpleNamespace(snapshot=lambda:dict(owner_online=True,telemetry=dict(system=dict(observed_at=1))),transport=SimpleNamespace(close=lambda:closed.append(True)),drain=lambda:None)
  source.receive=SimpleNamespace(read=lambda now:dict(live=dict(data={}),connector={}))
  source.read(29);self.assertEqual(closed,[])
  source.read(30);self.assertEqual(closed,[True]);self.assertEqual(source.delay(30),30)
  source.read(31);self.assertEqual(closed,[True])
  with patch('device_connection.time.time',return_value=40):source.notify()
  self.assertEqual(source.delay(40),30)
  source.gateway=object();self.assertIsNone(source.delay(100))

 def test_bridge_hop_states_expire_and_existing_profiles_survive(self):
  data=dict(connectivity=dict(version=1,profiles=[dict(id='saved')],links=[dict(id='wifi-ibss',connected=True)]))
  owner=dict(port='htit://AA/1/BB/1',owner_online=True,connection_state='online',bridge=dict(kind='htit',phase='online',observed_at=100,classic_connected=True,ble_connected=True,ble_ready=True,mtu=247,owner=1))
  fresh=project(data,owner,now=105);rows={r['id']:r for r in fresh['links']}
  self.assertEqual(fresh['profiles'],data['connectivity']['profiles']);self.assertTrue(rows['wifi-ibss']['connected'])
  self.assertTrue(rows['htit-classic']['connected']);self.assertTrue(rows['htit-ble']['connected']);self.assertIn('247',rows['htit-classic']['detail'])
  stale={r['id']:r for r in project(data,owner,now=116)['links']}
  self.assertIsNone(stale['htit-classic']['connected']);self.assertIn('stale',stale['htit-classic']['detail'])
  owner['bridge']['phase']='stopped'
  stopped={r['id']:r for r in project(data,owner,now=117)['links']}
  self.assertFalse(stopped['htit-classic']['connected']);self.assertIsNone(stopped['htit-ble']['connected'])

 def test_visible_system_age_advances_without_new_sample(self):
  from system_view import State as SystemState,System
  now=[100.]
  connector=SimpleNamespace(payload=dict(live=dict(data=dict(system=dict(source='nokia',observed_at=100)))))
  state=SystemState(connector,clock=lambda:now[0]);view=System(state)
  self.assertIn('Sample age: 0s',' '.join(view.lines()))
  now[0]=110.
  self.assertIn('Sample age: 10s',' '.join(view.lines()))
  self.assertEqual(view.presentation_interval(),1.)

 def test_owner_error_snapshot_retains_recovery_actions(self):
  from app_registry import Registry
  import importlib
  root=Path(__file__).resolve().parents[1]/'shell'
  Registry(root).configure_reticulum(register=False)
  wire=importlib.import_module('_pocket_reticulum_'+str(abs(hash(str((root/'vendor/apps/domains/reticulum').resolve()))))+'.wire')
  snapshot=dict(version=1,owner_online=True,error='Contact query failed',capabilities=['connect'])
  self.assertEqual(wire.decode(wire.encode(snapshot)),snapshot)
  with self.assertRaisesRegex(ValueError,'denied'):wire.decode(wire.encode(dict(version=1,error='denied')))

 def test_system_diagnostic_reads_publication_without_triggering_sample(self):
  from desktop_actions import dispatch
  state=SimpleNamespace(result=dict(sample_age_seconds=200),current=dict(connectivity=dict(version=1)),attachment={},update=lambda:self.fail('Diagnostic must not refresh'))
  host=SimpleNamespace(app_forms={'System':SimpleNamespace(state=state)})
  result=dispatch(host,None,{},dict(command='system-status'))
  self.assertEqual(result['system']['sample_age_seconds'],200)

 def test_visible_form_clock_does_not_poll_unrelated_applications(self):
  import textwrap
  source=(Path(__file__).resolve().parents[1]/'shell/desktop.py').read_text()
  start=source.index('                for index,application in enumerate(applications):',source.index('            owner_delays={}'))
  end=source.index('                if radio and ',start)
  scheduled={}
  form=SimpleNamespace(presentation_interval=lambda:1.)
  host=SimpleNamespace(app_forms={'System':form},window=lambda name:SimpleNamespace(rolled=False),shown=lambda window:True)
  environment=dict(applications=[SimpleNamespace(poll_interval=lambda:None)],host=host,metrics=None,model_intervals=None,timeout=None,owner_delay=lambda owner,delay:scheduled.update({owner:delay}))
  exec(compile(textwrap.dedent(source[start:end]),'desktop-timers','exec'),environment)
  self.assertEqual(scheduled,{'form:System':1.})
  host.shown=lambda window:False;scheduled.clear()
  exec(compile(textwrap.dedent(source[start:end]),'desktop-timers','exec'),environment)
  self.assertEqual(scheduled,{})
