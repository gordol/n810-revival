from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
class LazyStartupTests(unittest.TestCase):
    def test_closed_apps_are_not_imported_by_shell_startup(self):
        with tempfile.TemporaryDirectory() as temporary:
            script='''import json,runpy,sys
from pathlib import Path
root=Path(sys.argv[1]);state=Path(sys.argv[2]);sys.path.insert(0,str(root/'shell'))
sys.argv=[str(root/'shell/demo.py'),'--shell','--smoke','--app-state',str(state),'--station-db',str(state/'directory.sqlite3')]
runpy.run_path(sys.argv[0],run_name='__main__')
print(json.dumps(sorted(sys.modules)))
'''
            result=subprocess.run([sys.executable,'-c',script,str(ROOT),temporary],capture_output=True,text=True,timeout=float(os.environ.get('POCKET_STARTUP_TEST_TIMEOUT',20)))
            self.assertEqual(result.returncode,0,result.stderr)
            modules=json.loads(result.stdout.splitlines()[-1])
            for name in ('calendar','station_workspace','native_messages','native_feed','native_cw','audio_monitor','workbench_app','document_apps','model_scene','geometry','geometry_compute'):
                self.assertNotIn(name,modules)
    def test_runtime_records_do_not_import_class_generation_machinery(self):
        script="""import sys
sys.path.insert(0,sys.argv[1])
import app_registry,app_command,app_widgets,app_readiness,app_docks
import pointer_events,last_heard_model,native_feed,entity_actions
import connections,service_selection,device_radio_source
assert 'dataclasses' not in sys.modules
assert 'inspect' not in sys.modules
assert 'concurrent.futures' not in sys.modules
"""
        result=subprocess.run([sys.executable,'-c',script,str(ROOT/'shell')],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_calendar_is_loaded_when_its_view_is_opened(self):
        script="""import sys
sys.path.insert(0,sys.argv[1])
from widgets import CalendarView
assert 'calendar' not in sys.modules
view=CalendarView()
rows=view.lines(1767225600)
assert 'calendar' in sys.modules
assert rows and '2026' in rows[0]
assert view.key('right')
assert view.lines(1767225600)[0]!=rows[0]
"""
        result=subprocess.run([sys.executable,'-c',script,str(ROOT/'shell')],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_unused_scene_cache_and_font_preview_do_not_load_crypto(self):
        script="""import sys
sys.path.insert(0,sys.argv[1])
import scene_acceleration,font_preview
assert scene_acceleration.configure()['setup_fallback'] is None
assert 'hashlib' not in sys.modules
assert '_hashlib' not in sys.modules
"""
        result=subprocess.run([sys.executable,'-c',script,str(ROOT/'shell')],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_geometry_selection_is_deferred_until_a_geometry_consumer(self):
        script="""import sys
sys.path.insert(0,sys.argv[1])
import compute_runtime
compute_runtime.defer('python')
assert 'geometry_compute' not in sys.modules
import geometry_compute
assert compute_runtime.status()['selection']['requested']=='python'
assert compute_runtime.status()['selection']['selected']=='python'
compute_runtime.defer('existing')
assert compute_runtime.status()['selection']['selected']=='caller configured'
"""
        result=subprocess.run([sys.executable,'-c',script,str(ROOT/'shell')],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_lazy_form_preserves_source_pointer_metadata(self):
        from types import SimpleNamespace
        sys.path.insert(0,str(ROOT/'shell'))
        from app_registry import LazyApplication
        from pointer_events import PointerEvent,deliver_pointer
        form=LazyApplication.__new__(LazyApplication)
        received=[]
        form.owner=SimpleNamespace(pointer_event=lambda event,width:received.append((event,width)) or True)
        event=PointerEvent(('mouse',0,3,4,False))
        self.assertTrue(deliver_pointer(form,event,7,8,40))
        self.assertEqual(tuple(received[0][0]),('mouse',0,7,8,False))
        self.assertEqual(received[0][0].stamp,event.stamp)

    def test_last_heard_clicks_through_lazy_application(self):
        from types import SimpleNamespace
        sys.path.insert(0,str(ROOT/'shell'))
        from app_registry import LazyApplication
        from last_heard_view import LastHeard
        from pointer_events import deliver_pointer
        form=LazyApplication.__new__(LazyApplication)
        form.owner=LastHeard(lambda:None)
        event=('mouse',0,3,4,False)
        self.assertFalse(deliver_pointer(form,event,3,4,56))
        self.assertTrue(deliver_pointer(form,event,17,16,56))
        self.assertEqual(form.owner.mode,'selected')
        self.assertFalse(deliver_pointer(form,('mouse',0,3,4,True),2,16,56))
        self.assertTrue(deliver_pointer(form,event,2,16,56))
        self.assertEqual(form.owner.mode,'last')
        form.owner=SimpleNamespace()
        self.assertFalse(deliver_pointer(form,event,3,4,56))

if __name__=='__main__':unittest.main()
