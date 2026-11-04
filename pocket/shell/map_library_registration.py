"""Bind the frozen Map Library app to this release's immutable resource mirror."""
import importlib.util
from pathlib import Path
import time
from functools import partial

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('_map_library_descriptor_v3',ROOT/'apps/map-library-local-v3/registration.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class RetiredJobs:
    """Backend-only cancellation receipts; no view, Host or renderer reference.

    Keep the worker/lease, bounded request receipts and their persistence paths
    until cancellation is reaped. Drop catalog, resource inventory and store
    caches immediately. Readiness and actual deadlines drive cleanup.
    """
    def __init__(self):self.models=[];self.closed=False;self.error=None
    def retire(self,model):
        model.catalog=[];model.inventory={};model.store=None;model.resource_root=None
        if self.closed or model.worker is None:
            try:model.close()
            except Exception as error:
                self.error=str(error);self.models.append(model)
                if self.closed:raise
            return
        model.worker.cancel()
        self.models.append(model)
    def poll(self):
        for model in tuple(self.models):
            try:
                model.poll()
                if model.worker is None:model.close();self.models.remove(model)
            except Exception as error:self.error=str(error)  # Retain receipt/lock for retry on the next real event.
    def readiness_sources(self):
        return tuple((model.worker.process.stdout,self.poll) for model in self.models if model.worker is not None and model.worker.readiness_fd is not None)
    def poll_interval(self):
        deadlines=[model.worker.next_deadline for model in self.models if model.worker is not None and model.worker.next_deadline is not None]
        return max(0.,min(deadlines)-time.monotonic()) if deadlines else None
    def close(self):
        self.closed=True
        failure=None
        for model in tuple(self.models):
            try:model.close();self.models.remove(model)
            except Exception as error:
                self.error=str(error);failure=failure or error
        if failure is not None:raise failure  # Final shutdown reports failure after guaranteed terminal restoration.


class LibraryLifetime:
    dispose_on_close=True
    def __init__(self, app, service, retire):
        self.view=app;self.service=service;self.retire=retire

    def __getattr__(self,name):return getattr(self.view,name)

    def readiness_sources(self):
        if self.view is None:return ()
        worker=self.view.model.worker
        return ((worker.process.stdout,self.view.poll),) if worker is not None and worker.readiness_fd is not None else ()

    def close(self):
        app,self.view=self.view,None
        if app is None:return
        if app._map_unsubscribe is not None:
            app._map_unsubscribe();app._map_unsubscribe=None
        if self.service is not None:self.service.cancel()
        app.closed=app.closing=True
        model,app.model=app.model,None
        self.retire(model)


def create(host,*,retire,app_context=None):
    resources=ROOT/'vendor/map-library-resources/explorations/current-world'
    app=module.create(host,resources,app_context=app_context)
    service=app_context.services.get('map-open') if app_context is not None else None
    return LibraryLifetime(app,service,retire)


def descriptor(retire):
    result=module.descriptor()
    result.update(factory=partial(create,retire=retire),resources=())
    return result
