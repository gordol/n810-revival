"""Feed parsing, offline reading state, and a single bounded IO owner."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from html.parser import HTMLParser
import json
import math
import os
from pathlib import Path
import stat
import tempfile
from threading import Event
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

MAX_INPUT = 2 * 1024 * 1024
MAX_CACHE = 8 * 1024 * 1024
MAX_ARTICLES = 300
MAX_FEEDS = 32
SUGGESTED_FEEDS = (
    ('Hacker News', 'https://news.ycombinator.com/rss'),
    ('Lobsters', 'https://lobste.rs/rss'),
)


@dataclass(frozen=True, slots=True)
class CommandResult:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class Feed:
    id: str
    title: str
    source: str
    imported_at: float


@dataclass(frozen=True, slots=True)
class Article:
    id: str
    feed_id: str
    title: str
    url: str
    author: str
    published: str | None
    summary: str
    content: str
    read: bool = False
    saved: bool = False
    content_source: str = 'feed'


@dataclass(frozen=True, slots=True)
class Snapshot:
    revision: int = 0
    status: str = 'empty'
    feeds: tuple[Feed, ...] = ()
    articles: tuple[Article, ...] = ()
    pending: str | None = None
    result: CommandResult | None = None


def _identity(value):
    return sha256(value.encode('utf-8')).hexdigest()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        elif tag in ('p', 'div', 'br', 'li', 'h1', 'h2', 'h3', 'pre') and not self.hidden:
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        elif tag in ('p', 'div', 'li', 'pre') and not self.hidden:
            self.parts.append('\n')

    def handle_data(self, value):
        if not self.hidden:
            self.parts.append(value)


def plain_text(value, limit=12000):
    parser = _Text()
    parser.feed(value[:MAX_INPUT])
    text = ''.join(parser.parts)
    text = ''.join(c for c in text if c in '\n\t' or c.isprintable())
    return '\n'.join(' '.join(line.split()) for line in text.splitlines() if line.strip())[:limit]


def _name(element):
    return element.tag.rsplit('}', 1)[-1].lower()


def _element(parent, *names):
    return next((child for child in parent if _name(child) in names), None)


def _value(parent, *names):
    child = _element(parent, *names)
    if child is None:
        return ''
    if len(child):
        return ' '.join(child.itertext())
    return child.text or ''


def _url(value, source):
    value = urljoin(source, value.strip())
    parsed = urlsplit(value)
    return value[:4096] if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password else ''


def parse_feed(payload, source, imported_at=None):
    """Return one Feed and bounded Articles; source dates remain unmodified strings."""
    if not isinstance(payload, bytes) or len(payload) > MAX_INPUT:
        raise ValueError('Feed must be at most 2 MiB')
    declaration = payload.replace(b'\x00', b'').lower()
    if b'<!doctype' in declaration or b'<!entity' in declaration:
        raise ValueError('Feed declarations and entities are unsupported')
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise ValueError('Invalid feed XML: ' + str(error)) from error
    kind = _name(root)
    if kind == 'rss':
        container = _element(root, 'channel')
        if container is None:
            raise ValueError('RSS channel is missing')
        entries = [row for row in container if _name(row) == 'item']
    elif kind == 'feed':
        container = root
        entries = [row for row in root if _name(row) == 'entry']
    elif kind == 'rdf':
        container = _element(root, 'channel')
        if container is None:
            raise ValueError('RSS channel is missing')
        entries = [row for row in root if _name(row) == 'item']
    else:
        raise ValueError('Expected RSS or Atom feed')
    feed_id = _identity(source)
    feed = Feed(feed_id, plain_text(_value(container, 'title'), 512) or source[:512], source,
                time.time() if imported_at is None else imported_at)
    articles = []
    seen = set()
    for row in entries[:MAX_ARTICLES]:
        title = plain_text(_value(row, 'title'), 512) or 'Untitled'
        link = _value(row, 'link')
        if kind == 'feed':
            alternate = next((c for c in row if _name(c) == 'link' and c.get('rel', 'alternate') == 'alternate'), None)
            link = alternate.get('href', '') if alternate is not None else ''
        link = _url(link, source)
        published = _value(row, 'published', 'pubdate', 'date', 'updated').strip()[:128] or None
        summary = plain_text(_value(row, 'description', 'summary'), 2000)
        content = plain_text(_value(row, 'encoded', 'content')) or summary
        author = plain_text(_value(row, 'creator', 'author'), 256)
        key = _value(row, 'guid', 'id').strip() or link or title + '\0' + str(published) + '\0' + summary
        identifier = _identity(feed_id + '\0' + key)
        if identifier not in seen:
            articles.append(Article(identifier, feed_id, title, link, author, published, summary, content))
            seen.add(identifier)
    return feed, tuple(articles)


def _check(cancel):
    if cancel.is_set():
        raise InterruptedError('Operation cancelled')


def _atomic(path, snapshot, cancel):
    document = dict(version=1, feeds=[asdict(f) for f in snapshot.feeds],
                    articles=[asdict(a) for a in snapshot.articles])
    encoded = json.dumps(document, ensure_ascii=True).encode('utf-8')
    if len(encoded) > MAX_CACHE:
        raise ValueError('Reader cache exceeds 8 MiB')
    _check(cancel)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        fd, temporary = tempfile.mkstemp(prefix='.reader-', dir=path.parent)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        _check(cancel)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


def _load(path, cancel):
    _check(cancel)
    if not path.exists():
        return Snapshot(result=CommandResult('done', 'No cached feeds yet; import a feed or refresh an explicit URL'))
    if path.stat().st_size > MAX_CACHE:
        raise ValueError('Reader cache exceeds 8 MiB')
    with path.open('rb') as stream:
        payload = stream.read(MAX_CACHE + 1)
    if len(payload) > MAX_CACHE:
        raise ValueError('Reader cache exceeds 8 MiB')
    data = json.loads(payload)
    if not isinstance(data, dict) or data.get('version') != 1:
        raise ValueError('Unsupported reader cache')
    feeds, articles = data.get('feeds'), data.get('articles')
    if not isinstance(feeds, list) or len(feeds) > MAX_FEEDS or not isinstance(articles, list) or len(articles) > MAX_ARTICLES:
        raise ValueError('Invalid reader cache bounds')
    feeds = tuple(Feed(**row) for row in feeds)
    articles = tuple(Article(**row) for row in articles)
    ids = {f.id for f in feeds}
    if len(ids) != len(feeds) or len({a.id for a in articles}) != len(articles):
        raise ValueError('Duplicate reader identity')
    for feed in feeds:
        if not all(isinstance(v, str) for v in (feed.id, feed.title, feed.source)) or len(feed.source) > 4096 or len(feed.id) != 64 or len(feed.title) > 512:
            raise ValueError('Invalid cached feed')
        if type(feed.imported_at) not in (int, float) or not math.isfinite(feed.imported_at):
            raise ValueError('Invalid feed import timestamp')
    for article in articles:
        if article.feed_id not in ids or type(article.read) is not bool or type(article.saved) is not bool:
            raise ValueError('Invalid article state')
        for key, limit in (('id', 64), ('feed_id', 64), ('title', 512), ('url', 4096), ('author', 256), ('summary', 2000), ('content', 12000)):
            if not isinstance(getattr(article, key), str) or len(getattr(article, key)) > limit:
                raise ValueError('Invalid cached article ' + key)
        if article.published is not None and (not isinstance(article.published, str) or len(article.published) > 128):
            raise ValueError('Invalid cached article date')
        if article.content_source not in ('feed', 'article'):
            raise ValueError('Invalid article content source')
    _check(cancel)
    return Snapshot(status='ready', feeds=feeds, articles=articles, result=CommandResult('done', 'Offline cache restored'))


def _merge(current, feed, articles):
    feeds = (feed,) + tuple(f for f in current.feeds if f.id != feed.id)
    if len(feeds) > MAX_FEEDS:
        raise ValueError('Reader supports at most 32 feeds')
    previous = {a.id: a for a in current.articles}
    incoming = []
    for article in articles:
        old = previous.get(article.id)
        if old:
            article = replace(article, read=old.read, saved=old.saved)
            if old.content_source == 'article' and old.url == article.url:
                article = replace(article, content=old.content, content_source='article')
        incoming.append(article)
    incoming = tuple(incoming)
    incoming_ids = {a.id for a in incoming}
    combined = incoming + tuple(a for a in current.articles if a.id not in incoming_ids)
    saved = tuple(a for a in combined if a.saved)
    retained = saved + tuple(a for a in combined if not a.saved)[:MAX_ARTICLES-len(saved)]
    return Snapshot(status='ready', feeds=feeds, articles=retained,
                    result=CommandResult('done', f'Imported {len(incoming)} items; {len(retained)} retained'))


def _download(url, cancel):
    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or len(url) > 4096:
        raise ValueError('Use an HTTP or HTTPS feed URL without credentials')
    request = Request(url, headers={'User-Agent': 'PocketReader/1.0', 'Accept': 'application/atom+xml, application/rss+xml, application/xml, text/html, text/plain, text/xml'})
    _check(cancel)
    deadline = time.monotonic() + 12
    with urlopen(request, timeout=5) as response:
        if urlsplit(response.url).scheme not in ('http', 'https'):
            raise ValueError('Unsupported feed redirect')
        chunks = []
        total = 0
        while True:
            _check(cancel)
            if time.monotonic() > deadline:
                raise TimeoutError('Feed refresh exceeded its deadline')
            chunk = response.read(min(32768, MAX_INPUT + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > MAX_INPUT:
                raise ValueError('Feed exceeds 2 MiB')
    return b''.join(chunks)


class Reader:
    """One operation in flight; workers return immutable values to poll()."""
    def __init__(self, cache_root):
        self.path = Path(cache_root).expanduser() / 'reader.json'
        self._snapshot = Snapshot()
        self._pool = None
        self._future = None
        self._cancel = Event()
        self._closed = False
        self._cache_failed = False
        self.load()

    @property
    def busy(self):
        return self._future is not None

    def snapshot(self):
        return self._snapshot

    def search(self, query='', feed_id=None, saved_only=False, unread_only=False, limit=100):
        if not isinstance(query, str) or len(query) > 256 or type(limit) is not int or not 1 <= limit <= MAX_ARTICLES:
            raise ValueError('Use a query up to 256 characters and limit 1–300')
        terms = query.casefold().split()
        rows = (a for a in self._snapshot.articles if (feed_id is None or a.feed_id == feed_id)
                and (not saved_only or a.saved) and (not unread_only or not a.read))
        return tuple(a for a in rows if all(t in (a.title + '\n' + a.content).casefold() for t in terms))[:limit]

    def _submit(self, name, work):
        if self._closed:
            return CommandResult('closed', 'Reader is closed')
        if self.busy:
            return CommandResult('busy', 'Reader already has an operation in progress')
        if self._cache_failed and name != 'load':
            return CommandResult('blocked', 'Cache could not be restored; preserve or repair it before writing')
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='reader')
        self._cancel = Event()
        self._snapshot = replace(self._snapshot, revision=self._snapshot.revision + 1, pending=name,
                                 result=CommandResult('accepted', name))
        self._future = self._pool.submit(work, self._cancel)
        return self._snapshot.result

    def load(self):
        return self._submit('load', lambda cancel: _load(self.path, cancel))

    def import_local(self, path):
        current = self._snapshot
        source = Path(path).expanduser()
        def work(cancel):
            _check(cancel)
            resolved = source.resolve()
            fd = os.open(resolved, os.O_RDONLY | os.O_NONBLOCK)
            with os.fdopen(fd, 'rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError('Choose a regular local feed file')
                payload = stream.read(MAX_INPUT + 1)
            feed, articles = parse_feed(payload, resolved.as_uri())
            result = _merge(current, feed, articles)
            _atomic(self.path, result, cancel)
            return result
        return self._submit('import', work)

    def refresh(self, url):
        if not isinstance(url, str):
            return CommandResult('invalid', 'Feed URL must be a string')
        current = self._snapshot
        def work(cancel):
            feed, articles = parse_feed(_download(url, cancel), url)
            result = _merge(current, feed, articles)
            _atomic(self.path, result, cancel)
            return result
        return self._submit('refresh', work)

    def refresh_article(self, identifier):
        article = next((row for row in self._snapshot.articles if row.id == identifier), None)
        if article is None or not article.url:
            return CommandResult('invalid', 'Choose an article with an HTTP or HTTPS URL')
        current = self._snapshot
        def work(cancel):
            content = plain_text(_download(article.url, cancel).decode('utf-8', errors='replace'))
            if not content:
                raise ValueError('Page has no readable text; use a browser for this site')
            rows = tuple(replace(a, content=content, content_source='article') if a.id == identifier else a for a in current.articles)
            result = replace(current, articles=rows, pending=None, result=CommandResult('done', 'Article text cached, up to 12000 characters'))
            _atomic(self.path, result, cancel)
            return result
        return self._submit('article', work)

    def _flag(self, identifier, name, value):
        if not isinstance(identifier, str) or type(value) is not bool or identifier not in {a.id for a in self._snapshot.articles}:
            return CommandResult('invalid', 'Choose a retained article and a boolean state')
        current = self._snapshot
        def work(cancel):
            articles = tuple(replace(a, **{name: value}) if a.id == identifier else a for a in current.articles)
            result = replace(current, articles=articles, pending=None, result=CommandResult('done', name + ' state saved'))
            _atomic(self.path, result, cancel)
            return result
        return self._submit(name, work)

    def set_read(self, identifier, value=True):
        return self._flag(identifier, 'read', value)

    def set_saved(self, identifier, value=True):
        return self._flag(identifier, 'saved', value)

    def poll(self):
        if self._future is None or not self._future.done():
            return False
        future, self._future = self._future, None
        pending = self._snapshot.pending
        try:
            result = future.result()
            self._snapshot = replace(result, revision=self._snapshot.revision + 1, pending=None)
            if pending == 'load':
                self._cache_failed = False
        except Exception as error:
            if pending == 'load' and not isinstance(error, InterruptedError):
                self._cache_failed = True
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
