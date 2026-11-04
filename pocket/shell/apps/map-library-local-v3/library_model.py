"""Small durable queue and cached catalog; expensive map work stays in a child."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import errno
import stat
import tempfile
import uuid

if __package__:
    from .worker import PRESETS, Worker, inventory_digest
else:
    from worker import PRESETS, Worker, inventory_digest

INVENTORY = Path(__file__).with_name('dependency-inventory.json')
STATES = {'pending', 'approved', 'running', 'cancelling', 'complete', 'rejected', 'cancelled', 'failed'}
MAX_JSON = 1024 * 1024
MAX_CATALOG = 64 * 1024


def discard_worker_metadata(directory):
    """Only constant-size cleanup in the UI; the next child reclaims bulk data."""
    directory = Path(directory)
    for name in ('result.json', 'worker.log', '.result.json'):
        try:
            (directory/name).unlink()
        except FileNotFoundError:
            pass
    try:
        directory.rmdir()
    except FileNotFoundError:
        pass
    except OSError as error:
        if error.errno not in (errno.ENOTEMPTY, errno.EEXIST):
            raise


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.receipt-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read_private_json(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or info.st_mode & 0o077 or not 0 < info.st_size <= limit):
            raise ValueError('Unsafe or oversized Map Library receipt')
        raw = stream.read(limit+1)
        if len(raw) != info.st_size or len(raw) > limit:
            raise ValueError('Map Library receipt changed while reading')
    return json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Invalid JSON number')))


def locked_file(path, busy):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError('Unsafe Map Library lock file')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError(busy) from error
        return os.fdopen(fd, 'a+b')
    except BaseException:
        os.close(fd)
        raise


def validate_catalog(rows):
    if not isinstance(rows, list) or len(rows) > 64:
        raise ValueError('Invalid cached map catalog')
    if len(json.dumps(rows, allow_nan=False).encode()) > MAX_CATALOG:
        raise ValueError('Cached map catalog exceeds size limit')
    seen = set()
    for row in rows:
        if (not isinstance(row, dict) or not re.fullmatch('[0-9a-f]{64}', str(row.get('artifact_id', '')))
                or row['artifact_id'] in seen or row.get('state') not in ('published', 'imported')
                or type(row.get('compatible')) is not bool):
            raise ValueError('Invalid cached map artifact')
        seen.add(row['artifact_id'])
    return copy.deepcopy(rows)


class CatalogView:
    """The UI sees bounded metadata, never the full artifact store."""
    def __init__(self, model):
        self.model = model

    def list_artifacts(self):
        return copy.deepcopy(self.model.catalog)

    def import_artifact(self, artifact_id):
        if not re.fullmatch('[0-9a-f]{64}', str(artifact_id)):
            raise ValueError('Invalid map artifact identity')
        if not any(row['artifact_id'] == artifact_id for row in self.model.catalog):
            raise ValueError('Unknown published map artifact')
        return self.model._start_operation('import_artifact', artifact_id=artifact_id)


class LibraryModel:
    def __init__(self, state_root, resource_root):
        self.state_root = Path(state_root).absolute()
        self.resource_root = Path(resource_root).resolve()
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self._lock = locked_file(self.state_root/'map-requests.lock', 'Map Library is already open for this state directory')
        self.queue_path = self.state_root/'map-requests.json'
        self.catalog_path = self.state_root/'map-catalog.json'
        self.staging = self.state_root/'map-worker-staging'
        self.worker = None
        self.active_id = None
        self.operation = None
        self.closed = False
        self.closing = False
        self.operation_notice = ''
        self.records = []
        self.catalog = []
        self.store = CatalogView(self)
        try:
            # Probe the inherited child lease before reclassifying any receipt.
            self._probe_lease()
            if INVENTORY.stat().st_size > MAX_JSON:
                raise ValueError('Dependency inventory exceeds size limit')
            self.inventory = json.loads(INVENTORY.read_text(encoding='utf-8'))
            self.inventory_sha256 = inventory_digest(self.inventory)
            try:
                data = read_private_json(self.queue_path, MAX_JSON)
            except FileNotFoundError:
                data = {'version': 1, 'requests': []}
            if (not isinstance(data, dict) or data.get('version') != 1
                    or not isinstance(data.get('requests'), list) or len(data['requests']) > 256):
                raise ValueError('Unsupported map request store')
            seen = set()
            for row in data['requests']:
                self._validate_receipt(row)
                if row['request_id'] in seen:
                    raise ValueError('Duplicate stored map request')
                seen.add(row['request_id'])
            self.records = data['requests']
            try:
                cached = read_private_json(self.catalog_path, MAX_CATALOG)
            except FileNotFoundError:
                cached = {'version': 1, 'catalog': []}
            if not isinstance(cached, dict) or cached.get('version') != 1:
                raise ValueError('Unsupported cached map catalog')
            self.catalog = validate_catalog(cached.get('catalog'))
            changed = False
            for row in self.records:
                if row['state'] in ('approved', 'running', 'cancelling'):
                    row.update(state='failed', error='Interrupted before completion; submit a new request to retry')
                    changed = True
            if changed:
                self._save()
        except BaseException:
            self._lock.close()
            raise

    def _probe_lease(self):
        lease = locked_file(self.state_root/'worker.lease', 'A previous Map Library child is still alive; wait for it to finish')
        lease.close()

    @staticmethod
    def _validate_receipt(row):
        if not isinstance(row, dict) or row.get('state') not in STATES:
            raise ValueError('Invalid map request receipt')
        try:
            valid_id = str(uuid.UUID(row['request_id'])) == row['request_id']
        except (KeyError, TypeError, ValueError, AttributeError):
            valid_id = False
        if not valid_id or row.get('preset') not in PRESETS:
            raise ValueError('Invalid map request identity or preset')
        spec = row.get('spec')
        if (not isinstance(spec, dict) or spec.get('version') != 1 or spec.get('preset') != row['preset']
                or not re.fullmatch('[0-9a-f]{64}', str(spec.get('dependency_sha256', '')))):
            raise ValueError('Invalid map request specification')
        digest = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if row.get('spec_sha256') != digest:
            raise ValueError('Map request specification checksum differs')

    def _save(self):
        atomic_json(self.queue_path, {'version': 1, 'requests': self.records})

    def _admit(self):
        if self.closed or self.closing:
            raise ValueError('Map Library is closing or closed')

    def _find(self, identity):
        return next((row for row in self.records if row['request_id'] == identity), None)

    def _require(self, identity):
        self._admit()
        row = self._find(identity)
        if row is None:
            raise ValueError('Unknown map request')
        return row

    def request(self, preset, request_id=None):
        self._admit()
        if preset not in PRESETS:
            raise ValueError('Unsupported map preset')
        identity = request_id or str(uuid.uuid4())
        try:
            if str(uuid.UUID(identity)) != identity:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ValueError('Request identity must be a canonical UUID') from None
        spec = {'version': 1, 'preset': preset, 'dependency_sha256': self.inventory_sha256}
        spec_hash = hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        existing = self._find(identity)
        if existing:
            if existing['spec_sha256'] != spec_hash:
                raise ValueError('Request identity already belongs to a different specification')
            return copy.deepcopy(existing)
        if sum(row['state'] in ('pending', 'approved') for row in self.records) >= 8:
            raise ValueError('Map request queue is full')
        if len(self.records) >= 256:
            raise ValueError('Map request history is full')
        row = dict(request_id=identity, preset=preset, spec=spec, spec_sha256=spec_hash,
                   state='pending', error=None, artifact_id=None, memory_estimate='unknown',
                   budget={'wall_seconds': 120, 'tile_bytes': 4194304, 'manifest_bytes': 1048576, 'log_bytes': 16384})
        self.records.append(row)
        try:
            self._save()
        except BaseException:
            self.records.pop()
            raise
        return copy.deepcopy(row)

    def _start_operation(self, operation, preset=None, artifact_id=None):
        self._admit()
        if self.worker is not None:
            raise ValueError('Another map operation is running')
        self._probe_lease()
        self.worker = Worker(preset, self.resource_root, self.staging, copy.deepcopy(self.inventory),
                             deadline=120, operation=operation, state_root=self.state_root, artifact_id=artifact_id)
        self.operation = operation
        self.operation_notice = 'Validating map data in the background' if operation != 'prepare' else 'Preparing map pack'
        return {'state': 'validating'}

    def import_existing(self, preset):
        if preset not in PRESETS:
            raise ValueError('Unsupported map preset')
        return self._start_operation('import_existing', preset=preset)

    def refresh_catalog(self):
        return self._start_operation('refresh')

    def approve(self, identity):
        row = self._require(identity)
        if row['state'] in ('approved', 'running', 'complete'):
            return copy.deepcopy(row)
        if row['state'] != 'pending':
            raise ValueError('Only pending requests can be approved')
        if self.worker is not None:
            raise ValueError('Another map operation is running')
        self._probe_lease()
        if row['spec']['dependency_sha256'] != self.inventory_sha256:
            raise ValueError('The approved recipe differs from this worker version')
        row['state'] = 'approved'
        try:
            self._save()
        except BaseException:
            row['state'] = 'pending'
            raise
        try:
            self._start_operation('prepare', preset=row['preset'])
            self.active_id = identity
            row['state'] = 'running'
        except (OSError, ValueError) as error:
            row.update(state='failed', error=str(error))
        self._save()
        return copy.deepcopy(row)

    def reject(self, identity):
        row = self._require(identity)
        if row['state'] == 'rejected':
            return copy.deepcopy(row)
        if row['state'] != 'pending':
            raise ValueError('Only pending requests can be rejected')
        row['state'] = 'rejected'
        self._save()
        return copy.deepcopy(row)

    def cancel(self, identity):
        row = self._require(identity)
        if row['state'] == 'running' and identity == self.active_id:
            self.worker.cancel()
            row.update(state='cancelling', error=None)
        elif row['state'] == 'pending':
            row['state'] = 'cancelled'
        elif row['state'] not in ('cancelled', 'cancelling'):
            raise ValueError('Only pending or running requests can be cancelled')
        self._save()
        return copy.deepcopy(row)

    def poll(self):
        if self.closed or self.closing or self.worker is None or not self.worker.poll():
            return False
        worker = self.worker
        row = self._find(self.active_id)
        if worker.cancelled or row and row['state'] == 'cancelling':
            self.operation_notice = 'Map operation cancelled'
            if row:
                row.update(state='cancelled', error=None)
        elif worker.error:
            self.operation_notice = str(worker.error)
            if row:
                row.update(state='failed', error=str(worker.error))
        else:
            try:
                result = worker.result
                if not isinstance(result, dict) or result.get('operation') != self.operation:
                    raise ValueError('Unexpected worker result')
                catalog = validate_catalog(result.get('catalog'))
                artifact = result.get('artifact')
                if row and (not isinstance(artifact, dict) or artifact.get('artifact_id') not in {item['artifact_id'] for item in catalog}):
                    raise ValueError('Prepared artifact is missing from worker catalog')
                atomic_json(self.catalog_path, {'version': 1, 'catalog': catalog})
                self.catalog = catalog
                self.operation_notice = str(result.get('message') or 'Map operation completed')[:2048]
                if row:
                    row.update(state='complete', error=None, artifact_id=artifact['artifact_id'])
                    row['completion'] = dict(request_id=row['request_id'], state='complete', artifact_id=artifact['artifact_id'],
                                             message='Map pack prepared and published; import is a separate action')
            except ValueError as error:
                self.operation_notice = str(error)
                if row:
                    row.update(state='failed', error=str(error))
        # Keep the worker and parent lock if receipt persistence fails. Poll or
        # close can retry; cleanup must never silently drop a durable result.
        if row:
            self._save()
        worker.close()
        discard_worker_metadata(worker.directory)
        self.worker = None
        self.active_id = None
        self.operation = None
        return True

    def list_requests(self):
        return copy.deepcopy(self.records)

    def completions(self):
        return [copy.deepcopy(row['completion']) for row in self.records if row['state'] == 'complete' and 'completion' in row]

    def close(self):
        if self.closed:
            return
        self.closing = True
        if self.worker is not None:
            self.worker.close()
            row = self._find(self.active_id)
            if row:
                if row['state'] == 'cancelling':
                    row.update(state='cancelled', error=None)
                elif row['state'] not in ('complete', 'cancelled', 'failed'):
                    row.update(state='failed', error='Map Library closed during preparation')
                self._save()
            discard_worker_metadata(self.worker.directory)
            self.worker = None
            self.active_id = None
            self.operation = None
        self._lock.close()
        self.closed = True
