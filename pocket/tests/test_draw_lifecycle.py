"""Exercise the desktop's cached lifecycle boundaries with real readiness/Futures."""
import ast,selectors,socket,sys,time,unittest,textwrap
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from app_readiness import AppReadiness
from core import Inbox
from model_deadlines import ModelDeadlines
from renderer_wakeup import FutureWakeups
TREE=ast.parse((Path(__file__).resolve().parents[1]/'shell/desktop.py').read_text())
def statement(predicate):
    node=next(n for n in ast.walk(TREE) if isinstance(n,ast.If) and predicate(n))
    return compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'desktop.py','exec')
SCAN=statement(lambda n:ast.unparse(n.test)=='lifecycle_refresh' and 'application.poll_interval' in ast.unparse(n))
ARM=statement(lambda n:ast.unparse(n.test)=='lifecycle_refresh' and 'model_schedule.arm' in ast.unparse(n))
READY=statement(lambda n:ast.unparse(n.test)=='lifecycle_refresh' and 'app_readiness.sync' in ast.unparse(n))
PRESENTED=statement(lambda n:ast.unparse(n.test)=='not host.damage' and 'for form in presented_forms' in ast.unparse(n))
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.selector=selectors.DefaultSelector();self.addCleanup(self.selector.close)
        self.inbox=Inbox();self.addCleanup(self.inbox.close)
        self.ready=AppReadiness(self.selector);self.addCleanup(self.ready.close)
        self.schedule=ModelDeadlines()
        self.forms={}
        self.env=dict(DEVELOPMENT=True,lifecycle_refresh=True,applications=(),metrics=None,host=SimpleNamespace(app_forms=self.forms,damage=False,
            window=lambda name:SimpleNamespace(rolled=False),shown=lambda w:True),
            radio=None,timeout=None,owner_delays={},model_schedule=self.schedule,now=10.,serviced_owners=set(),
            future_wakeups=FutureWakeups(self.inbox),app_readiness=self.ready,time=time,presented_forms=())
        self.env['owner_delay']=lambda owner,delay:self.env['owner_delays'].__setitem__(owner,delay)
    def assemble(self):
        self.env['owner_delays']={}
        for block in (SCAN,ARM,READY):exec(block,self.env)
    def test_background_reuse_keeps_absolute_retry_and_new_owner_gets_readiness(self):
        read,write=socket.socketpair();self.addCleanup(read.close);self.addCleanup(write.close)
        calls=[]
        class Form:
            def poll_interval(self):return 1.
            def readiness_sources(self):return ((read,self.ready),)
            def ready(self):calls.append(read.recv(1))
        self.forms['Retry']=Form();self.assemble()
        self.assertEqual(self.schedule.deadlines,{'form:Retry':11.})
        old=self.selector.get_key(read).data
        for now in (10.2,10.5,10.9):
            self.env.update(lifecycle_refresh=False,now=now);self.assemble()
            self.assertEqual(self.schedule.deadlines,{'form:Retry':11.})
            self.assertIs(self.selector.get_key(read).data,old)
        self.assertEqual(self.schedule.due(11.),{'form:Retry'})
        # A restored/replaced owner is admitted by the next notified model pass.
        replacement=Form();replacement._future=Future();self.forms['Retry']=replacement
        self.env.update(lifecycle_refresh=True,now=11.,serviced_owners={'form:Retry'});self.assemble()
        self.assertIsNot(self.selector.get_key(read).data,old)
        replacement._future.set_result('done')
        self.assertEqual(set(self.inbox.drain_notifications()),{'form:Retry'})
        write.send(b'x');self.selector.select(.1)[0][0].data.callback();self.assertEqual(calls,[b'x'])
    def test_presented_callback_starts_work_before_sleep_even_without_model_refresh(self):
        class Form:
            interval=None
            def poll_interval(self):return self.interval
            def presented(self,now):self.interval=.25;self._future=Future()
        form=Form();self.forms['Presented']=form;self.assemble()
        self.env.update(lifecycle_refresh=False,presented_forms=(form,),now=20.)
        exec(PRESENTED,self.env);self.assertTrue(self.env['lifecycle_refresh'])
        self.assemble();self.assertEqual(self.schedule.deadlines,{'form:Presented':20.25})
        form._future.set_result(None)
        self.assertEqual(set(self.inbox.drain_notifications()),{'form:Presented'})
class PanelDrawTests(unittest.TestCase):
    def test_reused_panel_output_matches_full_checks_across_changes(self):
        from panel import Panels
        from core import Host,Window
        text=(Path(__file__).resolve().parents[1]/'shell/desktop.py').read_text()
        start=text.index('            current_panel_view=')
        end=text.index("            if platform is None:output+=f'",start)
        block=compile(textwrap.dedent(text[start:end]),'desktop-panel','exec')
        panels=[Panels(),Panels()]
        for panel in panels:panel.layout(100,30)
        host=Host(100,29,[Window('One',2,2,30,10)])
        widgets={'windows':[('One','One')]};icons={};styles={}
        env=dict(host=host,windows=host.windows,panel=panels[0],widgets=widgets,
            panel_icons=icons,radio_styles=styles,panel_view=None,lifecycle_refresh=True,platform=None)
        def compare(refresh=False):
            env['lifecycle_refresh']=refresh
            exec(block,env)
            expected=panels[1].render(widgets,{w.name:host.window_status(w) for w in host.windows},icons)
            self.assertEqual(env['panel_output'],expected)
            self.assertEqual(host.minimize_targets,panels[1].minimize_targets((w.name for w in host.windows),host.origin))
        compare(True)
        for _ in range(5):compare()
        host.focus=None;compare()
        host.window('One').visible=False;compare(True)
        widgets['windows'].append(('Two','Two'));compare(True)
        host.origin=(2,1);compare()
        for panel in panels:
            for p in panel.panels:p.cache=None
        compare() # Explicit invalidation, including repaint over a dock.
        for panel in panels:panel.layout(80,25)
        compare(True)

if __name__=='__main__':unittest.main()
