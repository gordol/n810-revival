# Cooperative retained-window images

This private Mesa interface transfers completed GPU image identities between
trusted Pocket clients. Images remain in guarded driver-owned memory; neither
pixels nor GPU addresses cross IPC. Publication does not acquire the global
owned-surface lease that would block the compositor's next GPU submission.

Two layouts are implemented. The legacy layout remains the default. The native
layout is an opt-in module/Mesa candidate with local checks; it has not been
executed on the Nokia.

| Layout | Client slots | Private scratch slots | Pool including guards |
| --- | --- | --- | ---: |
| 1, legacy | 0..13: 128x128 | 14/15: 128x128 | 1,092 KiB |
| 2, native | 0/1: 240x320; 2..13: 128x128 | 14/15: capacity for 240x320 | 2,036 KiB |

The two native client slots support a producer's double buffer or two admitted
single-buffer windows. Small UI images keep their own class. Scratch slots can
render either admitted shape, and merge sources must have matching dimensions.
They cannot be exported or imported by clients.

A game renders once into its ordinary private 240x320 RGBA8 texture/FBO. No
six-tile replay belongs in the app API. Its 300 KiB image payload replaces six
128x128 payloads totaling 384 KiB. The larger pool costs 944 KiB extra when
layout 2 is enabled; it retains twelve small UI slots alongside the two native
client images and two native scratch images. Retained-image-only Mesa contexts
also skip allocating the unused CPU readback/conversion buffers and the CPU
channel-merge staging buffer. That is an allocation-path change, not a measured
physical RSS or FPS claim.

## Matching module and capabilities

The new module provides read-only `MBX_WINDOW_LAYOUT` capabilities. Layout 2
requires `gpu_window_images=1` and `gpu_window_native=1` in the existing guarded
shared-owner initialization. This document does not install or load the module.
Without the native parameter, allocation, addresses and version-13 resources
retain the legacy layout.

The broker can query capabilities directly on its render FD, or use
`n810_mbx_window_get_layout(&caps)` before creating a GL context. The latter
requires the inherited render FD and never opens a replacement GPU owner.
Capabilities contain layout version, client mask, native mask, native dimensions,
stride and arena size. For layout 2, `client_mask=0x3fff`, `native_mask=3`,
`width=240`, `height=320`, `stride=960`, and `arena_bytes=2084864`.

`MBX_WINDOW_BIND/QUERY` retain their ioctl sizes; request version identifies the
layout. New sampler resource version 14 identifies layout-2 addresses. Legacy
version 13 is unchanged. The kernel rejects mismatched layouts, stale generations,
wrong dimensions, aliases and conflicting modes before hardware submission.
Pair the candidate Mesa and module; do not mix a layout-1 client into layout 2.

The pool remains separate from the final display target. It has a leading guard
and one page after each of sixteen allocations. The candidate covers virtual
addresses through `0x4bd000`; the existing driver already programs eight page-table
banks covering 32 MiB. Bounds verification checks the full mapping and all
seventeen guard pages. Layout 2 uses bank 1, whose physical execution remains a
Nokia acceptance check. No framebuffer aliasing or weakened guards are used.

## Broker setup

The exclusive render owner opens `/dev/n810-mbx-render` once. Give clients
duplicates of that same open file description by inheritance or `SCM_RIGHTS`.
A separate device open would start another owner or fail busy. Also pass one
`O_RDWR` regular file or memfd for cooperative job locking. Clients must refer
to the same lock inode. Configure before the first Mesa call:

```text
N810_MBX_RENDER_FD=<inherited render descriptor>
N810_MBX_JOB_LOCK_FD=<inherited regular lock descriptor>
N810_MBX_WINDOW_IMAGES=1
N810_MBX_NATIVE_WINDOWS=1
N810_MBX_WINDOW_FIRST=<first owned slot>
N810_MBX_WINDOW_COUNT=<number of owned slots>
```

`N810_MBX_NATIVE_WINDOWS=1` requires matching layout-2 capabilities and fails
before rendering if they are missing. Omit it for the legacy interface. For one
native producer and Pocket, assign 0..1 to the producer and 2..13 to Pocket.
Native targets select native slots; small targets select small slots. Admit
internal app render targets as well as published window images when assigning
ranges. There is no eviction of live published images or CPU raster fallback.

Mesa rejects overlapping context claims in a process. Use one configured context
per client process, or explicitly assign separate ranges during serialized context
initialization. Destroying a context with a published image or active final sink
fails closed. The broker must drain publications before reassigning a range.
Range policy is cooperative, not kernel isolation from a malicious render-FD
holder; keep guest syscalls away from the broker's descriptors.

Shared mode requires synchronous jobs and rejects template, async, shared-image
and old global resident-checkpoint/alpha modes. The private lock covers the whole
flush: bind, RGB, alpha, merge and completion query. Texture-residency identity is
rechecked after another client may have changed the shared upload cache.

The lock uses POSIX process-owned record locks plus a local thread mutex.
`flock`/OFD locks on duplicated inherited FDs would not exclude another client.
Nested transactions are supported; cancellation is deferred until unlocking.
Do not close descriptors for the lock inode during a transaction. Use one Mesa
library per process; forked children must exec before using it. Exit releases
the job lock, but a crashed compositor's outstanding kernel owned-surface lease
still requires supervised retirement of all shared render-FD holders.

## Image lifetime

The seven exported functions and fixed 32-byte image descriptor are declared in
`common/mbx_window_export.h`. Functions return zero or a negative errno.

- `n810_mbx_window_get_layout(&caps)` queries the inherited owner's capabilities.
- `n810_mbx_window_export(texture, &image)` publishes a completed texture after
  `glFinish`. It becomes read-only and cannot be evicted while published.
- `n810_mbx_window_import(texture, &image)` binds a foreign token to allocated
  level-zero, non-mipmapped `GL_TEXTURE_2D` RGBA8 storage of matching dimensions.
  Creating and checking its renderable FBO establishes that storage. Use the
  existing admitted nearest/clamp sampler and texture-coordinate path. There is
  no pixel upload or CPU row flip. The source must be outside the receiver's range.
- `n810_mbx_window_forget(texture)` drops an imported binding after consuming work
  finishes. Delete that texture afterward; its stale CPU backing stays inaccessible.
- `n810_mbx_window_export_release(texture, &image)` unpins the exact publication
  after the compositor's completion ACK. Keep the producer texture name alive
  until release succeeds; only then may it be redrawn.
- `n810_mbx_transaction_begin/end()` bracket an indivisible sequence across
  clients. Each flush nests inside this transaction. The owned RGB565 final-target
  begin/release path holds it through the display sink, so clients wait rather
  than submit into the compositor's outstanding lease.

A layout-1 image has version 1, dimensions 128x128 and a zero reserved word.
A layout-2 image has version 2, dimensions matching its class, and `stride_bytes`
in the last word: 960 for native images or 512 for small images. Layout, dimensions,
format, stride, session and generation must agree; there are no user addresses.

Call import/forget between draws, after `glFinish`; pending work returns `-EBUSY`.
Restore the compositor's render target after creating an imported texture/FBO:
imported textures are sources, not writable render targets. Treat errors as failed
frames, never a request to read back or upload substitute pixels.

The producer sends the descriptor with normal window/frame identity. Pocket
imports, draws with its existing texture path, completes the display sink, then
ACKs. The producer releases that publication before reusing its image. The image
holds no global kernel surface lease while waiting. Closing a window forgets its
imports and retires outstanding publications through the broker.

## Bounded incremental window history

Completed 2D window targets now keep a 436-byte, one-quad checkpoint that samples
that window's completed version-14 token (version 13 for the legacy layout).
There is no CPU image upload or global resident-bank background dependency.
On an FBO switch, the completed image reconstructs this checkpoint instead of
saving the old draw stream. Small targets and native 240x320 targets use the same
path. Targets with attached depth retain their existing 3D history behavior;
a color checkpoint does not preserve depth.

The next incremental submission samples the old image into private scratch 14
and 15 for the RGB and alpha replays, then merges into the client slot. The final
merge is the first operation that replaces the source image. Even an unblended
update uses these two scratch passes when a checkpoint is present, so there is
no read/write feedback and both channels remain available. The existing job
transaction spans all three operations. Imported/published images remain
read-only until their existing forget/ACK/release barrier. No additional client
slot is required; producer 0..5 and Pocket 6..13 remain valid partitions.

This window path is independent of `N810_MBX_SURFACE_CHECKPOINT`, which now
requires the exact value `1`. Unset, empty and `0` disable that legacy path, and
window targets cannot select its global resident checkpoint. The separate-alpha
environment flag likewise uses exact `1`; required checkpoint scratch replay is
an internal lifetime rule, not an optional blend mode.

## Desktop command pressure

Mesa no longer rejects a frame merely for exceeding 32 scissor-mask changes.
That was a software policy, not a separate kernel limit. The actual encoder's
65,536-command limit, 256-draw frame limit, 2,048-triangle frame limit, wire bounds
and 256-triangle per-draw limit remain intact.

Adjacent 2D records with bit-identical program, uniform/immediate payload,
viewport, blend, cull, interpolation, resource and scissor state are concatenated
without deduplicating or changing any vertex attribute. New indices are rebased;
triangle order and provoking vertices remain exact. The last-record length gives
constant-time lookup across resource-table insertion; clears and history restores
invalidate it. Set `N810_MBX_DRAW_BATCH=0` for an unbatched control. Command-budget
accounting uses the kernel draw encoder's conservative formula, charging actual
mask transitions and one program/state block for a merged draw.

Native/small window targets can also retire a full batch through their GPU token
checkpoint, including with `N810_MBX_SURFACE_CHECKPOINT=0`. Both draw and texture
pressure recognize the one-quad checkpoint. RGB565 desktop targets at 400x256 or
800x480 keep their existing final owned export/DMA path; this change does not
invent a framebuffer checkpoint, read pixels back, increase kernel budgets or
permit arbitrarily large single frames. Truly over-budget incompatible geometry
still fails before submission.

Actual ARM Mesa with a fake service admits 640 separate quad submissions and
40 changed clip regions as 40 draws / 78,144 wire bytes at both desktop sizes,
with one final owned export. Disabling batching reproduces the hard draw-cap
rejection. A 1,280-quad native-window pressure case completes in four bounded jobs
using version-14 history and scratch merge while the legacy checkpoint flag is
zero. These establish command/lifecycle behavior, not hardware pixels or FPS.

## Resident two-texture channel combine

`n810_mbx_window_channels(source, mask, target, mode, &view)` is a general
pointwise operation: preserve source RGB and replace alpha from the mask. It
reuses the existing verified single-texture sampler and two-texture channel
selector; it adds no kernel ABI, speculative sampler opcode or shader dialect.
The three names belong to the current GL context. The caller finishes pending GL
work first and allocates target level-zero RGBA8 storage with no pixel payload.
The helper leaves GL bindings, viewport, sampler and framebuffer state unchanged.
It rejects aliasing, published/imported destinations, unsupported modes and slot
exhaustion before submitting any job. It never reads GPU memory back or uploads
the composed output.

Modes are `MBX_WINDOW_ALPHA`, `MBX_WINDOW_RED_ALPHA`, and
`MBX_WINDOW_BINARY_RED_ALPHA`. CPU-uploaded RGBA8/BGRA8 inputs use Mesa's existing
canonical storage for their initial transfer. RED modes put the selected red
channel into the transfer's alpha lane; this is CPU format/channel packing,
not GPU red-channel swizzling or CPU composition. Binary mode checks every
logical red value before any GPU submission and rejects values other than0/255.
Resident inputs remain on the GPU; resident RED masks are unsupported and fail
before submission, without an implicit readback. sRGB, filtering, mipmaps,
resampling, inversion and additional pixel formats are not admitted here.

Both inputs must have equal literal GL dimensions. Inputs1..128 on each axis
use an allocated128x128 target; native240x320 inputs use a240x320 target in layout2.
The returned view distinguishes logical width/height from storage width/height.
**The caller must scale normalized sampling UVs by logical/storage dimensions.**
Preserve that view with a cached handle; do not treat padded storage as logical
content. Mixed uploaded/resident inputs must satisfy the same dimension and
storage-class checks. Source/target feedback and duplicate resident sources are
rejected. For larger canonical uploads, `n810_mbx_window_channels_region(source, mask,
target, &rect, mode, &view)` accepts equal-size input textures up to1024x1024.
The rectangle is1..128 on each axis and is bounds-checked without overflowing
coordinate additions. Both inputs use the same canonical level-zero x/y origin;
no row flip or resampling is introduced. Only selected rows/columns are packed,
so temporary transfer storage stays below148KiB for the two128x128 packets.
The target is128x128 and returned view contains the rectangle width/height;
consumer geometry/UV placement and tile streaming remain caller responsibilities.
Binary mode validates only the selected rectangle, not unseen mask pixels.
Cropped resident inputs and resident RED masks reject before submission. An
uncropped128x128 ALPHA region retains the existing resident path. The original
whole-image and240x320 interfaces are unchanged. Other larger/resampled image
operations retain their separate, explicitly selected paths.

Uploaded inputs render into private scratch14/15. A final channel merge writes
the destination client slot. If one input is already resident, only the other
needs a transfer/render; two compatible resident inputs need only the80-byte
merge job. The existing job transaction spans all stages. Final output uses the
normal export/ACK lifetime and is sampleable through the existing token path.
CPU access to its stale shadow remains rejected.

The helper uses one free destination slot and never borrows another client's
partition. Evict/delete cached outputs *before* requesting a replacement, after
pending consumers finish. A budget of four small slots cannot hold four cached
outputs plus a fifth replacement; reserve staging capacity, account actual
128x128 storage, and preserve any slots needed by other live intermediates.
`-ENOSPC` has no hardware side effects. No unsafe live-image eviction is added.

Local checks cover30 small/native format/mode transfer cases with exact bytes,
binary rejection and shared encoder admission. Actual ARM Mesa with a fake
service exercises7x11->128x128 and240x320 targets, mixed/resident inputs,
merge-only submission, GL-state preservation, alias/capacity failures, and
readback tripwires on every duplicate fake GPU descriptor. These are command and
lifecycle checks. Physical pixel equality and CPU/FPS still require device
acceptance before runtime promotion.

## Local verification and remaining device gate

From the repository root:

```sh
python3 pocket/graphics/driver/mbx/tests/check_window_channels.py
python3 pocket/graphics/driver/mbx/tests/check_draw_batch.py
python3 pocket/graphics/driver/mbx/tests/check_window_checkpoint.py
python3 pocket/graphics/driver/mbx/tests/check_native_windows.py
python3 pocket/graphics/driver/mbx/tests/check_window_sharing.py
python3 pocket/graphics/driver/mbx/tests/check_window_images.py
python3 pocket/graphics/driver/mbx/tests/check_prepared.py
```

These checks cover both layouts, all guard locations, page-table bank boundaries,
all published sampler addresses/pitches, mixed upload/token cache expansion,
stale-token rejection, the actual service admission block, publication lifetime,
context ranges, process/thread locking, cancellation and exit cleanup. Existing
legacy window and prepared-command parity checks remain intact.

The ARM module builds against the pinned `5.15.224-n810-mbx-clock-wip1` ABI with
matching import CRCs and verified DMA descriptor layout. Isolated ARM Mesa tests
check its window/transaction symbols, ordinary software-context pixels, and real 240x320 and
128x128 GL texture import/forget with explicitly fake kernel metadata. The latter
submit zero GPU writes and establish neither GPU pixels nor performance. Test-only
ioctl fixtures are not linked or packaged into the driver.

Physical acceptance still needs guarded offscreen patterns through bank 1,
native RGB/alpha composition, exact output pixels and CPU/FPS before live Pocket
integration. No such device test or installation is claimed by the local build.

The checkpoint candidate additionally passes 3,000 software admission/encode
cycles across native and small targets, with source-token lifetime checks through
both scratch passes and merge, feedback rejection, explicit flag parsing and
pixel-centre UV math checks. An actual ARM Mesa test using a fake GPU service
executes 256 incremental updates with same-target reuse, FBO switches, repeated
idle `glFinish` and an explicit clear. Job draw counts remain bounded at two;
no global resident descriptor is emitted with the legacy flag set to `0`.
These are command/lifecycle checks, not hardware pixel or performance results.
The new full-image sampling checkpoint still requires offscreen pixel acceptance
on the Nokia before enabling it in a live runtime.

The region extension's local checks include nonzero source origins, a padded
1024-wide row stride, all corner/edge/interior crops, exact selected transfer
bytes and binary-mask values. Actual ARM Mesa/fake-service tests exercise
1024x1024 inputs with128x128,7x11 and1x1 regions; invalid/overflow coordinates,
zero sizes, feedback and cropped resident inputs reject before a GPU write.
These remain software/command checks; physical baseline/candidate measurements
must use the matched runtime adapter and identical viewport/UV semantics.
