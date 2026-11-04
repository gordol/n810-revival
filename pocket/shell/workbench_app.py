"""Composition/lifetime adapter for the separate local Workbench domain."""
import importlib.util
from pathlib import Path
import sys
import time
from native_workbench import WorkbenchView


def domain_root():
    here=Path(__file__).resolve().parent
    return next((root for root in (here/'vendor/apps',)
                 if (root/'domains/workbench/__init__.py').is_file()),None)


def load_domain():
    root=domain_root()
    if root is None:raise ImportError('Local Workbench domain is not installed')
    name='_pocket_workbench_domain'
    if name not in sys.modules:
        path=root/'domains/workbench/__init__.py'
        spec=importlib.util.spec_from_file_location(name,path,submodule_search_locations=[str(path.parent)])
        module=importlib.util.module_from_spec(spec);sys.modules[name]=module
        try:spec.loader.exec_module(module)
        except Exception:sys.modules.pop(name,None);raise
    return sys.modules[name].Workbench


class WorkbenchApp:
    """One owner per desktop, independent of pane visibility; no work in draw."""
    def __init__(self,state_dir,*,model=None):
        self.model=model if model is not None else load_domain()(state_dir)
        self.closed=False;self.next_poll=0
        self.view=WorkbenchView(self.command)
        self.poll(force=True)

    def command(self,action,*args,**kwargs):
        if self.closed:return
        if action not in ('select','run_cw','cancel','load_result','refresh_evidence'):raise ValueError('Unknown Workbench action')
        try:
            getattr(self.model,action)(*args,**kwargs)
            self.view.notice=''
        except (ValueError,RuntimeError,OSError) as error:self.view.notice=str(error)
        self.poll(force=True)

    def poll(self,*,force=False):
        if self.closed:return
        now=time.monotonic()
        if not force and (self.poll_interval() is None or now<self.next_poll):return
        self.next_poll=now+.1;self.view.update(self.model.snapshot())

    def poll_interval(self):
        return .1 if not self.closed and self.view.snapshot.get('status') in ('running','cancelling') else None

    def close(self):
        if not self.closed:self.closed=True;self.model.close()
