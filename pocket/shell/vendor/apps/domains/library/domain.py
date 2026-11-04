"""Local collection ownership; no implicit home scan, network, or process launch."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from hashlib import sha256
import mimetypes
import os
from pathlib import Path
import stat
from threading import Event
import time
from urllib.parse import urlsplit

MAX_DOCUMENTS = 500
MAX_ENTRIES = 2000
MAX_DEPTH = 6
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_PREVIEW_BYTES = 128 * 1024
TEXT_TYPES = {'.txt', '.md', '.rst', '.html', '.htm', '.json', '.xml', '.csv', '.log', '.py', '.c', '.h', '.s', '.yaml', '.yml', '.toml'}


@dataclass(frozen=True, slots=True)
class CommandResult:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class Collection:
    id: str
    title: str
    root: str
    kind: str = 'documents'


@dataclass(frozen=True, slots=True)
class CollectionStatus:
    id: str
    title: str
    root: str
    state: str
    count: int
    message: str


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    collection_id: str
    relative_path: str
    title: str
    kind: str
    size: int
    modified_ns: int
    text: str = ''


@dataclass(frozen=True, slots=True)
class OpenedDocument:
    id: str
    path: str
    media_type: str
    text: str | None
    truncated: bool
    external: bool


@dataclass(frozen=True, slots=True)
class Snapshot:
    revision: int = 0
    status: str = 'unindexed'
    collections: tuple[CollectionStatus, ...] = ()
    documents: tuple[Document, ...] = ()
    opened: OpenedDocument | None = None
    pending: str | None = None
    result: CommandResult | None = None
    kiwix_state: str = 'unavailable'
    kiwix_url: str | None = None


def _check(cancel):
    if cancel.is_set():
        raise InterruptedError('Operation cancelled')


def _text(payload):
    text = payload.decode('utf-8', errors='replace')
    return ''.join(c for c in text if c in '\n\t' or c.isprintable())


def _read(path, limit):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError('File is no longer a regular document')
        return stream.read(limit)


def _root(collection):
    root = Path(collection.root).expanduser().resolve()
    if root == Path(root.anchor) or root == Path.home().resolve():
        raise ValueError('Choose a specific collection folder, rather than the filesystem or home root')
    return root


def _scan(collections, current, cancel):
    documents = []
    states = []
    budget = MAX_INDEX_BYTES
    entries = 0
    deadline = time.monotonic() + 5
    for collection in collections:
        _check(cancel)
        count = 0
        truncated = False
        try:
            root = _root(collection)
            if not root.exists():
                states.append(CollectionStatus(collection.id, collection.title, str(root), 'missing', 0, 'Collection folder does not exist'))
                continue
            if not root.is_dir():
                states.append(CollectionStatus(collection.id, collection.title, str(root), 'unavailable', 0, 'Collection root must be a folder'))
                continue
            stack = [(root, 0)]
            while stack:
                _check(cancel)
                if entries >= MAX_ENTRIES or len(documents) >= MAX_DOCUMENTS or time.monotonic() > deadline:
                    truncated = True
                    break
                folder, depth = stack.pop()
                with os.scandir(folder) as iterator:
                    for entry in iterator:
                        _check(cancel)
                        entries += 1
                        if entries > MAX_ENTRIES or len(documents) >= MAX_DOCUMENTS or time.monotonic() > deadline:
                            truncated = True
                            break
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if depth < MAX_DEPTH:
                                stack.append((Path(entry.path), depth + 1))
                            else:
                                truncated = True
                            continue
                        if not entry.is_file(follow_symlinks=False):
                            continue
                        path = Path(entry.path)
                        info = entry.stat(follow_symlinks=False)
                        relative = path.relative_to(root).as_posix()
                        identifier = sha256((collection.id + '\0' + relative).encode()).hexdigest()
                        text = ''
                        if path.suffix.lower() in TEXT_TYPES and budget > 0:
                            if not path.resolve().is_relative_to(root):
                                raise ValueError('Document moved outside its collection during scan')
                            payload = _read(path, min(32768, budget))
                            budget -= len(payload)
                            text = _text(payload)
                        documents.append(Document(identifier, collection.id, relative, path.name,
                                                  collection.kind, info.st_size, info.st_mtime_ns, text))
                        count += 1
            states.append(CollectionStatus(collection.id, collection.title, str(root), 'limited' if truncated else 'ready', count,
                                           'Index bound reached; narrow the collection root' if truncated else 'Local collection indexed'))
        except (OSError, ValueError) as error:
            states.append(CollectionStatus(collection.id, collection.title, collection.root, 'error', count, str(error)[:512]))
    _check(cancel)
    documents.sort(key=lambda row: (row.collection_id, row.relative_path.casefold(), row.relative_path))
    return replace(current, status='ready' if documents else 'empty', collections=tuple(states),
                   documents=tuple(documents), opened=None, pending=None,
                   result=CommandResult('done', f'{len(documents)} local files indexed'))


def _open(document, collection, current, cancel):
    _check(cancel)
    root = _root(collection)
    indexed_root = next(row.root for row in current.collections if row.id == collection.id)
    if str(root) != indexed_root:
        raise ValueError('Collection root changed; scan the collection again')
    path = root / document.relative_path
    resolved = path.resolve()
    if path.is_symlink() or not resolved.is_relative_to(root):
        raise ValueError('Document is outside its configured collection')
    if not resolved.is_file():
        raise FileNotFoundError('Document is no longer available; scan the collection again')
    media = mimetypes.guess_type(resolved.name)[0] or 'application/octet-stream'
    preview = None
    truncated = False
    if resolved.suffix.lower() in TEXT_TYPES:
        payload = _read(resolved, MAX_PREVIEW_BYTES + 1)
        truncated = len(payload) > MAX_PREVIEW_BYTES
        preview = _text(payload[:MAX_PREVIEW_BYTES])
    _check(cancel)
    opened = OpenedDocument(document.id, str(resolved), media, preview, truncated, preview is None)
    message = 'Text preview ready' if preview is not None else 'File available; use a suitable viewer for this format'
    return replace(current, opened=opened, pending=None, result=CommandResult('done', message))


class Library:
    """One bounded local scan/open operation; search reads the current snapshot."""
    def __init__(self, collections=(), kiwix_url=None):
        collections = tuple(collections)
        if len(collections) > 16 or any(not isinstance(c, Collection) for c in collections):
            raise ValueError('Use at most 16 Collection values')
        for collection in collections:
            if not isinstance(collection, Collection) or not all(isinstance(v, str) and v for v in (collection.id, collection.title, collection.root, collection.kind)):
                raise ValueError('Collection requires an ID, title, root, and kind')
            if len(collection.id) > 100 or len(collection.title) > 256 or len(collection.root) > 4096:
                raise ValueError('Collection configuration exceeds bounds')
        if len({c.id for c in collections}) != len(collections):
            raise ValueError('Use at most 16 collections with unique IDs')
        if kiwix_url is not None:
            parsed = urlsplit(kiwix_url)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError('Use an HTTP or HTTPS Kiwix service URL without credentials')
        self._collections = collections
        states = tuple(CollectionStatus(c.id, c.title, c.root, 'unindexed', 0, 'Scan this collection to index local files') for c in collections)
        self._snapshot = Snapshot(collections=states, kiwix_url=kiwix_url,
                                  kiwix_state='configured_unverified' if kiwix_url else 'unavailable')
        self._pool = None
        self._future = None
        self._cancel = Event()
        self._closed = False

    @property
    def busy(self):
        return self._future is not None

    def snapshot(self):
        return self._snapshot

    def search(self, query='', collection_id=None, limit=100):
        if not isinstance(query, str) or len(query) > 256 or type(limit) is not int or not 1 <= limit <= MAX_DOCUMENTS:
            raise ValueError('Use a query up to 256 characters and limit 1–500')
        terms = query.casefold().split()
        result = []
        for document in self._snapshot.documents:
            if collection_id is not None and document.collection_id != collection_id:
                continue
            haystack = (document.title + '\n' + document.relative_path + '\n' + document.text).casefold()
            if all(term in haystack for term in terms):
                result.append(document)
                if len(result) == limit:
                    break
        return tuple(result)

    def _submit(self, name, work):
        if self._closed:
            return CommandResult('closed', 'Library is closed')
        if self.busy:
            return CommandResult('busy', 'Library already has an operation in progress')
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='library')
        self._cancel = Event()
        self._snapshot = replace(self._snapshot, revision=self._snapshot.revision + 1, pending=name,
                                 result=CommandResult('accepted', name))
        self._future = self._pool.submit(work, self._cancel)
        return self._snapshot.result

    def scan(self):
        current = self._snapshot
        return self._submit('scan', lambda cancel: _scan(self._collections, current, cancel))

    def open(self, identifier):
        document = next((row for row in self._snapshot.documents if row.id == identifier), None)
        if document is None:
            return CommandResult('invalid', 'Choose a file from the current library index')
        collection = next(c for c in self._collections if c.id == document.collection_id)
        current = self._snapshot
        return self._submit('open', lambda cancel: _open(document, collection, current, cancel))

    def poll(self):
        if self._future is None or not self._future.done():
            return False
        future, self._future = self._future, None
        try:
            result = future.result()
            self._snapshot = replace(result, revision=self._snapshot.revision + 1, pending=None)
        except Exception as error:
            self._snapshot = replace(self._snapshot, revision=self._snapshot.revision + 1, pending=None,
                                     result=CommandResult('cancelled' if isinstance(error, InterruptedError) else 'error', str(error)[:512]))
        return True

    def cancel(self):
        self._cancel.set()

    def close(self):
        self._closed = True
        self.cancel()
        if self._pool:
            self._pool.shutdown(wait=False, cancel_futures=True)
