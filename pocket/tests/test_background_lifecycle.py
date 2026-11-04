"""Disabling a loading scene must repaint even before its first base frame."""
import sys,unittest
import subprocess
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host
from concurrent.futures import Future
from types import SimpleNamespace
from paint import Scene

class BackgroundLifecycle(unittest.TestCase):
 def test_effect_worker_does_not_import_terrain_and_keeps_one_job(self):
  code='''import sys
from frame_worker import Renderer
r=Renderer();key=(20,8,False,'flux',0,None,1,0)
r.effect_frame(key,lambda *args:())
r.pending.result(timeout=3)
assert r.effect_frame(key,lambda *args:())==()
assert r.pending is None and r.trace.progress()['completed']==1
assert not {'model_scene','geometry','landscape_detail'}&set(sys.modules)
r.close()
'''
  subprocess.run([sys.executable,'-c',code],cwd=Path(__file__).resolve().parents[1]/'shell',check=True,timeout=30)
 def test_flux_consumes_completion_without_waiting_for_another_clock_step(self):
  host=Host(20,8,[],clock=lambda:.005);host.effect_epoch=0
  host.set_effect('flux');host.background_enabled=True;host.background_async=True;host.background_step=0
  future=Future();scene=Scene({},{(1,1):('x',0)})
  renderer=SimpleNamespace(pending=future,fx_completed=((20,8,False,'flux',0),scene))
  def ready(key,prepare):renderer.pending=None;return scene
  renderer.effect_frame=Mock(side_effect=ready);host.terrain_renderer=renderer
  self.assertIsNone(host.background_delay())
  future.set_result(scene);self.assertEqual(host.background_delay(),0)
  host.tick()
  renderer.effect_frame.assert_called_once()
  self.assertIs(host._effect_scene,scene)
  host.damage.clear();host._flux_painted(.001)
  self.assertAlmostEqual(host.background_delay(),1/30-.005)

 def test_flux_budget_accounts_for_generation_and_drawing_without_polling(self):
  clock=[.1];host=Host(20,8,[],clock=lambda:clock[0]);host.set_effect('flux')
  host.background_enabled=True;host.background_async=True;host.damage.clear()
  host.effect_frame_id=(1,'flux',0.);host._flux_started=0.;host._flux_generation_cpu=.05
  host._flux_painted(.04)
  self.assertAlmostEqual(host.background_delay(),.08)
  host.background_step=0.;host.terrain_renderer=SimpleNamespace(pending=None,effect_frame=Mock())
  host.tick();host.terrain_renderer.effect_frame.assert_not_called()
  host._flux_painted(.5)
  self.assertAlmostEqual(host.background_delay(),.08)

 def test_fast_demo_is_explicit_and_does_not_change_scene_quality(self):
  host=Host(20,8,[],clock=lambda:.1);host.set_effect('flux');host.background_enabled=True;host.damage.clear()
  self.assertEqual(host.flux_performance,'balanced')
  quality=(host.flux_density,host.flux_glow,host.flux_arms)
  from controls import scene_controls
  pace=scene_controls(host)['flux'][0];pace.adjust(1)
  self.assertEqual(host.flux_performance,'fast demo');host.damage.clear()
  host.effect_frame_id=(1,'flux',0.);host._flux_started=0.;host._flux_generation_cpu=.05
  host._flux_painted(.04)
  self.assertAlmostEqual(host.background_delay(),.09/.65-.1)
  self.assertEqual((host.flux_density,host.flux_glow,host.flux_arms),quality)
  pace.adjust(-1);self.assertEqual(host.flux_performance,'balanced')

 def test_flux_finer_cadence_retains_original_animation_speed(self):
  clock=[0.];host=Host(20,8,[],clock=lambda:clock[0]);host.effect_epoch=0
  host.set_effect('flux');host.background_enabled=True;host.background_async=True
  steps=[];renderer=SimpleNamespace(pending=None)
  def ready(key,prepare):
   steps.append(key[4]);scene=Scene({},{})
   renderer.fx_completed=(key,scene);return scene
  renderer.effect_frame=ready;host.terrain_renderer=renderer
  for stamp in (0.,1/30+.001,1/6+.001):clock[0]=stamp;host.tick()
  self.assertEqual(steps,[0.,.2,1.])

 def test_flux_does_not_schedule_background_wakes_during_menu_or_drag(self):
  host=Host(20,8,[]);host.set_effect('flux');host.background_enabled=True
  host.launcher_lines=['menu'];self.assertIsNone(host.background_delay())
  host.launcher_lines=[];host.drag=('window',);self.assertIsNone(host.background_delay())

 def test_disable_cancels_and_damages_empty_loading_background(self):
  host=Host(20,8,[])
  host.background_enabled=True;host.terrain_loading=True
  host.terrain_renderer=Mock();host.backdrop={}
  host.damage.clear();host.ui_damage.clear()
  host.set_background_enabled(False)
  host.terrain_renderer.suspend.assert_called_once()
  self.assertFalse(host.terrain_loading)
  self.assertEqual(set(host.damage),set(range(160)))

 def test_hiding_scenery_suspends_its_independent_renderer(self):
  from scenery_app import SceneryApp
  app=SceneryApp.__new__(SceneryApp);app._active=True;app._initialized=True
  app.renderer=Mock();app._layer=object();app._display=object()
  app.set_active(False)
  app.renderer.suspend.assert_called_once()
  self.assertIsNone(app._layer)
