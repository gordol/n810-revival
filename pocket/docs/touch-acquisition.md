# Touch acquisition under rendering load

The N810 uses one process-owned touch source. A native reader thread drains its
nonblocking evdev descriptor without holding the Python GIL. It retains up to
4096 raw input records (64 KiB on the Nokia) and wakes the existing Python worker
through a nonblocking pipe. Python still owns device validation, calibration,
coordinate mapping, motion coalescing and the existing MessagePack handoff.
Presses, releases and source timestamps retain their order. This is buffering
against reader stalls, not interpolation, reduced input detail or a new gesture
implementation.

The queue is bounded. If it overflows, the reader reports loss explicitly and
uses the existing cancel/resynchronization path; it does not silently drop a
press or release. Cancellation and viewport changes discard old queued contacts
before rearming. Device disconnects propagate as errors. Shutdown wakes and joins
the native thread before closing its descriptors. The direct Python acquisition
path remains available when no native library is selected.

This addresses a reproduced failure in release b04f01cf7601 with Balanced Flux
and Connections open. A physical drag/resize test recorded five new SYN_DROPPED
notifications. The first two appeared in an interval containing 228 new major
page faults in the touch worker, but another two-drop interval had no new major
faults. Paging is therefore a contributing suspect, not an explanation of every
loss. The old reader already ran in its own process, but parsing, calibration,
Python execution and paging still occurred between reads of the small kernel
queue. The native thread separates that urgent read from those operations.

Diagnostics distinguish the reader (`native-buffered` or `python`), cumulative
native reads, and native-buffer overflows. Existing SYN_DROPPED/resync/cancel
counters remain visible. The process snapshot is still startup-or-last-active-
batch data, not a continuously refreshed physical contact state; a stale
`pressed` value alone does not prove a stuck contact.

Local tests cover ordering while Python holds the GIL, bounded overflow,
disconnect, idle shutdown, cancellation and resynchronization. The initial five
native-reader tests and three worker/trace tests passed on the physical Nokia.
All six native-reader tests, including the final cancellation boundary, then
passed against the installed ARM library in 2.341 seconds. The final clean
release ran 448 tests successfully with 9 skips. Release 1eff54047718 passed
post-install checks for saved layout/preferences, fresh shared telemetry, both
radio owners, all 200 retained packets and one desktop/touch worker. Evidence and
physical acceptance receipts are in `outputs/touch-loss-20261030` beside this
repository. The subsequent physical test is recorded in `fixed.msgpack`: 107 samples over
222.681 seconds, all Balanced and connected, with 2,036 emitted reports and
77 mapped events. It recorded zero new SYN_DROPPED, resyncs, cancellations or
native overflows; the final contact was released. The worker incurred 285 major
faults without losing input. The user nevertheless reported substantial lag,
especially switching to an empty desktop and back, so overall responsiveness
was not accepted. Active swap was zram; SD swap was unused. Major faults alone
do not identify storage reads or prove the cause of any stall. The first
automatic health discovery timed out; a direct desktop query succeeded and a
subsequent full check under the desktop owner passed. The timeout is retained
as a verification limitation rather than attributed to a proven runtime fault.

The change does not alter picture quality, the Balanced/Fast demo budget, the
VFP-enabled arithmetic build, kernel settings or radio services. It does not
claim GPU acceleration or remove the need to improve UI response latency after
a long stall.
