"""Owned scene jobs without importing terrain, geometry, or lighting models."""
from build_trace import Trace


class Renderer:
    """One owned worker, one pending frame, latest request wins; no state copies.

    The existing selector observes Future completion. Requests contain small
    immutable viewport/time keys; terrain loads only when requested. A completed
    obsolete viewport is discarded. There is no queue of old animation frames.
    """
    def __init__(self,prewarm=False):
        self.trace=Trace()
        self.pool=None;self.pending=None;self.completed=None;self.requested=None
        self.ready={};self.prewarm=prewarm
        self.mode='terrain';self.requested_mode=None;self.fx_completed=None

    def start(self,key,prepare=None):
        if self.pool is None:
            from concurrent.futures import ThreadPoolExecutor
            self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='scene')
        self.requested=key;self.requested_mode=self.mode
        if prepare is None:
            from model_scene import base
            prepare=base
        self.pending=self.pool.submit(self.trace.run,prepare,*key)

    def _resume(self,mode):
        if self.mode!=mode:self.suspend();self.mode=mode
        if self.trace.stopped.is_set():
            if self.pending is not None and not self.pending.done():return False
            if self.pending is not None:
                from concurrent.futures import CancelledError
                try:self.pending.result()
                except CancelledError:pass
            self.pending=None;self.requested=None;self.requested_mode=None;self.trace=Trace()
        return True

    def effect_frame(self,key,prepare):
        """One pending decorative frame; no queue of obsolete animation steps."""
        def identity(value):
            # Step and scene age advance animation; settings define its meaning.
            return value[:4]+value[5:7]+value[8:]
        mode='effect:'+key[3]
        if self.pending is not None and self.requested_mode==mode and identity(self.requested)!=identity(key):self.suspend()
        if not self._resume(mode):
            return self.fx_completed[1] if self.fx_completed and identity(self.fx_completed[0])==identity(key) else None
        if self.pending is not None and self.pending.done():
            result=self.pending.result()
            if identity(self.requested)==identity(key):self.fx_completed=(self.requested,result)
            self.pending=None
        if self.pending is None and self.requested!=key:self.start(key,prepare)
        return self.fx_completed[1] if self.fx_completed and identity(self.fx_completed[0])==identity(key) else None

    def frame(self,*args,**kwargs):
        # Terrain adds its projection lazily; retain this worker and its jobs.
        from model_scene import Renderer as TerrainRenderer
        return TerrainRenderer.frame(self,*args,**kwargs)

    def suspend(self):
        """Stop obsolete work cooperatively without waiting on the input thread."""
        self.trace.cancel()
        if self.pending is not None:self.pending.cancel()

    def close(self):
        self.trace.cancel()
        if self.pending is not None:self.pending.cancel()
        if self.pool is not None:self.pool.shutdown(wait=True,cancel_futures=True)
        self.pool=None;self.pending=None;self.completed=None;self.fx_completed=None;self.ready.clear()
