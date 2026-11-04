"""Bounded local data-pack validation and transactional, immutable storage."""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from map_tiles import Archive
from map_palette import PALETTE_VERSION, BREAKPOINTS

HASH = re.compile(r'[0-9a-f]{64}\Z')
MAX_PACK_BYTES = 5 * 1024 * 1024
MAX_STORE_BYTES = 128 * 1024 * 1024
MAX_ARTIFACTS = 64


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(canonical(value) + b'\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def directory_fd(path):
    """Open every directory component without following a symlink."""
    path = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        yield fd
    finally:
        os.close(fd)


def read_at(fd, name, maximum):
    if '/' in name or name in ('', '.', '..'):
        raise ValueError('Invalid pack filename')
    child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
    with os.fdopen(child, 'rb') as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022:
            raise ValueError('Pack file ownership or mode is unsafe')
        if not 0 < info.st_size <= maximum:
            raise ValueError('Pack file exceeds size limit')
        data = stream.read(maximum + 1)
        if len(data) != info.st_size or len(data) > maximum:
            raise ValueError('Pack changed while reading')
        return data


def inspect_pack(directory):
    """Validate metadata and decode every tile with the existing map reader."""
    directory = Path(os.path.abspath(directory))
    with directory_fd(directory) as fd:
        # Archive uses paths internally. Retain an open directory and reject any
        # path replacement before returning; imports independently validate staging.
        opened = os.fstat(fd)
        archive = Archive(directory, hot_tiles=1)
        raw = read_at(fd, 'manifest.json', 1024 * 1024)
        if json.loads(raw) != archive.manifest:
            raise ValueError('Manifest changed while validating')
        files = {'manifest.json': dict(bytes=len(raw), sha256=digest(raw))}
        total = len(raw)
        for level in archive.levels:
            for key, item in level['tiles'].items():
                data = read_at(fd, item['file'], 65536)
                if len(data) != item['bytes'] or digest(data) != item['sha256']:
                    raise ValueError('Tile checksum mismatch')
                x, y = map(int, key.split(','))
                archive._load(level, (x, y), lambda: False)
                files[item['file']] = dict(bytes=len(data), sha256=digest(data))
                total += len(data)
                if total > MAX_PACK_BYTES:
                    raise ValueError('Pack exceeds disk budget')
        if set(os.listdir(fd)) != set(files):
            raise ValueError('Pack contains unlisted files')
        current = directory.stat(follow_symlinks=False)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise ValueError('Pack directory changed while validating')
        return dict(artifact_id=digest(canonical(files)), manifest_sha256=digest(raw),
                    raw_manifest_sha256=digest(raw),
                    canonical_manifest_sha256=digest(canonical(archive.manifest)),
                    bytes=total, files=files, state='validated',
                    semantic_identity=archive.manifest['identity'],
                    manifest=archive.manifest)


class ArtifactStore:
    def __init__(self, state_root, resource_root=None):
        self.root = Path(os.path.abspath(state_root))
        self.resource_root = Path(resource_root).resolve() if resource_root is not None else None
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with directory_fd(self.root):
            pass
        self.artifacts = self.root / 'artifacts'
        self.descriptors = self.root / 'descriptors'
        self.staging = self.root / 'staging'
        for path in (self.artifacts, self.descriptors, self.staging):
            path.mkdir(mode=0o700, exist_ok=True)
            with directory_fd(path):
                pass

    @contextmanager
    def _lock(self):
        fd = os.open(self.root / 'artifact.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            yield
        finally:
            os.close(fd)

    def _compatibility(self, descriptor):
        if self.resource_root is None:
            return False, 'Source and palette compatibility has not been checked'
        manifest = descriptor['manifest']
        packet = self.resource_root.parents[1] / 'packet-console'
        try:
            if (manifest['palette']['version'] != PALETTE_VERSION
                    or manifest['palette']['breakpoints'] != json.loads(json.dumps(BREAKPOINTS))):
                return False, 'Pack palette settings differ from the current viewer'
            sources = {row['file']: row['sha256'] for row in manifest['sources']}
            expected = {'n810-map-next.py', 'n810-map-rgb.py', 'n810-map.py', 'n810-walk-map.py'}
            expected.update('maps/' + p.name for p in (packet / 'maps').iterdir() if p.is_file())
            if set(sources) != expected:
                return False, 'Pack source catalog differs from the local map catalog'
            for name, checksum in sources.items():
                path = packet / name
                with directory_fd(path.parent) as fd:
                    if digest(read_at(fd, path.name, 64 * 1024 * 1024)) != checksum:
                        return False, 'Pack source differs: ' + name
            palette_path = self.resource_root / 'map_palette.py'
            with directory_fd(palette_path.parent) as fd:
                if digest(read_at(fd, palette_path.name, 1024 * 1024)) != manifest['palette']['sha256']:
                    return False, 'Pack palette differs from the current viewer palette'
            identity = dict(sources=manifest['sources'], palette=manifest['palette'],
                            center=manifest['levels'][0]['center'], span=manifest['levels'][0]['span'],
                            widths=[level['width'] for level in manifest['levels']], terrain=True, roads=True)
            semantic = digest(json.dumps(identity, sort_keys=True).encode())
            if semantic != manifest['identity']:
                return False, 'Pack semantic identity differs from its declared inputs'
            return True, 'Inputs and palette match; viewer activation is separate'
        except (OSError, ValueError, KeyError) as error:
            return False, 'Compatibility check failed: ' + str(error)

    def _decorate(self, descriptor, imported=False):
        value = {k: v for k, v in descriptor.items() if k != 'manifest'}
        compatible, reason = self._compatibility(descriptor)
        value.update(path=str(self.artifacts / descriptor['artifact_id']),
                     state='imported' if imported else 'published',
                     compatible=compatible, compatibility_reason=reason)
        return value

    def _library(self):
        path = self.root / 'library.json'
        if not path.exists():
            return dict(version=1, artifacts=[])
        with directory_fd(self.root) as fd:
            value = json.loads(read_at(fd, 'library.json', 65536))
        if (not isinstance(value, dict) or value.get('version') != 1
                or not isinstance(value.get('artifacts'), list)
                or len(value['artifacts']) > MAX_ARTIFACTS
                or any(not isinstance(x, str) or not HASH.fullmatch(x) for x in value['artifacts'])):
            raise ValueError('Invalid local library index')
        return value

    def _publish(self, source):
        original = inspect_pack(source)
        destination = self.artifacts / original['artifact_id']
        if destination.exists():
            installed = inspect_pack(destination)
            if installed['files'] != original['files']:
                raise ValueError('Existing immutable artifact differs')
            value = self._decorate(installed, original['artifact_id'] in self._library()['artifacts'])
            descriptor_path = self.descriptors / (value['artifact_id'] + '.json')
            if not descriptor_path.exists():
                atomic_json(descriptor_path, value)
            return value
        entries = list(self.descriptors.iterdir())
        if len(entries) >= MAX_ARTIFACTS:
            raise ValueError('Artifact count budget reached')
        total = sum(p.stat().st_size for p in self.artifacts.rglob('*') if p.is_file())
        if total + original['bytes'] > MAX_STORE_BYTES:
            raise ValueError('Artifact storage budget reached')
        with tempfile.TemporaryDirectory(prefix='pack-', dir=self.staging) as folder:
            staged = Path(folder) / 'pack'
            staged.mkdir(mode=0o700)
            with directory_fd(source) as fd:
                for name, expected in original['files'].items():
                    data = read_at(fd, name, expected['bytes'])
                    if len(data) != expected['bytes'] or digest(data) != expected['sha256']:
                        raise ValueError('Source changed during import')
                    child = os.open(staged / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(child, 'wb') as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
            verified = inspect_pack(staged)
            if verified['artifact_id'] != original['artifact_id']:
                raise ValueError('Imported content identity differs')
            fd = os.open(staged, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            staged.rename(destination)
            fd = os.open(self.artifacts, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        # The content directory is self-describing, so a crash before this index
        # write is recoverable by reimporting the same pack without changing it.
        value = self._decorate(verified)
        atomic_json(self.descriptors / (value['artifact_id'] + '.json'), value)
        return value

    def publish_pack(self, source):
        with self._lock():
            return self._publish(source)

    def _import(self, descriptor):
        if self.resource_root is not None and not descriptor['compatible']:
            raise ValueError(descriptor['compatibility_reason'])
        library = self._library()
        if descriptor['artifact_id'] not in library['artifacts']:
            library['artifacts'].append(descriptor['artifact_id'])
            atomic_json(self.root / 'library.json', library)
        return dict(descriptor, state='imported')

    def import_pack(self, source):
        with self._lock():
            candidate = inspect_pack(source)
            compatible, reason = self._compatibility(candidate)
            if self.resource_root is not None and not compatible:
                raise ValueError(reason)
            return self._import(self._publish(source))

    def import_artifact(self, artifact_id):
        if not isinstance(artifact_id, str) or not HASH.fullmatch(artifact_id):
            raise ValueError('Invalid artifact identity')
        with self._lock():
            descriptor = inspect_pack(self.artifacts / artifact_id)
            if descriptor['artifact_id'] != artifact_id:
                raise ValueError('Stored artifact identity differs')
            return self._import(self._decorate(descriptor))

    def list_artifacts(self):
        imported = set(self._library()['artifacts'])
        results = []
        with directory_fd(self.descriptors) as fd:
            names = sorted(os.listdir(fd))
            if len(names) > MAX_ARTIFACTS:
                raise ValueError('Artifact count exceeds budget')
            for name in names:
                if not name.endswith('.json') or not HASH.fullmatch(name[:-5]):
                    raise ValueError('Invalid artifact descriptor filename')
                row = json.loads(read_at(fd, name, 512 * 1024))
                if row.get('artifact_id') != name[:-5]:
                    raise ValueError('Artifact descriptor identity differs')
                row['state'] = 'imported' if row['artifact_id'] in imported else 'published'
                try:
                    pack = self.artifacts / row['artifact_id']
                    with directory_fd(pack) as pack_fd:
                        raw = read_at(pack_fd, 'manifest.json', 1024 * 1024)
                        if digest(raw) != row['manifest_sha256']:
                            raise ValueError('Stored manifest checksum differs')
                        archive = Archive(pack, hot_tiles=1)
                        if digest(canonical(archive.manifest)) != row['canonical_manifest_sha256']:
                            raise ValueError('Stored canonical manifest differs')
                    row['compatible'], row['compatibility_reason'] = self._compatibility(
                        dict(manifest=archive.manifest))
                except (OSError, ValueError, KeyError) as error:
                    row.update(compatible=False, compatibility_reason='Stored pack unavailable: ' + str(error))
                results.append(row)
        return results
