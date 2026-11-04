"""Map Library form using the desktop's existing character widgets.

Drawing reads cached model records only. Requests need a separate approval;
publication and import never imply activation in the map renderer.
"""
from pathlib import Path
import os
import re
import time

from app_widgets import Canvas, DetailBlock, SelectList


PRESETS = ('lakewood', 'lakewood-lod', 'puget', 'puget-lod',
           'lakewood-fine', 'lakewood-fine-lod', 'rainier', 'rainier-lod')
TABS = ('Presets', 'Requests', 'Library', 'Completions')
HELP = (('Map Library', (
    'Tab or Left/Right: change page. Up/Down: choose an item.',
    'Presets: Enter requests preparation; it does not run it.',
    'Presets: U validates and imports an existing local pack without a job.',
    'Requests: A approves and runs, R rejects, C cancels.',
    'Library: I validates and imports a published pack.',
    'Library: O requests opening an imported pack in the normal map viewer.',
    'F5: refresh the cached catalog and compatibility in the background.',
    'Import does not open a map. Opening requires an available viewer service.',
    'Jobs and results are local. No remote worker is contacted.')),)


def default_state_root():
    return Path(os.environ.get('XDG_STATE_HOME', str(Path.home()/'.local/state'))) / 'current-world/map-library'


def _id(record):
    return str(record.get('id') or record.get('artifact_id') or record.get('request_id') or '')


class LibraryApp:
    """Desktop lifetime owner and form; a pane close does not kill local work."""
    def __init__(self, host, resource_root, state_root=None, *, model=None, open_map=None):
        if model is None:
            from .library_model import LibraryModel
            model = LibraryModel(state_root or default_state_root(), resource_root)
        self.host, self.model = host, model
        self.open_map = open_map
        self.view = self
        self.width, self.height = 78, 22
        self.tab = 0
        self.lists = [SelectList(PRESETS), SelectList(()), SelectList(()), SelectList(())]
        self.records = [tuple({'id': p, 'preset': p} for p in PRESETS), (), (), ()]
        self.notice = ''
        self.closed = False
        self.closing = False
        self._map_unsubscribe = None
        self._map_artifact = None
        self._map_generation = None
        self._spans, self._hits = (), []
        self._list_rect = None
        self._session_callback = None
        self.refresh()

    def refresh(self):
        self.records[1] = tuple(self.model.list_requests())
        self.records[2] = tuple(self.model.store.list_artifacts())
        self.records[3] = tuple(self.model.completions())
        for tab in range(1, 4):
            rows = self.records[tab]
            labels = []
            for row in rows:
                label = str(row.get('preset') or row.get('title') or _id(row))
                state = str(row.get('state') or row.get('status') or 'unknown')
                if tab == 2:
                    state += ' / compatible' if row.get('compatible') else ' / unverified'
                labels.append(label + ' · ' + state)
            self.lists[tab].replace(labels, tuple(_id(row) for row in rows))

    def selected(self):
        rows = self.records[self.tab]
        index = self.lists[self.tab].index
        return rows[index] if 0 <= index < len(rows) else None

    def invoke(self, action):
        if self.closed or self.closing:
            return False
        if action == 'refresh':
            try:
                self.model.refresh_catalog()
                self.notice = 'Refreshing cached catalog and compatibility in the background.'
            except (ValueError, RuntimeError, OSError) as error:
                self.notice = str(error)
            return True
        row = self.selected()
        if not row:
            self.notice = 'Choose an item first.'
            return True
        if action == 'open_map' and self.tab == 2:
            try:
                if getattr(self.model, 'closed', False) or getattr(self.model, 'closing', False):
                    raise ValueError('Map Library is closing or closed.')
                if getattr(self.model, 'worker', None) is not None:
                    raise ValueError('Wait for the current map operation before opening a pack.')
                if row.get('state') != 'imported':
                    raise ValueError('Import this pack before opening it in the map.')
                identity = row.get('artifact_id')
                if not isinstance(identity, str) or re.fullmatch('[0-9a-f]{64}', identity) is None:
                    raise ValueError('The imported pack has an invalid artifact identity.')
                if not callable(self.open_map):
                    raise ValueError('The map viewer service is unavailable in this desktop.')
                self._map_artifact = self._map_generation = None
                accepted = self.open_map(identity)
                generation = accepted.get('generation') if isinstance(accepted, dict) else None
                if type(generation) is int and generation >= 0:
                    self._map_artifact, self._map_generation = identity, generation
                else:
                    accepted = accepted is True
                self.notice = ('Opening requested; verifying pack.' if accepted else
                               'The map viewer did not accept the opening request.')
            except (ValueError, RuntimeError, OSError) as error:
                self.notice = str(error)
            return True
        try:
            if action == 'request' and self.tab == 0:
                self.model.request(row['preset'])
                self.notice = 'Request saved. Approve it on Requests to run preparation.'
            elif action == 'use_existing' and self.tab == 0:
                self.model.import_existing(row['preset'])
                self.notice = 'Validating existing pack in the background; not imported yet.'
            elif action in ('approve', 'reject', 'cancel') and self.tab == 1:
                result = getattr(self.model, action)(_id(row))
                self.notice = {'approve': 'Approved; preparation started.',
                               'reject': 'Request rejected.', 'cancel': 'Cancellation requested.'}[action]
                if isinstance(result, dict) and result.get('state') == 'failed':
                    self.notice = 'Preparation failed: '+str(result.get('error') or 'Unknown error')
            elif action == 'import' and self.tab == 2:
                self.model.store.import_artifact(_id(row))
                self.notice = 'Validating pack in the background; not imported yet.'
            else:
                return False
        except (ValueError, RuntimeError, OSError) as error:
            self.notice = str(error)
        self.refresh()
        return True

    def on_map_open_notice(self, notice):
        if (self.closed or self.closing or getattr(self.model, 'closing', False)
                or getattr(self.model, 'closed', False) or not isinstance(notice, dict)
                or set(notice) != {'artifact_id', 'generation', 'state', 'message'}):
            return
        if (self._map_generation is None or type(notice['generation']) is not int
                or notice['generation'] != self._map_generation
                or notice['artifact_id'] != self._map_artifact
                or notice['state'] not in ('validating', 'failed', 'selected')
                or not isinstance(notice['message'], str) or len(notice['message']) > 512
                or not all(char.isprintable() for char in notice['message'])):
            return
        self.notice = ('Selected; awaiting map frame.' if notice['state'] == 'selected' else notice['message'])
        if self._session_callback:
            self._session_callback()

    def bind_session(self, callback):
        self._session_callback = callback

    def session_state(self):
        return {'tab': TABS[self.tab]}

    def restore_session(self, state):
        if isinstance(state, dict) and state.get('tab') in TABS:
            self.tab = TABS.index(state['tab'])

    def select_tab(self, index):
        previous = self.tab
        self.tab = index % len(TABS)
        if previous != self.tab and self._session_callback:
            self._session_callback()

    def key(self, key):
        if self.closed:
            return False
        if key == 'f5':
            return self.invoke('refresh')
        chosen = self.lists[self.tab]
        if chosen.search_key(key):
            return True
        if key in ('\t', 'backtab', 'left', 'right'):
            self.select_tab(self.tab + (-1 if key in ('backtab', 'left') else 1))
            return True
        if key in ('1', '2', '3', '4'):
            self.select_tab(int(key)-1)
            return True
        action = None
        if self.tab == 0 and key in ('\r', '\n', 'enter'):
            action = 'request'
        elif self.tab == 0 and key.lower() == 'u':
            action = 'use_existing'
        elif self.tab == 1:
            action = {'a': 'approve', 'r': 'reject', 'c': 'cancel'}.get(key.lower())
        elif self.tab == 2 and key.lower() == 'i':
            action = 'import'
        elif self.tab == 2 and key.lower() == 'o':
            action = 'open_map'
        if action:
            return self.invoke(action)
        return chosen.key(key)

    def pointer(self, column, row, width, button=0, released=False):
        if self.closed or released or button & 32:
            return False
        self.width = width
        if button == 0:
            for x, y, size, kind, value in self._hits:
                if row == y and x <= column < x+size:
                    if kind == 'tab':
                        self.select_tab(value)
                    else:
                        self.invoke(value)
                    return True
        if self._list_rect:
            x, y, w, h = self._list_rect
            if x <= column < x+w and y <= row < y+h:
                chosen = self.lists[self.tab]
                if button & 64:
                    chosen.scroll(1 if button & 1 else -1, h)
                    return True
                if button == 0:
                    return chosen.pointer_at(column-x, row-y, w, h)
        return False

    def poll_interval(self):
        worker = getattr(self.model, 'worker', None)
        deadline = getattr(worker, 'next_deadline', None)
        return max(0., deadline-time.monotonic()) if not self.closed and not self.closing and deadline is not None else None

    def readiness_sources(self):
        if self.closed or self.closing:
            return ()
        worker = getattr(self.model, 'worker', None)
        fd = getattr(worker, 'readiness_fd', None)
        return ((fd, self.poll),) if fd is not None else ()

    def poll(self):
        if self.closed or self.closing:
            return
        if self.model.poll():
            self.refresh()
            notice = getattr(self.model, 'operation_notice', '')
            if notice:
                self.notice = str(notice)

    def close(self):
        if not self.closed:
            self.closing = True
            try:
                if self._map_unsubscribe is not None:
                    self._map_unsubscribe()
                    self._map_unsubscribe = None
                self.model.close()
            except Exception as error:
                self.notice = 'Could not close Map Library: '+str(error)
                raise
            self.closed = True

    def help_pages(self):
        return HELP

    def _details(self, width):
        body = DetailBlock(width)
        row = self.selected()
        if row is None:
            body.text(('No requests yet.', 'No requests yet.', 'No published packs yet.',
                       'No completed jobs yet.')[self.tab])
            return body
        body.section(str(row.get('preset') or row.get('title') or 'Selected item'))
        if self.tab == 0:
            body.text('U: import an existing local pack without a preparation job.')
            body.text('Enter: request preparation using the fixed regional-pack-v2 recipe. Approval is separate.')
            body.text('Import does not activate a map. No remote worker is contacted.', 'muted')
        else:
            for label, key in (('State', 'state'), ('Status', 'status'), ('Estimate', 'estimate'),
                               ('Memory estimate', 'memory_estimate'), ('Bytes', 'bytes')):
                if key in row:
                    body.field(label, str(row[key]))
            budget = row.get('budget')
            if isinstance(budget, dict):
                body.field('Limit', str(budget.get('wall_seconds', '?'))+' s; '+
                           str(budget.get('tile_bytes', 0)//1024)+' KiB tile data')
            if row.get('compatibility_reason'):
                body.text(str(row['compatibility_reason']))
            if row.get('error'):
                body.text(str(row['error']), 'warning')
            if row.get('message'):
                body.text(str(row['message']))
            if self.tab == 2:
                body.text('Compatibility is from the last background check. F5 refreshes this cached catalog.', 'muted')
                body.text('O: request opening an imported pack. The viewer verifies it before use.', 'muted')
                if not callable(self.open_map):
                    body.text('Map viewer service unavailable in this desktop.', 'muted')
        return body

    def lines(self):
        c = Canvas(self.width, self.height)
        self._hits = []
        x = 0
        for index, title in enumerate(TABS):
            if self.width < 48:
                title = ('Presets', 'Queue', 'Packs', 'Done')[index]
            label = ('['+title+']') if index == self.tab else title
            c.put(x, 0, label)
            c.role(x, 0, len(label), 'selected' if index == self.tab else 'control')
            self._hits.append((x, 0, len(label), 'tab', index))
            x += len(label)+1
        c.put(0, 1, 'Cached catalog · F5 refresh' if self.tab == 2 else 'Local work queue · request, approve, prepare, import')
        c.role(0, 1, self.width, 'muted')
        actions = (('Request', 'request'), ('Use existing', 'use_existing')) if self.tab == 0 else (
            (('Approve and run', 'approve'), ('Reject', 'reject'), ('Cancel', 'cancel'))
            if self.tab == 1 else (('Import', 'import'), ('Open in map', 'open_map'), ('Refresh', 'refresh')) if self.tab == 2 else ())
        x = 0
        for label, action in actions:
            label = '[ '+label+' ]'
            c.put(x, 2, label)
            c.role(x, 2, len(label), 'control')
            self._hits.append((x, 2, len(label), 'action', action))
            x += len(label)+1
        list_height = max(1, (self.height-7)//2)
        self._list_rect = (0, 4, self.width, list_height)
        self.lists[self.tab].draw(c, *self._list_rect)
        details_y = 4+list_height
        self._details(self.width).draw(c, 0, details_y, self.width,
                                       max(1, self.height-details_y-2), 0)
        c.put(0, self.height-2, self.notice or 'Published and imported are separate from active.', self.width)
        c.role(0, self.height-2, self.width, 'status')
        hints = ('Enter: request  U: use existing', 'A: approve/run  R: reject  C: cancel', 'I: import  O: open map  F5: refresh', 'Retained local completion records')[self.tab]
        c.put(0, self.height-1, hints+' · Tab: page · ↑↓: select', self.width)
        self._spans = c.styled_spans()
        return c.lines()

    def spans(self):
        return self._spans
