# Bounded framebuffer DMA sink

The opt-in `POCKET_DMA_SINK=1` native presenter exports each completed RGB565 target and invokes `MBX_SURFACE_DMA_SINK`. It transfers pixels with the OMAP DMAengine into the existing framebuffer allocation. The CPU still submits geometry and DMA descriptors; RFBI still sends the final framebuffer to the panel. This is not direct scanout from MBX memory, general dma-buf support, or full GPU residency.

The existing `POCKET_OWNED_SINK=1` path is the explicit CPU-copy comparison. DMA rejection is an error, never a silent CPU fallback. Separate counters expose DMA bytes/descriptors/time/failures and CPU sink bytes/calls. Diagnostic captures remain explicit CPU reads.

## Ownership and cache rules

This prototype is pinned to the recorded 5.15.224 kernel and its OMAP framebuffer structures. An imported writable framebuffer descriptor names the destination; userspace cannot supply physical addresses. A completed-image generation lease excludes subsequent GPU writes. DMA channel acquisition precedes nested framebuffer locks. Device lock, live framebuffer identity, framebuffer lock and original region read lock remain held until DMA has completed or terminated and drained. No lock survives the ioctl.

The framebuffer allocation must be allocator-owned, write-combined, CPU mapped, normal RGB565, aligned, unrotated and unmirrored. Source and destination rectangles and strides are validated independently. Both OMAP devices must resolve to the pinned default noncoherent ARM DMA operations, with no address-range translation and a valid DMA mask. The legacy framebuffer has raw NULL ops (the architecture default); the DT DMA provider explicitly records that same default through arch_setup_dma_ops. Their raw pointers therefore need not match. Driver identity, setup provenance and device-tree presence are checked instead. Each destination page mapping is checked against the allocator handle and mask. DMA maps use the consuming DMAengine device, never an MBX address.

Framebuffer attachment uses `DMA_ATTR_SKIP_CPU_SYNC` on both map and unmap: ordinary streaming cache maintenance on the coherent allocation's cached alias is incorrect. Only the write-combined alias is used for CPU access, with an ordering barrier before transfer. Source streaming pages use normal DMA ownership transitions. Adjacent mapped pages are coalesced within a row only when their DMA addresses are contiguous; source row reversal is unchanged. DMA completion status is checked before success. Mapping and submission failures drain queued work before releasing memory or locks. No forced module unload or reboot is part of this path.

The caller owns presentation after the synchronous copy returns, including the framebuffer lease and RFBI submission/completion. This is a narrow architecture-specific attachment, not a portable exporter.

## Validation

Local sanitizer tests cover stale leases, reserved fields, bounds, strides and overflow. ARM emulator scene tests cover native rectangles/text, Room composition and transparent overlays. The physical gate compares every framebuffer pixel against the materialized GPU reference before measuring the plain desktop. Background is disabled. Idle CPU and controlled repaint throughput are reported separately; idle FPS is not a throughput score. Physical receipts and benchmark output are kept under the workspace `outputs/shared-gpu-scene-dma-20261108` directory. Hardware success and performance must be read from those receipts rather than inferred from compilation.

## Physical result, 2026-11-08

The guarded Nokia test matched all 384,000 reference pixels. Final presentation used 768,000 DMA bytes, zero CPU sink-copy bytes and no frontend glReadPixels calls. All GPU/service/resident/cleanup and DMA error counters remained zero. Normal unload restored the prior framebuffer, VT, display mode, panel state and preferences with the same boot. The calibrated touch reader and foreground TTY were enabled for a 180-second live trial; physical input confirmation remains pending.

| Same-quality plain desktop, background off | CPU-copy sink | Coalesced DMA sink |
| --- | ---: | ---: |
| Controlled full redraw FPS | 2.915 | 2.654 |
| Process CPU ms/frame | 265.52 | 261.75 |
| Whole-system busy CPU | 94.97% | 94.46% |
| Final CPU copy bytes/frame | 768,000 | 0 |
| DMA descriptors/frame | 0 | 978 |

Both measured windows had zero major page faults and the same 330 MHz CPU setting. Whole-system counters include other services; a surviving Symbian diagnostic monitor was observed using about 6.5% CPU after the run and was left untouched. Coalescing reduced the original 1,320 descriptors/frame to 978 and reduced DMA sink wall time to 25.23 ms/frame, but the complete desktop still regressed. This is a successful opt-in DMA API/pixel proof, **not a passed performance gate**. No default or installed Pocket change was made. Native/Mesa presentation still consumed about 230 ms of process CPU per frame; measured GPU raster wall time was about 15.7 ms/frame. These are different timing domains and are not additive.

Raw comparison, image captures and cleanup receipts: workspace `outputs/shared-gpu-scene-dma-20261108/run5`; compact result `SUMMARY.json` in its parent directory. Earlier failed harness/admission attempts are retained separately; none required a reboot.


## Forward rows and block completion candidate (2026-11-09)

`POCKET_DMA_FORWARD=1` renders final 2D tiles in framebuffer row order when the
DMA sink is selected. Room keeps its established orientation. Switching
orientation invalidates retained output damage, so unchanged tiles cannot use
the wrong row order. GPU textures, glyph detail and output dimensions are unchanged.

The DMA sink groups forward rows only while both source and destination mappings
are contiguous in the consuming DMA device's address domain. It submits one
interleaved descriptor per such run; fragmented boundaries use the existing
bounded row path. The source mappings, framebuffer locks and completion/drain
requirements remain in force.

The pinned OMAP provider requests `CICR_FRAME_IE` for interleaved transfers but
its non-cyclic callback completes the entire descriptor on that first row IRQ.
Physical comparison exposed missing rows despite a success receipt. The module
corrects only its own newly prepared, unsubmitted descriptor to `CICR_BLOCK_IE`,
retaining all error interrupts. It verifies the provider identity and expected
source/destination, row count, width, strides, mode and old interrupt mask first.
The ARM module build statically checks every private descriptor field offset and
structure size against the pinned kernel source. This is a narrow compatibility
fix, not a portable DMA ABI or a live kernel-code patch. A source patch is saved
at `../display/omap-dma-interleaved-completion.patch` for the next kernel build.

The ARM-emulated forward-output check preserves all 384,000 pixels. The local
mapping test checks 2,048 fragmented/aligned rectangles against byte addresses.
Physical pixel and throughput evidence is recorded separately in the run report.


## Texture residency and measured comparison (2026-11-09)

The opt-in `gpu_texture_residency=1` service and
`N810_MBX_TEXTURE_RESIDENCY=1` Mesa path retain one session-owned linear texture
arena. A session/generation token references its verified contents; it never
contains a userspace GPU address. Only canonical v8 linear RGBA and v12 twiddled
RGB565 resources are eligible. Changed content uploads normally. Every draw
still passes canonical validation, and post-job texture and memory guard checks
remain enabled. GPU vertex geometry still enters through the VGP FIFO; this is
texture residency, not resident vertex buffers or asynchronous submission.

The first physical comparison preserved all 384,000 final pixels, completed
and unloaded normally, and restored the prior desktop state without a reboot.
It reduced texture upload bytes from 19,543,680 to 15,050,880 and command transport
from 23,295,976 to 18,803,912 over 44 redraws. DMA replaced 24,396,800 CPU copy
bytes with 2,607 bounded DMA descriptors. However, FPS fell from 4.919 to 4.610
and process CPU rose from 155.40 to 161.39 ms/redraw. This candidate did **not**
pass the performance gate and was not promoted. Raw receipts are in workspace
`outputs/gpu-resident-textures-20261109/results`; immutable tested binaries are
in that output directory's `physical-v1-artifacts` subdirectory.

The next candidate retains the canonical texture buffer itself and changes only
validated header/draw ranges on a reference. It removes CPU reconstruction and
redundant reference-hit receipt queries. The opt-in
`gpu_readonly_frame_cache=1` skips device-transition cleaning only after verified
completion of a private single-image target with no CPU writers. Completion
unmapping still invalidates GPU-written pages before any CPU reads or checks.
Shared/multi-image targets retain the normal transitions. DMA source reads use
the same proven read-only ownership. Per-transition nanosecond counters expose
the remaining cost. These revisions require their own physical acceptance;
the preceding successful pixels do not validate a newer binary.

`POCKET_SCENE_PROFILE=1` adds coarse process-CPU counters around each output
tile's native geometry submission, `glFinish`, and final sink/lease work. It
prints one aggregate record at renderer destruction, with no per-draw logging.
These process times are separate from GPU/RFBI wall-time counters and cannot be
added to them as disjoint pipeline stages.


## Follow-up physical results (2026-11-09)

The revised ownership/residency path passed the 384,000-pixel DMA proof. Three
matched 44-redraw runs measured 4.869 FPS / 150.03 CPU ms per redraw for CPU-copy
control, 5.273 / 153.31 for texture residency with CPU copy, and 5.170 / 147.88
for texture residency with DMA. Final images were bit-identical; DMA failures
and GPU readback calls were zero. Source uploads fell by 4,492,800 bytes and
DMA replaced all 24,396,800 final CPU-copy bytes. This is a modest throughput
change, not evidence of a 30 FPS desktop. Receipts:
`outputs/gpu-resident-clean-20261109/results`.

`POCKET_SCENE_COMPILED=1` retains command-owned color/UV conversion and primitive
bounds. Every replay still evaluates current destination, translation, clipping,
and occlusion; texture/command lifetime remains explicit. It does not make
vertex buffers resident in GPU memory. Its matched Nokia run improved
5.023 to 5.247 FPS and 153.22 to 143.21 CPU ms/redraw, with identical final pixels
and only 76 KiB greater peak RSS. Receipts:
`outputs/gpu-native-compiled-20261109/results`.

`POCKET_SCENE_MATRIX_CACHE=1` avoids rebuilding unchanged projection and texture
matrices for each command. Each flush resets ownership, and Room invalidates the
cache before taking matrix control. A matched run with compiled geometry enabled
improved 4.964 to 5.316 FPS and 146.63 to 138.80 CPU ms/redraw, with identical
final pixels. ARM-emulated mixed Room/overlay/damage regressions also passed their
existing exact or one-RGB565-step bounds. Receipts:
`outputs/gpu-native-matrix-20261109/results`.

Every physical run restored VT/panel/preferences, retained the same boot, left
Pocket stopped, and unloaded the module normally. No default was promoted.
The counters still show substantial CPU geometry and completion costs; these
results do not satisfy the requested desktop throughput target.


### 2026-11-09 full-size target: guard correction and physical acceptance

The first 800x480 experiment tripped a guard (-75), and restored the prior
framebuffer/VT without reboot. The user-authorized GPU-only recovery saved the
failed buffers and unloaded normally. Static tracing identified undersized
Morton tile state: padded 52x32 tiles require 14464 bytes; the old mapping had
4096. The correction maps 16384 bytes and relocates adjacent context buffers.

The corrected physical run passed all 384000 reference pixels exactly, memory
guards, page-table checks, and normal unload. A matched 44-redraw desktop
workload improved from 4.981 to 6.782 FPS, and from 146.32 to 106.70 CPU ms/redraw.
Peak RSS was 36360 versus 36380 KiB. Measured texture uploads fell from 15050880
to zero bytes; transport from 18803912 to 3808500 bytes; GPU jobs from 126 to 44.
Both paths had zero CPU framebuffer-copy/readback bytes. Full-canvas DMA traffic
increased from 24396800 to 33792000 bytes, so partial presentation remains work.
The final framebuffer hashes matched exactly. Background was off, Balanced,
800x480 RGB565, same interaction sequence. These are workload redraw rates,
not a claim of a 30 FPS interactive desktop or fully resident window geometry.

Evidence: `outputs/gpu-single-desktop-v4-20261109/results`; failed-buffer evidence:
`outputs/gpu-single-desktop-v2-20261109/results/guard-recovery`. All physical runs
preserved the boot, VT, panel, preferences, and prior stopped Pocket state.

Retained indexed arrays and VBO experiments remain opt-in: neither improved the
matched workload (6.625 to 6.494 FPS and 6.685 to 6.478 FPS respectively), despite
exact final pixels. Do not enable them as performance defaults. Detailed GL-call
CPU clocks require `POCKET_SCENE_DRAW_PROFILE=1` separately from coarse profiling.

The opt-in text-run experiment (`POCKET_SCENE_TEXT_RUNS=1`) preserves installed
font coverage in bounded immutable native textures. Power-of-two widths avoid
floating-point page-edge errors. The physical comparison passed all 384000
independent reference pixels and the final desktop hash, but regressed from
6.718 to 5.059 FPS and 105.12 to 152.99 CPU ms/redraw (RSS 36264 to 36972 KiB).
Do not enable it by default. Although FIFO time fell from 215.4 to 154.7 ms over
44 redraws, GL draw calls grew from 483 to 2528 over the process lifetime;
linear texture-cache rebuilds grew from 3 to 1023. Steady texture uploads rose
from zero to 8895744 bytes. This identifies texture working-set churn and draw
submission growth, rather than a raster bottleneck. Evidence:
`outputs/gpu-text-runs-20261109/results` and its `ARTIFACTS.json`.

The next structural work is retained GPU window images and batched composition,
with explicit damage/lifetime ownership. Current retained commands are CPU-side
geometry; calling them resident GPU window images would be inaccurate. The
full-size target and texture residency improvement is accepted; the extra
indexed/VBO/text experiments are diagnostic opt-ins only, not deployment defaults.

### 2026-11-09 damage-bounded composition and DMA

`POCKET_SCENE_DMA_DAMAGE=1` intersects the DMA destination/source rectangle with
validated desktop damage. Reverse-row sources use the corresponding bottom-up
source interval. A destination pointer/stride/target change still invalidates
damage and requires full presentation. The same region bounds GPU scissors and
primitive rejection; nested retained command replay cannot bypass that target
scissor. Sampled FBOs do not use this partial-source path. The private GPU target
is only composition-complete inside damage; it must not be reused as a complete
sampled window image. The existing final framebuffer retains everything outside
that region. RFBI remains full-panel fallback; this is not partial-panel support.

Physical matched results: 6.5206 to 7.7299 FPS, 110.7053 to 97.1472 CPU ms/redraw,
identical peak RSS (37204 KiB). All 48 interaction framebuffer snapshots matched
exactly (384000 pixels each), including changes, focus, movement, resize, closing
and reopening. Both runs used Balanced, background off, 800x480 RGB565, 44
redraws, zero driver readbacks and zero CPU final sinks. Diagnostic framebuffer
reads/hashes were timed separately and removed from reported process CPU/wall
budgets; these are instrumented matched-workload figures, not free-running FPS.

DMA bytes fell 33792000 to 13057024, descriptors 2156 to 767, DMA observed wall
516.1 to 236.2 ms. FIFO observed time fell 218.1 to 186.9 ms; raster remained
421.8 versus 413.6 ms over 44 redraws. Culling changes the texture working set:
texture uploads rose from zero to 2246400 bytes and resident hits fell 44 to 29.
This remaining whole-resource-set residency limitation is recorded, not hidden.

All guards, device state restoration, and normal unload passed without reboot.
Evidence: `outputs/gpu-damage-compose-20261109/results/summary.json`, per-frame
hashes in baseline/candidate JSON, and `ARTIFACTS.json`. The preceding DMA-only
isolation is in `outputs/gpu-dma-damage-20261109/results` (6.844 to 7.061 FPS).
Rendered per-window images are still not resident: command replay remains the
source of window content. This change completes damage-bounded composition and
final transfer, not general render-to-texture residency.
