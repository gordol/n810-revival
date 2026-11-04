# SPDX-License-Identifier: MIT
"""Opt-in Flurry provider; one retained workspace, untouched Python fallback."""
import importlib.util
from pathlib import Path
from paint import Scene
import flurry


class Provider:
    def __init__(self,library,expected_sha256=None,backend='auto'):
        self.context=None;self.key=None;self.library=None;self.module=None
        self.backend=backend;self.actual='python';self.reason=None
        self.native_frames=self.python_frames=self.rebuilds=0;self.failed=False
        try:
            source=Path(__file__).parent/'vendor/native/flurry_sidecar.py'
            spec=importlib.util.spec_from_file_location('_flurry_sidecar',source)
            self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)
            self.library=self.module.FlurryLibrary(library,expected_sha256)
            if backend not in self.module.RetainedFlurryContext.BACKENDS:raise ValueError('unsupported Flurry backend')
        except Exception as error:
            self.failed=True;self.reason=type(error).__name__+': '+str(error)

    def frame(self,width,height,step,ascii=False,seed=0,strands=48,sway=.6,speed_scale=1.):
        # Begin with the exact compared workload. Never silently resize or clamp.
        supported=(width==80 and height==24 and seed==17 and strands==24 and not ascii and sway==.6 and speed_scale==1. and 0<=step<=1000000)
        if not self.failed and supported:
            key=(width,height,seed,strands,sway,speed_scale)
            try:
                base=flurry.backdrop(width,height)
                if key!=self.key or self.context is None or self.context.base_source is not base:
                    self.context=self.module.RetainedFlurryContext(self.library,width,height,flurry.plan(seed)[:strands],base,self.backend)
                    self.key=key;self.rebuilds+=1
                overlay=self.context.frame(step,sway,speed_scale,False)
                self.actual=self.context.actual_backend;self.reason=None;self.native_frames+=1
                return Scene(base,overlay)
            except Exception as error:
                self.failed=True;self.reason=type(error).__name__+': '+str(error)
        elif not self.failed:self.reason='configuration outside compared colored 80x24/24/seed17 path'
        self.context=None;self.key=None;self.actual='python';self.python_frames+=1
        return flurry.frame(width,height,step,ascii,seed,strands,sway,speed_scale)

    def status(self):
        return dict(backend=self.actual,reason=self.reason,native_frames=self.native_frames,
                    python_frames=self.python_frames,rebuilds=self.rebuilds,
                    workspace_bytes=self.context.workspace_bytes if self.context else 0,
                    library_sha256=self.library.sha256 if self.library else None,
                    requested_backend=self.backend)
