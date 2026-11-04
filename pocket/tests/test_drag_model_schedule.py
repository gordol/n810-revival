"""Drag scheduling: exact loop statements and a real PTY/source-loop fixture."""
import ast,fcntl,json,os,pty,select,signal,struct,subprocess,sys,tempfile,termios,textwrap,time,types,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from core import Host,Window
from model_deadlines import ModelDeadlines
ROOT=Path(__file__).resolve().parents[1]/'shell'
TEXT=(ROOT/'desktop.py').read_text();TREE=ast.parse(TEXT)
start=TEXT.index('            view=(host.desktop,host.focus,host.overview,host.screensaver,host.mouse_trails)')
end=TEXT.index('            model_start=',start)
DECISION=compile(textwrap.dedent(TEXT[start:end]),'demo.py','exec')
OVERRIDE=next(n for n in ast.walk(TREE) if isinstance(n,ast.If) and 'launcher.active'==ast.unparse(n.test) and any('timeout' in ast.unparse(x) for x in n.body) and n.orelse and 'model_deferred' in ast.unparse(n.orelse[0].test))
CONTINUE=next(n for n in ast.walk(TREE) if isinstance(n,ast.If) and any(isinstance(x,ast.Continue) for x in n.body) and 'due_owners' in ast.unparse(n.test))
RESET=next(n for n in ast.walk(TREE) if isinstance(n,ast.If) and ast.unparse(n.test)=='not host.drag or full_models')
def code(nodes):return compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),'demo.py','exec')
class ScheduleTests(unittest.TestCase):
 def env(self,due=(),held=True,latest=False):
  host=Host(100,30,[Window('one',3,3,40,12)],move_mode='outline');host.background_enabled=False;host.shadow_enabled=False;host.animate=False
  host.flush(3000)
  if held:host.begin();host.flush(3000)
  if latest:host.motion(4,2)
  schedule=ModelDeadlines();schedule.deadlines={owner:0. for owner in due}
  return dict(keyboard_router=None,sync_keyboard=lambda:None,host=host,radio=None,model_schedule=schedule,time=time,first_frame=False,model_inputs=True,model_full_deferred=False,resized=False,model_view=(host.desktop,host.focus,host.overview,host.screensaver,host.mouse_trails),model_deferred=False,launcher=types.SimpleNamespace(active=False,lines=lambda height=None:()),events=['ready'],timeout=None,notified_owners=set())
 def test_menu_close_is_painted_before_deferred_models(self):
  e=self.env(held=False);h=e['host']
  h.set_launcher(('Applications','Find:','  Connections','','Esc closes'));h.flush(3000)
  self.assertFalse(h.ui_damage)
  exec(DECISION,e)
  self.assertEqual(h.launcher_lines,())
  self.assertTrue(h.ui_damage);self.assertTrue(h._launcher_dirty)
  self.assertFalse(e['refresh_models']);self.assertTrue(e['model_full_deferred'])
  h.flush(3000);e['model_inputs']=False
  exec(DECISION,e)
  self.assertTrue(e['refresh_models']);self.assertTrue(e['full_models'])
 def test_age_tick_does_not_rebuild_unrelated_apps(self):
  for pending in (False,True):
   e=self.env(due=['sources'],held=False);e['model_inputs']=False
   e['radio']=types.SimpleNamespace(publication_pending=lambda:pending)
   exec(DECISION,e)
   self.assertTrue(e['source_models']);self.assertTrue(e['refresh_models'])
   self.assertEqual(e['full_models'],pending)
 def test_background_completion_does_not_rebuild_sources_or_forms(self):
  e=self.env(held=False);e['model_inputs']=False;e['notified_owners']={'background'}
  exec(DECISION,e)
  self.assertFalse(e['refresh_models']);self.assertFalse(e['full_models'])
  self.assertFalse(e['source_models']);self.assertEqual(e['notified_owners'],set())
 def test_draw_only_pass_preserves_deadline_and_safety_without_flux(self):
  from keyboard_runtime import KeyboardRouter
  foreground=[True];cancelled=[]
  form=types.SimpleNamespace(key_event=lambda *args:None,cancel_keys=lambda now:cancelled.append(now))
  router=KeyboardRouter(types.SimpleNamespace(device={'motion_codes':[]}),foreground=lambda:foreground[0])
  router.select(form);router.event(('key_event','left','press'))
  e=self.env(held=False);e.update(model_inputs=False,keyboard_router=router,sync_keyboard=lambda:router.select(form))
  e['model_schedule'].deadlines={'sources':time.monotonic()+10}
  original=dict(e['model_schedule'].deadlines)
  for _ in range(5):
   e['notified_owners']={'background'};exec(DECISION,e)
   self.assertFalse(e['lifecycle_refresh']);self.assertEqual(e['model_schedule'].deadlines,original)
  foreground[0]=False;exec(DECISION,e)
  self.assertTrue(cancelled);self.assertIsNone(router.target);self.assertFalse(router.held)
  e['model_schedule'].deadlines['sources']=0;exec(DECISION,e)
  self.assertTrue(e['lifecycle_refresh']);self.assertTrue(e['source_models'])
 def test_deferred_restored_owner_refreshes_on_next_draw(self):
  e=self.env(held=False);e['model_inputs']=False;e['notified_owners']={'form:Restored'}
  exec(DECISION,e);self.assertTrue(e['lifecycle_refresh']);self.assertIn('form:Restored',e['due_owners'])
 def test_pending_motion_defers_before_advance_and_preserves_full_request(self):
  e=self.env(latest=True);self.assertFalse(e['host'].ui_damage);exec(DECISION,e);self.assertFalse(e['refresh_models']);self.assertTrue(e['model_full_deferred']);self.assertIsNotNone(e['host'].latest)
  output,_,_=e['host'].flush(3000);self.assertTrue(output);self.assertIsNone(e['host'].latest)
 def test_stationary_held_contact_can_sleep(self):
  e=self.env();exec(DECISION,e);self.assertFalse(e['refresh_models']);self.assertTrue(e['model_deferred']);exec(code([OVERRIDE]),e);self.assertIsNone(e['timeout'])
 def test_due_source_io_panel_and_jobs_remain_enabled_without_full_fanout(self):
  for owner in ('sources','panel','form:CW','application:0'):
   e=self.env(due=[owner]);exec(DECISION,e);self.assertTrue(e['refresh_models']);self.assertFalse(e['full_models']);self.assertEqual(e['source_models'],owner=='sources')
 def test_explicit_all_fallback_keeps_full_lifecycle_work(self):
  e=self.env(due=['all']);exec(DECISION,e);self.assertTrue(e['refresh_models']);self.assertTrue(e['full_models'])
 def test_due_batch_runs_after_paint_before_another_ready_motion(self):
  e=self.env(due=['sources'],latest=True);exec(DECISION,e);self.assertFalse(e['refresh_models']);self.assertTrue(eval(compile(ast.Expression(CONTINUE.test),'demo.py','eval'),e));self.assertFalse(e['serviced_owners'])
  e['host'].flush(3000);e['events']=();exec(DECISION,e);self.assertTrue(e['refresh_models']);self.assertFalse(eval(compile(ast.Expression(CONTINUE.test),'demo.py','eval'),e))
  e['serviced_owners'].add('sources');e['model_schedule'].arm({'sources':1.},time.monotonic(),e['serviced_owners']);self.assertGreater(e['model_schedule'].delay(time.monotonic()),.9)
 def test_partial_jobs_do_not_drop_deferred_full_input(self):
  e=self.env(due=['form:CW']);exec(DECISION,e);exec(code([RESET]),e);self.assertTrue(e['model_inputs']);self.assertTrue(e['model_full_deferred'])
 def test_release_cancel_and_fresh_contact(self):
  for commit in (False,True):
   e=self.env(latest=True);exec(DECISION,e);original=e['host'].window('one').rect;e['host'].advance();proposed=e['host'].drag[2];e['host'].finish(commit);self.assertEqual(e['host'].window('one').rect,proposed if commit else original);e['host'].flush(3000);exec(DECISION,e);self.assertTrue(e['refresh_models']);self.assertTrue(e['full_models']);exec(code([RESET]),e);self.assertFalse(e['model_deferred']);e['host'].begin();e['host'].flush(3000);e['host'].motion(1,0);exec(DECISION,e);self.assertFalse(e['refresh_models'])
 def test_repeated_motion_cannot_push_out_already_due_source(self):
  e=self.env(due=['sources']);clock=[10.];e['time']=types.SimpleNamespace(monotonic=lambda:clock[0]);serviced=0
  for _ in range(4):
   e['host'].motion(4,2);exec(DECISION,e);self.assertFalse(e['refresh_models']);self.assertTrue(eval(compile(ast.Expression(CONTINUE.test),'demo.py','eval'),e))
   e['host'].flush(3000);e['events']=();exec(DECISION,e);self.assertTrue(e['source_models']);self.assertTrue(e['refresh_models']);serviced+=1
   e['model_schedule'].arm({'sources':1.},clock[0],{'sources'});clock[0]+=1.1
  self.assertEqual(serviced,4)
 def test_control_pty_provider_ingress_preserved_with_additive_readiness(self):
  baseline=ast.parse((ROOT.parent/'tests/fixtures/drag_baseline.py').read_text())
  ingress=lambda tree:next(n for n in ast.walk(tree) if isinstance(n,ast.For) and ast.unparse(n.target)=='(key, _)' and ast.unparse(n.iter)=='events')
  branch=lambda tree,test:next(ast.dump(n,include_attributes=False) for n in ingress(tree).body if isinstance(n,ast.If) and ast.unparse(n.test)==test)
  for test in ('control is not None and (key.data is control or key.data in control.clients)', 'key.data in terminals.values()', 'key.fileobj is sys.stdin'):
   self.assertEqual(branch(TREE,test),branch(baseline,test),test)
  provider=lambda tree:next(n for n in ast.walk(ingress(tree)) if isinstance(n,ast.For) and ast.unparse(n.target)=='(ok, value)')
  self.assertEqual([ast.dump(n,include_attributes=False) for n in provider(TREE).body],[ast.dump(n,include_attributes=False) for n in provider(baseline).body])
  tests={ast.unparse(n.test) for n in ingress(TREE).body if isinstance(n,ast.If)}
  self.assertIn('isinstance(key.data, AppReady)',tests)
  self.assertEqual(sum(isinstance(n,ast.Call) and ast.unparse(n.func)=='ChildExitWake' for n in ast.walk(TREE)),1)
  source=lambda tree:next(ast.dump(n.body[0].test,include_attributes=False) for n in ast.walk(tree) if isinstance(n,ast.If) and ast.unparse(n.test)=='source_models' and 'radio.update' in ast.unparse(n))
  self.assertEqual(source(TREE),source(baseline))
 def test_notified_owner_survives_outline_then_consumes_only_after_service(self):
  e=self.env(latest=True);e['notified_owners'].add('form:CW')
  exec(DECISION,e);self.assertFalse(e['refresh_models']);self.assertEqual(e['notified_owners'],{'form:CW'})
  e['host'].flush(3000);e['events']=();exec(DECISION,e)
  self.assertTrue(e['refresh_models']);self.assertIn('form:CW',e['due_owners'])
  consume=next(n for n in ast.walk(TREE) if isinstance(n,ast.Expr) and ast.unparse(n).startswith('notified_owners.difference_update'))
  exec(code([consume]),e);self.assertEqual(e['notified_owners'],{'form:CW'})
  e['serviced_owners'].add('form:CW');exec(code([consume]),e);self.assertEqual(e['notified_owners'],set())
 def test_first_frame_and_render_budget_unchanged(self):
  e=self.env(latest=True);e['first_frame']=True;exec(DECISION,e);self.assertTrue(e['refresh_models'])
  baseline=(ROOT.parent/'tests/fixtures/drag_baseline.py').read_text()
  get=lambda text:tuple(ast.unparse(n) for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Call) and ast.unparse(n.func)=='host.flush')
  self.assertEqual(get(TEXT),get(baseline))

class PtyTests(unittest.TestCase):
 def run_loop(self,baseline=False,jobs=False):
  with tempfile.TemporaryDirectory(prefix='drag-schedule-') as temporary:
   folder=Path(temporary);demo=ROOT/'desktop.py'
   if baseline:
    demo=folder/'baseline.py';demo.write_bytes((ROOT.parent/'tests/fixtures/drag_baseline.py').read_bytes())
   read,slave=pty.openpty();fcntl.ioctl(slave,termios.TIOCSWINSZ,struct.pack('HHHH',32,100,0,0))
   env=dict(os.environ,HOME=str(folder),SHELL='/bin/sh',ENV='',BASH_ENV='',TERM='xterm-256color',PYTHONDONTWRITEBYTECODE='1')
   child=subprocess.Popen([sys.executable,'-I','-B',str(ROOT.parent/'tests/fixtures/drag_scheduling_fixture.py'),str(demo),str(folder)]+(['jobs'] if jobs else []),cwd=ROOT,env=env,stdin=slave,stdout=slave,stderr=slave,start_new_session=True);os.close(slave);chunks=[]
   def records():
    try:return [json.loads(line) for line in (folder/'events.jsonl').read_text().splitlines()]
    except FileNotFoundError:return []
   def pump():
    if select.select([read],[],[],.01)[0]:
     try:chunks.append(os.read(read,65536))
     except OSError:pass
   def wait(predicate,label):
    end=time.monotonic()+10
    while time.monotonic()<end:
     pump();rows=records()
     if predicate(rows):return rows
     if child.poll() is not None:break
    raise AssertionError((label,child.poll(),records()[-12:],b''.join(chunks)[-1000:]))
   def pointer(button,x,y,release=False):os.write(read,f'\x1b[<{button};{x};{y}{"m" if release else "M"}'.encode())
   try:
    rows=wait(lambda rows:any(r['kind']=='ready' for r in rows),'first normal frame');ready=next(r for r in rows if r['kind']=='ready');x,y=ready['rect'][:2];ox,oy=ready['origin'];px=x+ox+8;py=y+oy+1
    pointer(0,px,py);wait(lambda rows:any(r['kind']=='outline-written' for r in rows),'down outline')
    # Let the prior initial model turn settle before enabling deliberate delay.
    until=time.monotonic()+.12
    while time.monotonic()<until:pump()
    (folder/'slow').touch();mark=len(records());pointer(32,px+4,py+2)
    rows=wait(lambda rows:any(r['kind']=='outline-written' and r.get('rect')!=[x,y,50,15] for r in rows[mark:]),'isolated motion emitted')
    until=time.monotonic()+.25
    while time.monotonic()<until:pump()
    held=records()[mark:];slow=[r for r in held if r['kind']=='slow-start'];outlines=[r for r in held if r['kind']=='outline-written'];self.assertTrue(outlines)
    if baseline:self.assertTrue(slow);self.assertLess(slow[0]['ns'],outlines[0]['ns'])
    else:
     self.assertFalse(slow);selects=[r for r in held if r['kind']=='select'];self.assertLessEqual(len(selects),8 if jobs else 4);self.assertTrue(any(r['timeout'] is None or r['timeout']>0 for r in selects))
     if jobs:self.assertGreaterEqual(sum(r['kind']=='job-poll' for r in held),2)
    pointer(0,px+4,py+2,True);rows=wait(lambda rows:any(r['kind']=='slow-start' and not r['drag'] for r in rows[mark:]),'release services deferred work')
    released=next(r for r in rows[mark:] if r['kind']=='slow-start' and not r['drag']);self.assertEqual(released['rect'],outlines[0]['rect']);self.assertTrue(any(r['kind']=='finish' and r['commit'] and r['rect']==released['rect'] and r['ns']<released['ns'] for r in rows[mark:]));committed=released['rect'];until=time.monotonic()+.22
    while time.monotonic()<until:pump()
    # Fresh contact and cancel use the same real input/Host path.
    pointer(0,px+4,py+2);newmark=len(records());pointer(32,px+6,py+3);wait(lambda rows:any(r['kind']=='outline-written' for r in rows[newmark:]),'fresh contact outline');os.write(read,b'\x1b');rows=wait(lambda rows:any(r['kind']=='finish' and not r['commit'] for r in rows[newmark:]),'cancel');cancelled=next(r for r in rows[newmark:] if r['kind']=='finish' and not r['commit']);self.assertEqual(cancelled['rect'],committed)
    rows=wait(lambda rows:any(r['kind']=='slow-start' and not r['drag'] and r['ns']>cancelled['ns'] for r in rows[newmark:]),'cancel services deferred work');after_cancel=next(r for r in rows[newmark:] if r['kind']=='slow-start' and not r['drag'] and r['ns']>cancelled['ns']);self.assertEqual(after_cancel['rect'],committed);(folder/'slow').unlink()
    os.write(read,b'q');wait(lambda rows:child.poll() is not None,'normal quit');self.assertEqual(child.returncode,0)
    result=dict(baseline=baseline,jobs=jobs,held_events=held,all_events=records(),stdout_bytes=sum(len(c) for c in chunks),exit_status=child.returncode)
    evidence=os.environ.get('DRAG_SCHEDULE_EVIDENCE')
    if evidence:
     target=Path(evidence)/('BASELINE-PTY.json' if baseline else 'CANDIDATE-JOBS-PTY.json' if jobs else 'CANDIDATE-PTY.json');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,indent=2)+'\n')
    return result
   finally:
    if child.poll() is None:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=5)
    os.close(read)
 def test_actual_loop_baseline_then_candidate_outline_before_slow_work(self):self.run_loop(True);self.run_loop(False)
 def test_actual_loop_due_hidden_job_is_serviced_during_hold(self):self.run_loop(False,True)
if __name__=='__main__':unittest.main(verbosity=2)
