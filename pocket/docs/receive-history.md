# Radio packet history

Radio Feed opens with the live receiver's recent packets. Scroll past the oldest
packet or choose **Older** (`o`) to read an older page. **Latest** (`g`) returns to
the live buffer. New packets follow automatically while you are at the newest
end; browsing older packets preserves your selection. Reception continues while
you browse.

Raw packets are archived by the receiver in
`~/.local/state/n810-aprs/packets.sqlite3`. SQLite stores frame and fragment bytes
as binary columns. The archive survives receiver restarts. It uses SQLite WAL with normal
synchronization to avoid a flash synchronization for every received packet; an
abrupt power loss can lose the most recent uncheckpointed transactions. The existing recent
snapshot seeds a new archive once; the original snapshot is preserved. Packets
already discarded before archiving was installed cannot be recovered.

Older pages use the existing private device service, including SSH connections
and device services shared with trusted peers. Existing device read grants cover these archive pages. They do not open another
network port or enable sharing. A legacy receive-only socket connection can still show
live packets but does not provide archive access. Connect to the device service
to browse its archive.

## Resource limits

Set these environment variables before starting the relevant process. Invalid
values produce an error rather than silently selecting another limit.

| Setting | Default | Applies to |
| --- | ---: | --- |
| `POCKET_RX_HISTORY_RECORDS` | 200 | Receiver and client's live buffer |
| `POCKET_RX_HISTORY_BYTES` | 262144 (256 KiB) | Raw data in each live buffer |
| `POCKET_RX_ARCHIVE_RECORDS` | 100000 | Receiver's disk archive |
| `POCKET_RX_ARCHIVE_BYTES` | 33554432 (32 MiB) | Archive data budget |
| `POCKET_RX_PAGE_RECORDS` | 50 | Maximum records per server page |
| `POCKET_RX_BROWSE_RECORDS` | 1000 | Older records held by the Feed window |
| `POCKET_RX_ARCHIVE` | Path above | Receiver and device service archive path |

For example, to retain more recent packets in a desktop client:

```sh
POCKET_RX_HISTORY_RECORDS=500 make n810
```

Configure the receiver process separately to increase what it retains; a laptop
setting does not change the Nokia's settings. A custom archive path must be the
same in the receiver and its device service. Restart those processes after
changing their environment. Existing archive limits are enforced as packets are
written.

The first live limit reached evicts the oldest live packet. The first archive
limit reached deletes the oldest archived packet. The disk budget accounts for
raw bytes, timestamps, directions and a per-record allowance; SQLite indexes,
free pages and its write-ahead log add filesystem overhead. It is not a strict
filesystem quota. Browsing uses indexed cursors and loads only a page at a time;
it does not load or decode the archive at startup.

Pages also obey the existing service message budget. A page may contain fewer
records than configured. A single packet too large for that budget reports an
error; it is not silently truncated or skipped. Hard validation ceilings remain:
10,000 live or browse records, 16 MiB live raw data, 10 million archived records,
1 GiB archive data budget, and 200 records per page.

## Updating an existing Nokia

The radio receiver runs separately from the shell. Upgrade its configured
`n810-aprs-feed.py` and adjacent `n810-frame-history.py` together, then restart
the receiver. The maintained receiver is under `shell/owner-service`; the shared
history implementation is under `shell/vendor/packet-console`. A shell-only
update does not replace a receiver script previously installed outside the
release tree. Keep the old scripts and recent snapshot for rollback. No firmware
change is needed.
