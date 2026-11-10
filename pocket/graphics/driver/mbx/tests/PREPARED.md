# Prepared commands: local source checkpoint

The API retains validated wire resources and encoded commands in caller-owned
storage. Static `begin` takes no geometry or texture payload. Dynamic execution
accepts only the compact viewport/uniform update format. The encoder records
patch offsets at emission; callers do not infer offsets from packet lengths.

The opt-in kernel service (`gpu_prepared_commands=1`) retains four templates per
exclusive session, identified by monotonically increasing generations. Mesa's
`N810_MBX_TEMPLATE=1` path compares each canonical frame against four immutable
snapshots, including resource bytes. Matching frames submit only dynamic state.
Changed geometry, textures, frame state or scissor rectangles require replacement.
Static scissor masks are retained; updates cannot change the mask's clip words.
Compact state is assembled once after resource insertion and compaction.

The default remains off. No new OpenGL capability, texture GPU residency or
physical performance improvement is claimed by these source tests. Existing
per-job resource placement, upload and guard verification remain in place.
Separate-alpha replay, asynchronous execution, external resident surfaces and
preserve-target frames remain outside this opt-in path.

A trusted service owns and serializes objects. Generations never wrap. Failed
replacement invalidates the replaced object; other slots retain their identity.
Busy work and exported surfaces prevent mutation. Close retains all storage on
a busy fault. The existing attended recovery may retire it only after reset,
MMU/table checks, DMA quiescence and DMA release; failed evidence retains it.
No automatic recovery, reboot or forced unload is introduced.

Kernel opt-in storage is bounded: four 1 MiB snapshots and four 65,536-entry
command arrays (512 KiB each), plus the existing wire buffer. Mesa allocates
snapshot capacity as needed, up to four 1 MiB frames. This memory cost must be
included in the physical acceptance test; source correctness is not a speedup.

Run `python3 tests/check_prepared.py` from this driver directory. Tests cover:

- 1,000 zero-payload repeats for both geometry and textured geometry.
- Full command-array equality across 65 viewport/color updates per fixture.
- Canonical mixed resources and immutable scissor; changed resources or clip
  require replacement before any command mutation.
- Four alternating templates, 256 compact updates and exact command parity;
  stale eviction and cross-session requests are rejected.
- Busy, exported, closed, faulted, nonfinite/truncated and exhausted-generation
  requests, plus failed replacement.
- The actual service open/close/retirement functions with allocator injection:
  all nine required allocation failures clean up without advancing the session;
  default optional-cache behavior remains unchanged; failed reset evidence and
  exports retain storage, and verified retirement frees the full pool.

These are local command and lifetime tests. Device pixel, CPU/FPS, memory and
physical input acceptance are recorded separately for each staged candidate.
