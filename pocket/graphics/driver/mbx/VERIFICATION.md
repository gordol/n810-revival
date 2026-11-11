# Selectable render verification

`gpu_verification_mode` is fixed at module insertion; 0 is the existing full diagnostic default, 1 is normal checkpoint verification. Values above 1 reject render writes. This setting never changes rendering commands or pixel quality.

Both modes retain command/resource admission, bounds and ownership checks, generation tokens, FIFO flow control, GPU completion/error/timeouts, DMA synchronization, startup render proof and fault retention.

Full mode scans guard memory and compares submitted texture bytes after every job. Normal mode scans guards on the first job of each session, after texture replacements and every 32 completed jobs. It compares uploaded textures when replaced. Session close scans all guards and the current verified texture arena before freeing command storage. A failed checkpoint latches the fault and retains storage for attended diagnosis. Normal mode can detect corruption later than full mode; it does not provide per-job corruption detection.

Read-only counters `gpu_verification_checks` and `gpu_verification_skipped` expose the selected coverage. `gpu_last_guard_checked` reports whether the most recent job/checkpoint actually scanned guards. The internal `gpu_bounds_verified` handoff accepts completion under the selected verification policy, including scheduled skips; it remains false on failed checks. Detailed existing timing counters remain available for the matched comparison.

Local service tests exercise a failing normal close checkpoint, retained storage, and successful cleanup after the injected fault is removed. Physical CPU/FPS and final-pixel comparisons remain pending device ownership. No persistent device default has been changed.

## Normal timing must exclude automatic diagnostic snapshots

`gpu_capture_success` is independent of guard verification. Its diagnostic
default copies successful job buffers and logs a capture message after every
frame. Normal timing must explicitly select `gpu_capture_success=0` alongside
`gpu_verification_mode=1`. This removes observation work, not rendering, DMA
synchronization, completion checks or the selected guard checkpoints. Use a
separate diagnostic run for success captures; fault capture remains available.

The legacy GLX profile originally omitted this newer parameter. Measuring it
with the newer module therefore included per-frame diagnostic copies, even
after selecting normal verification. Do not interpret that cost as GPU raster
throughput or silently compare it with a capture-free historical profile.

## Legacy replay compatibility and physical regression

The legacy replay entry point had also stopped capturing templates, leaving
older GLX clients on full uploads every frame. It now captures self-contained
clear frames in wire versions1 through6 when the exclusive command owner has
enough snapshot storage. Compact updates retain generation, command-owner and
immutable-state checks. Failed replacements invalidate the old identity;
oversized frames keep full encoding. Newer retained-image dependencies continue
to use the explicit prepared-object lifetime path.

Sanitizer tests compare128 plain/textured compact updates with full command
encoding and reject stale generations and wrong owners before writes. Prepared,
retained-image, atlas and ARM Mesa regressions pass separately.

On the physical N810, unchanged standard glxgears and512-triangle terrain at
400x400 RGB565 measured the following in a clean session:

| Profile | Gears rendered FPS | Terrain rendered FPS |
| --- | ---: | ---: |
| Replay disabled, automatic snapshots enabled | 22.361 | 28.811 |
| Replay repaired, automatic snapshots enabled | 24.232 | 33.294 |
| Replay repaired, normal verification, snapshots disabled | 36.248 | 60.964 |

Final app CPU time was16.289 ms/frame for gears and6.801 ms/frame for terrain.
All160000 pixels of the fixed-camera terrain reference matched exactly. Fault
counters stayed zero, close/unload succeeded, boot/VT/preferences were preserved,
and no reboot occurred. Display transfers remained about23.49/s; these numbers
are completed GPU rendering rates, not distinct LCD updates.

The user reported apt activity during an earlier test. Earlier runs also had
background mesh/radio owners active and paging; those runs are excluded from
this clean comparison. The final preflight rejects package work and mesh/radio
owners. The owners and offline docs server were stopped cleanly. The collector
ran at nice+10 and the application at0; no real-time or IRQ priority changed.

Private evidence and exact artifact identities are under project output
`legacy-replay-repair-20261110`. The observed CPU clock was330MHz with the
performance governor; no clock setting changed. This test does not establish a
new native retained-image desktop FPS or replace its installed release.


## 480 MHz kernel comparison

The new kernel can leave the idle GFX divider at 2. The probe previously required
an initial divider 1 and rejected this otherwise idle state before GPU execution.
It now admits either verified idle divider, avoids an unnecessary clock commit
when already at 2, and restores the exact initial selector on teardown. The
existing gate/reset/power, exclusive ownership, MMU, bounds and fault-retention
checks remain. Extracted admission/cleanup tests inject failure at every cleanup
readback, cover partial enable ownership and failed commits, and run with host
and Linux sanitizers plus ARM1136 emulation. Receipt checks require the matching
transition count and exact observed initial selector.

The benchmark helper also restores the original RFBI update mode and submits the
restored console after preflight failure. Leaving manual mode selected had left
stale repeating pixels on the panel even though framebuffer memory contained the
normal console. Restoring automatic updates and a full console update recovered
it without reboot. The callable identity helper accepts explicit argument lists
as well as its command line.

Matched physical runs used the same frozen Mesa library, standard glxgears,
512-triangle rotating terrain, 400×400 RGB565 target and rendering settings.
Pocket, MeshCore, Reticulum, APRS and Bluetooth services were stopped; SSH and
battery services remained. Applications ran at nice 0 and the collector at nice 10.
Normal checkpoint verification was active; diagnostic success copies were off.
CPU readings remained 480000 throughout. No CPU/GPU frequency switching or reboot
occurred during this comparison.

| Workload | Earlier 330 MHz GPU FPS |480 MHz GPU FPS | Gain | Earlier CPU ms/frame |480 MHz CPU ms/frame |
| --- | ---: | ---: | ---: | ---: | ---: |
| Standard glxgears |36.248|42.742|17.9%|16.289|13.533|
| 512-triangle terrain |60.964|71.668|17.6%|6.801|5.493|

Gears used a 32.05 s sample. Terrain's final clean sample ran without concurrent
SSH commands or evidence downloads; an earlier sample overlapped a gears-file
transfer and is retained as contaminated evidence rather than a headline result.
All 160,000 fixed-camera terrain pixels matched the prior reference exactly.
Both framebuffer snapshots changed in each animated run. GPU transform, lighting
and rasterization completed; guard/error/fault/cleanup counters were zero and
normal module removal succeeded. Session preferences and boot identity were
preserved. These are completed-render FPS, not distinct LCD frames; the RFBI
presentation rate is reported separately in the saved results. The comparison is
the 480 MHz kernel against the earlier 330 MHz baseline, with the entry-divider
compatibility fix, rather than a frequency-only toggle in one kernel session.

Raw results and original framebuffer captures are in the project workspace at
`outputs/gpu-480mhz-comparison-20261110`. The verified module is a test artifact;
the shared installed release was not silently replaced, and command-cache reuse
remains opt-in. Pocket and radio services remain stopped after the test.


Build locations are explicit configuration: set `MBX_KERNEL_SOURCE` to the pinned
Linux checkout inside the builder VM and optionally `MBX_KERNEL_BUILD_TMP` to
writable scratch storage. Set `MBX_MESA_BUILD_ROOT` for the Mesa build directory.
Source revision, archive, toolchain and kernel-import checks remain mandatory;
these settings replace machine-specific development paths, not dependency pins.
