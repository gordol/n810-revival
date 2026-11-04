# Reader domain

Standard-library RSS/Atom reading, offline article text, and durable read/saved
state. No framework, display, account, radio, scheduled refresh, or global event
store dependency. One owner per cache folder is shared by all its views; creating
independent writers for the same folder is unsupported.

## Desktop integration contract

```python
from domains.reader import Reader

reader = Reader(cache_root)  # Explicit state folder; queues local restore only.
reader.poll()               # Call on the domain/event-loop thread while busy.
snapshot = reader.snapshot()
```

`snapshot()` and `search(query='', feed_id=None, saved_only=False,
unread_only=False, limit=100)` read memory only. Snapshots, feeds, and articles
are frozen dataclasses containing immutable tuples/values. Article IDs hash the
source feed plus its GUID/Atom ID, then URL, then title/date/summary as a fallback.
Selection/focus/scrolling belong to each view, not this owner.

Commands return `CommandResult(code, message)` immediately. `accepted` means
queued, not completed. Other immediate codes are `busy`, `closed`, `invalid`, and
`blocked`. One lazy single-thread worker admits one operation, including a
completed result awaiting `poll()`. The worker returns a replacement value;
`poll()` publishes it and increments `snapshot.revision` on the caller thread.
The initial constructor restore is also asynchronous.

| Command | Effect |
|---|---|
| `load()` | Restore local cache; no network |
| `import_local(path)` | Import a regular local RSS/Atom file and save the cache |
| `refresh(url)` | Explicitly fetch one HTTP(S) feed and save its items |
| `refresh_article(id)` | Explicitly fetch the selected article URL and cache plain text |
| `set_read(id, value=True)` | Atomically persist read/unread state |
| `set_saved(id, value=True)` | Atomically persist saved/unsaved state |
| `cancel()` / `close()` | Cooperatively cancel / reject new commands and stop the worker |

Render only when the relevant revision or local interaction state changes. Poll
at a modest cadence while `busy`; no periodic wake is required when idle. Reuse
the same owner when a window hides/reopens. On final shutdown call `close()`.
`poll()` returns whether a completion was applied. Completion/error details are
in `snapshot.result`; `pending` names the admitted command or is `None`.
`status` describes available cached data (`empty` or `ready`), not network health.
On a failed refresh the last good articles remain available, with an error result.

## Content, provenance, storage and limits

- No URL is fetched on construction, rendering, local import, search, or opening
  a cached item. Only explicit `refresh` and `refresh_article` commands fetch.
  `SUGGESTED_FEEDS` declares HN/Lobsters URLs without querying them.
- Feed content is already usable offline. `content_source='feed'` distinguishes
  it from an explicitly fetched article (`'article'`). A feed may supply only a
  summary. Full article fetch is lightweight HTML-to-text, without JavaScript,
  authenticated sessions, media, or a promise of extracting only the article body.
- `published` preserves the feed's date string or `None`; import time is separate.
  No current publication date, received time, or live freshness is invented.
- HTTP(S) only, no embedded URL credentials; redirects remain HTTP(S). Input is
  capped at 2 MiB, socket operations use a five-second timeout, and reads check a
  twelve-second elapsed deadline and cancellation between chunks. DNS/platform
  IO is not forcibly interruptible; there is no hard real-time cancellation claim.
- Up to 32 feeds and 300 retained articles; saved items survive ordinary item
  eviction. Summary/title/article text caps are 2000/512/12000 characters. URL and
  author caps are 4096/256. RSS/Atom GUIDs keep flags through changed titles.
- XML DTD/entity declarations are rejected. HTML scripts/styles and terminal
  control characters are removed. No resource referenced by HTML is fetched.
- `reader.json` is a bounded version-1 cache (8 MiB), written through a flushed,
  fsynced temporary file and atomic replace. Failed persistence leaves the prior
  in-memory snapshot and cache intact. A malformed cache blocks writes until a
  successful explicit `load()`; the original file is preserved.
- Cancellation checks precede durable commit. If commit has already completed,
  the completed result can still be applied; cancellation does not undo a save.

## Immediately usable local flow

Run from `packet-console/`, using an explicit scratch cache:

```sh
python3 -m domains.reader --cache /tmp/pocket-reader-example import domains/reader/fixtures/field-notes.rss
python3 -m domains.reader --cache /tmp/pocket-reader-example list
python3 -m domains.reader --cache /tmp/pocket-reader-example read ARTICLE_ID
python3 -m domains.reader --cache /tmp/pocket-reader-example save ARTICLE_ID
python3 -m domains.reader --cache /tmp/pocket-reader-example list --saved
```

Use the ID emitted by `list`. Commands return JSON and a nonzero exit on failure.
The included feed is an authored offline example, never labeled a live source.
To fetch an actual public feed, explicitly run `refresh FEED_URL`. To fetch its
selected linked page, explicitly run `article ARTICLE_ID`. A hidden view never
initiates either operation.

Tests: `python3 -B -m unittest domains.reader.tests.test_domain -v`.
