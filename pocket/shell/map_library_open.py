"""One bounded admission job for the existing Map Library open action.

The UI passes an artifact ID, never an approval or directory. A child validates
it; only the current request may select a provider on the UI thread. Completion
wakes the desktop's existing inbox. There is no recurring timer or idle work.
"""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import weakref

MAX_RESULT = 65536
WORKER = Path(__file__).with_name('map_library_open_worker.py')


class MapOpen:
    def __init__(self, root, viewer_root, wake, select):
        self.root, self.viewer_root = str(root), str(viewer_root)
        self.wake, self.select = wake, select
        self.generation = 0
        self.closed = False
        self.notice = ''
        self._lock = threading.Lock()
        self._pool = None
        self._future = None
        self._process = None
        self._requested = None
        self._artifact_id = None
        self._observers = {}
        self._observer_id = 0
        self._notice = None

    def open_map(self, artifact_id):
        if not self.request(artifact_id):
            raise RuntimeError('Map Library is closed')
        return {'generation': self.generation}

    def bind_notice(self, callback):
        # Subscriptions cannot retain a closed LibraryApp owner.
        reference = weakref.WeakMethod(callback) if getattr(callback, '__self__', None) is not None else weakref.ref(callback)
        self._observer_id += 1
        token = self._observer_id
        self._observers[token] = reference
        def unsubscribe():
            self._observers.pop(token, None)
        return unsubscribe

    def _publish(self, state):
        self._notice = dict(artifact_id=self._artifact_id, generation=self.generation,
                            state=state, message=self.notice[:512])
        for token, reference in tuple(self._observers.items()):
            callback = reference()
            if callback is None:
                self._observers.pop(token, None)
            else:
                callback(dict(self._notice))

    def request(self, artifact_id):
        if self.closed:
            return False
        if not isinstance(artifact_id, str) or not re.fullmatch('[0-9a-f]{64}', artifact_id):
            raise ValueError('Invalid map artifact ID')
        self.generation += 1
        self._artifact_id = artifact_id
        self._requested = (self.generation, artifact_id)
        self.notice = 'Validating requested map'
        self._publish('validating')
        self._cancel_child()
        self._start()
        return True

    def _cancel_child(self):
        with self._lock:
            child = self._process
            if child is not None:
                try:
                    child.terminate()
                except ProcessLookupError:
                    pass

    def _start(self):
        if self.closed or self._future is not None or self._requested is None:
            return
        request, self._requested = self._requested, None
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='map-admission')
        self._future = self._pool.submit(self._run, *request)
        self._future.add_done_callback(self._completed)

    def _completed(self, future):
        try:
            self.wake()
        except OSError:
            pass  # Full inbox already wakes the loop; closed inbox is shutdown.

    def _run(self, generation, artifact_id):
        with self._lock:
            if self.closed or generation != self.generation:
                return generation, None, None
        child = subprocess.Popen(
            [sys.executable, '-I', str(WORKER), self.root, artifact_id, self.viewer_root],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        with self._lock:
            self._process = child
            if self.closed or generation != self.generation:
                child.terminate()
        try:
            try:
                raw, _ = child.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.communicate()
                return generation, None, 'Map validation exceeded its deadline'
            if len(raw) > MAX_RESULT:
                raise ValueError('Map validation result exceeds its limit')
            result = json.loads(raw)
            if not isinstance(result, dict) or set(result) != {'reference', 'error'}:
                raise ValueError('Invalid map validation result')
            error = result['error']
            if error is not None and (not isinstance(error, str) or len(error) > 2048):
                raise ValueError('Invalid map validation error')
            if child.returncode != 0 and error is None:
                raise ValueError('Map validation failed')
            if error is not None and result['reference'] is not None:
                raise ValueError('Ambiguous map validation result')
            return generation, result['reference'], error
        except (ValueError, OSError) as error:
            return generation, None, str(error)[:2048]
        finally:
            with self._lock:
                self._process = None

    def drain(self):
        """Called after an inbox wake, never to wait for work."""
        future = self._future
        if future is None or not future.done():
            return False
        self._future = None
        changed = False
        try:
            generation, reference, error = future.result()
            if not self.closed and generation == self.generation:
                if error is not None:
                    self.notice = 'Cannot open map: ' + error
                    self._publish('failed')
                else:
                    from map_library_provider import ApprovedProviderRef
                    approved = ApprovedProviderRef.from_mapping(reference)
                    self.select(approved)
                    self.notice = 'Map requested; loading detail'
                    self._publish('selected')
                changed = True
        except Exception as error:
            if not self.closed and self._requested is None:
                self.notice = 'Cannot open map: ' + str(error)[:2048]
                self._publish('failed')
                changed = True
        self._start()
        return changed

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.generation += 1
        self._requested = None
        self._observers.clear()
        self._cancel_child()
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)

    def cancel(self):
        """Retire pending activation when its requesting window is closed."""
        self.generation += 1
        self._requested = None
        self._cancel_child()
