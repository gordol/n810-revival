# Library domain

Bounded metadata indexing, text search, and local document previews over explicit
collection roots. No UI, process launch, home-directory discovery, network scan,
SQLite service, or ZIM parser. Collections can hold manuals, documents, captures,
and prepared map packs without turning them into radio entities.

## Desktop integration contract

```python
from domains.library import Collection, Library

library = Library((Collection('manuals', 'Manuals', explicit_manual_folder),))
library.scan()              # Explicit local work, not performed by construction.
library.poll()              # Domain/event-loop thread while busy.
snapshot = library.snapshot()
matches = library.search('antenna', collection_id='manuals')
```

`Collection(id, title, root, kind='documents')` is immutable configuration.
Collection IDs are caller-assigned stable identities; do not reuse an ID for an
unrelated root. `Document.id` hashes collection identity plus relative path, so
editing file contents does not disturb selection. Keep one shared Library owner
per configured collection set; windows retain only their local presentation state.

`snapshot()` and `search(query='', collection_id=None, limit=100)` perform no IO.
Search is a bounded case-insensitive AND over title, relative path, and indexed
text. Snapshots/documents/statuses/results are frozen dataclasses containing
immutable values. Search does not mutate selection or start a scan.

- `scan()` queues one local index operation.
- `open(document_id)` queues a bounded local preview/metadata read, only for an ID
  in the current index. It returns text or an external-viewer reference; it does
  not launch an application or execute a file.
- `cancel()` requests cooperative cancellation. `close()` also rejects new work
  and stops the worker. Reuse the owner when hiding/reopening a view.
- Commands immediately return `CommandResult(code, message)`: `accepted`, `busy`,
  `closed`, or `invalid`. They never claim completion at admission.
- One lazy single-thread worker admits one operation, including a completed result
  awaiting `poll()`. Workers return replacement values; `poll()` applies one result
  on the caller thread and increments `snapshot.revision`. Poll only while busy;
  cache view rendering by revision plus local interaction/size changes.
- Completion/error details appear in `snapshot.result`; `pending` names the
  command or is `None`. On open failure the previous successful preview remains
  with its own ID; do not present it as the failed requested file.

## Honest collection states and bounds

The initial status is `unindexed`. Each collection reports `unindexed`, `ready`,
`missing`, `unavailable`, `limited`, or `error`, plus a count and explanation.
Aggregate `ready`/`empty` is not proof that every configured collection is healthy.
An empty existing directory differs from a missing directory. No example or
invented content fills a missing collection.

At most 16 roots, 500 files and 2000 examined directory entries per scan, six
nested directory levels, and a five-second cooperative elapsed scan budget.
Symlinks are skipped; filesystem/home roots are rejected. Paths are checked again
on open, and files moved outside their root are rejected. Path references are
local metadata, not a permission to share files or launch programs.

Recognized text files index at most 32 KiB each, under a shared 2 MiB text budget.
Search is therefore partial for large files and collections; metadata remains
searchable. Text previews read at most 128 KiB and explicitly report truncation.
Control characters are removed. PDF, ZIM, map, archive and binary captures retain
size/type/path metadata and return `external=True, text=None`; no extraction or
rendering support is fabricated. Local/network filesystem calls are not forcibly
interruptible, so the elapsed scan budget is cooperative rather than real-time.

`Library(..., kiwix_url=URL)` declares an optional existing HTTP(S) service.
`kiwix_state` is `unavailable` without it, `configured_unverified` with it. The
domain never contacts it, claims it is healthy, or parses ZIM archives itself.
The frontend may offer an explicit handoff using the configured service URL.

## Immediately usable local flow

From `packet-console/`:

```sh
python3 -m domains.library --root domains/library/fixtures/manuals --query antenna
python3 -m domains.library --root domains/library/fixtures/manuals --open DOCUMENT_ID
python3 -m domains.library --root /explicit/path/to/manuals --query receiver
python3 -m domains.library --root /missing/collection
```

Use the ID emitted by search. Commands return JSON; missing collections and errors
produce nonzero exits. Example manuals are explicitly authored offline fixtures.
Configured roots are provided by the host's configuration; this domain stores no
copy of a user's directory tree or documents.

Tests: `python3 -B -m unittest domains.library.tests.test_domain -v`.
