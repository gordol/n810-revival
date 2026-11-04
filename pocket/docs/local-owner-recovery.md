# Shared local owner recovery

An explicitly configured local Reticulum session, Reticulum carrier or MeshCore companion starts one shared idle management owner. Opening another matching client borrows it. Closing one client leaves that owner running. Unconfigured temporary contact owners retain their existing client-owned cleanup.

Startup uses a private nonblocking advisory lock, a process-held lifetime lock and a listener-ready pipe. Readiness and cancellation use descriptor events. A busy startup lock returns to the existing cancellable recovery backoff; it never blocks the UI or starts another interpreter just to wait for a lock. Retry delay grows from 250 ms to a maximum of 15 seconds. A subscription that lasted at least 30 seconds resets that crash backoff.

The client records the device, inode and change timestamp of an endpoint only after receiving and validating its owner snapshot. A refused socket can be removed only when its private receipt matches that exact device, inode, change timestamp and owner identity and the lifetime lock is free. Live mismatched owners, unknown endpoints, unsafe files and replacement inodes are retained and reported as errors.

A radio owner saves explicit Connect/Disconnect intent in its private binary
state. A matching selected target resumes after restart. Fresh owners and changed
targets stay idle. Disconnect cancels recovery; closing a display client preserves
the owner's requested connection. Failed connections retry after 5 seconds with
backoff up to 60 seconds. Reticulum cleans up its failed session before retrying.
Send, pairing, discovery and profile commands are not replayed. Recovering a
management process does not take ownership of an orphaned active radio child.

The device directory opens independently of receive-history loading, telemetry collection and optional owner startup. It publishes the built-in service list immediately, then updates each configured endpoint and its starting/ready/unavailable state. Telemetry and provider changes use the existing binary subscription. Directory-only snapshots (`snapshot` with `scope=directory`) omit receive history; the normal snapshot/subscription retains it. The attachment helper uses this lean query. An SSH attachment can forward a starting endpoint; its client follows readiness without another connection action.

Device catalogue startup treats a full Unix socket backlog as a transient busy
listener. It waits within the existing readiness deadline without spawning a
second owner. Nokia Bluetooth preparation has a separate cold-start allowance
for interpreter startup and the helper's own 25-second deadline. Cancelling the
connection terminates preparation without waiting for that allowance to expire.

`tests/test_local_owner_recovery.py` runs only original local fixtures and idle owners. It opens no radio ports or RNS carrier interfaces. `POCKET_STARTUP_TEST_TIMEOUT=120` allows slower source imports on the Nokia; this changes the test allowance, not the production readiness policy or a performance measurement.
