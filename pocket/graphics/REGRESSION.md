# Native graphics regression checks

Keep the terminal implementation and default rendering path intact while testing
an opt-in backend change. A passing new unit test does not replace the existing
workloads.

## Local checks

Run `python3 graphics/build.py`, then `python3 graphics/check.py` from `pocket/`.
The latter checks native input, border coverage, resizing, app activation and
Room output through the desktop. Report the actual renderer; a software run is
not hardware performance evidence.

For the shared target, cross-build with the matching Mesa headers/library and
run `graphics/test_target.py` as documented in `PIXEL-INTERFACE.md`. The ARM
reference compares legacy and direct-readback pixels, output guards, padding, invalid
spans, nesting, pixel-pack restoration and cells/Room context reuse. Its timings
are emulator diagnostics, not Nokia measurements.

## Physical regression window

Acquire the device handoff before starting. Use the existing pinned, bounded
GPU owner and preserve initial processes, preferences, VT and display mode.
No reboot, forced fault recovery or installed runtime replacement is part of
this test. Retain a fault for inspection rather than starting another workload.

1. Run the unchanged standard `glxgears` binary at 400x400 RGB565. Record its
   executable/library/module hashes, GPU renderer and completed-job counters.
2. Run the existing 512-triangle terrain workload at the same resolution and
   quality. Compare its fixed-camera frame-30 capture with the saved reference.
3. Run `test-pixel-target --hardware` inside the accepted offscreen GPU owner.
   The executable rejects software rendering. Both modes use the same library
   and scene; direct readback is explicitly opt-in. Eighty measured frames
   follow ten warmup frames for each case. Guard/state-check overhead is part
   of these diagnostic timings; they are not whole-desktop FPS. Use
   `--hardware-capture` for one-frame cases with the intermediate-buffer sentinel
   check, and inspect saved RGB565 files when any comparison fails.
4. Collect pre-unload fault/guard receipts, normal-unload confirmation and
   restored state before releasing the device.

Record process CPU milliseconds per completed frame, elapsed time, RSS, swap,
minor/major faults, clock settings and sample count. Record display transfers
separately from completed GPU jobs. Use trace-disabled runs for throughput.
Differences between old and new dates do not isolate a code regression: compare
identical workload/configuration and account for concurrent services and paging.

The standalone historical workloads do not call Pocket's target helper. They
verify the driver still renders those workloads; they cannot establish a speedup
from a Pocket-only change. The Room/cell comparison exercises that change.

Save source commits, artifact hashes, captures and raw measurements. Keep
private process/device records outside the publication tree. Promote an opt-in
path only after its relevant pixel and performance checks pass.

## Native pixel desktop damage and PNW

`test_pixel_desktop_damage.py` exercises Flux → PNW, background off/on,
retained static artwork, panel no-op updates, and damage consumption. PNW
reuses the existing procedural scene decisions; those still run in Python.
Its artwork is submitted to native C geometry/font drawing without Host.flush,
ANSI, a desktop cell plane, or Python pixel rasterization. This preserves the
original scene rather than substituting a lower-detail landscape.

The local ARM `test-scene-gl --desktop-reference` check compares all 384,000
pixels against a full redraw after moving a translucent window over another
window. With 400×256 output tiles it redraws one tile and retains three, checks
memory guards, and forces a full redraw when the owned destination changes.
It also compares sparse landscape half-block/glyph layers against the existing
renderer. These are correctness checks, not physical MBX performance results.

Damage currently avoids unchanged output-tile rendering and final sink copies.
Unchanged windows, panels and backgrounds retain the existing native command
batches. Each frame assembles references in stacking order instead of rebuilding
those vertices. Changed content/palette rebuilds only its batch;
retired batches release their source references. Animated backgrounds and dirty app
surfaces conservatively request a full frame. The Nokia adapter submits damage bounds, with one full-only capability fallback
for the old panel driver; SDL keeps its existing full-frame path. The physical
48-operation comparison completed 44 redraws per variant: 4.3007 to 4.6184 FPS,
189.193 to 178.885 CPU ms/frame, identical final 384,000 pixels, zero process
swap, and normal owner restoration. Both runs stayed at 330 MHz. Baseline had
one major fault versus zero for the candidate, so this single comparison is
not a variance estimate. RSS increased by 160 KiB. The initial three-second
idle window produced no rendering submissions; it is not a settled idle-CPU
measurement. The old kernel rejected the partial request, so RFBI remained
full-screen in both runs. No default promotion or kernel switch was performed.

## Same-frame resource references (2026-11-09)

`N810_MBX_RESOURCE_REFERENCES=1` reuses a packed texture's table index while
its resource reference, timestamp, crop, sampler interpretation and canonical
frame epoch remain unchanged. Clear, history restore, checkpoint and resident
materialization invalidate the epoch; updates/eviction invalidate the entry.
Append and compaction preserve table indices. This avoids repeated full-image
comparisons within a submission; it is not persistent GPU texture allocation.
Kernel payload upload, bounds checks and texture verification remain unchanged.

The same opt-in skips command-history copies for final exported surfaces.
Those surfaces have no CPU-sampling or incremental-replay contract and must be
explicitly cleared before reuse. Ordinary app/Room history remains retained.
The sanitizer test compares 3,900 reference operations against canonical resource
assembly, including changed contents and frame replacement.

An earlier Mesa display-list experiment preserved all pixels but did not improve
physical desktop throughput or CPU use. It was removed from the source; its
patch and comparison receipts remain in the private experiment artifacts.


The resource-reference physical A/B completed the same 44 redraws: 3.9671 to
4.6906 FPS, 201.608 to 172.652 CPU ms/frame, and 37,476 to 36,424 KiB peak RSS.
The final 384,000 pixels matched exactly. It skipped 21,340,800 comparison bytes
and 21,920,620 final-surface history-copy bytes. Baseline had nine major faults
and candidate zero: do not attribute the whole throughput gain to the code.
No kernel upload or guard verification was removed.

## Retained window placement and native damage bounds (2026-11-09)

Unchanged window geometry now replays with a model-view translation rather than
rebuilding its native batch for position alone. Dynamic app views keep their
conservative placement key. The existing packed damage-index buffer is reduced
to bounds in native C instead of creating Python integers for every index.
`POCKET_SCENE_MOVE_REUSE=0` selects the old placement/bounds behavior for comparison.
The model and text layout remain CPU work. This retains native geometry; it does
not establish persistent GPU vertex or texture allocation.

The matched physical comparison used the same Mesa resource-reference candidate,
800x480 RGB565, Balanced, background off, 330 MHz, 48 operations and 44 redraws:

| Metric | Control | Retained placement/native bounds |
| --- | ---: | ---: |
| Desktop FPS | 4.5832 | 5.2947 |
| Process CPU ms/redraw | 173.919 | 147.291 |
| Peak RSS KiB | 36,632 | 36,408 |
| Major faults / process swap | 0 / 0 | 0 / 0 |
| Model preparation CPU ms/redraw | 30.930 | 5.952 |
| Native batch builds during measurement | 45 | 39 |

The final 384,000 pixels matched exactly. The local ARM translation check covers
five offsets and 1,920,000 pixels; one blended pixel differs by one native RGB565
channel step at an extreme clipped offset. Coverage remains unchanged. Existing
full/partial redraw and PNW comparisons remain exact, with clean memory guards.
This is a single-order comparison, not a variance estimate or physical input test.
The three-second initial window has zero rendered frames but includes startup
work; it must not be presented as settled idle CPU.

Both physical variants still submitted 126 GPU jobs, uploaded 23,295,976 command
bytes, verified 19,543,680 texture bytes and copied 24,396,800 final-sink bytes.
DMA sink transfers were zero. The running kernel rejected partial RFBI and used
full-screen transfer. The owned module unloaded normally; boot, VT, panel,
preferences and previously stopped Pocket state were preserved. Radios stayed off
apart from the existing SSH transport. The kernel candidate was not activated.

The existing prepared-command path already retains validated command templates,
but still places/uploads texture resources per job. It is not a GPU texture
residency implementation; enabling it alone cannot remove these copies. It also
excludes separate-alpha replay and external resident dependencies. Those ownership
boundaries must be handled explicitly before combining the paths.
