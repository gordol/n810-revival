# Build and test the verified 30 FPS driver

The repository contains a frozen copy of the driver and Mesa changes behind the two physical runs at 30.78 and 30.63 completed GPU FPS. It lives under `graphics/mbx/checkpoints/30fps-20261104/`. The [journal](../posts/2026-11-04-gpu-performance.md#repeating-the-30-fps-result) explains the debugging and measurements; this guide identifies the code and repeats its source checks, compilation and offline tests.

## Read the changes

These local source views come directly from the checked-in files when the site builds. The GitHub links point to the same paths for repository review.

| Change or test | Read locally | GitHub |
|---|---|---|
| Exact command-template matching and reuse | [Encoder](../assets/source/gpu-30fps/command-reuse.c.txt) | [mbx_vgp_wire.c](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/experiments/vgp-service-20261104/common/mbx_vgp_wire.c) |
| FIFO capacity, sixteen-poll option, sleep fallback | [Submission](../assets/source/gpu-30fps/fifo-stream.c.txt) | [mbx_vgp_stream.c](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/experiments/vgp-service-20261104/common/mbx_vgp_stream.c) |
| Kernel ownership, cache lifetime and submission | [Render service](../assets/source/gpu-30fps/render-service.h.txt) | [mbx_render_service.h](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/experiments/vgp-service-20261104/kernel/mbx_render_service.h) |
| Mesa sampler scan | [Patch](../assets/source/gpu-30fps/sampler-patch.py.txt) | [prepare_sampler_scan.py](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/mesa/prepare_sampler_scan.py) |
| 19,190 command comparisons and rejection cases | [Replay test](../assets/source/gpu-30fps/test-command-reuse.c.txt) | [test_wire_replay.c](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/experiments/vgp-service-20261104/test_wire_replay.c) |
| FIFO occupancy, scalar/batch writes, 0/16/32 polls | [FIFO test](../assets/source/gpu-30fps/test-fifo.c.txt) | [test_stream_batch.c](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/experiments/vgp-service-20261104/test_stream_batch.c) |
| 12,000 comparisons of the actual Mesa routine | [Sampler test](../assets/source/gpu-30fps/test-samplers.py.txt) | [test_sampler_scan.py](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/tests/test_sampler_scan.py) |

The [source manifest](../assets/source/gpu-30fps/SOURCE.json) maps each imported file to its archive path and checksum. It also identifies the tested binaries and the hexadecimal gears fixture. The [snapshot manual](../reference/gpu-30fps-inputs.md) describes the complete layout.

## Build on a Linux host

Use the compiler and package prerequisites in the [graphics build guide](build-graphics.md), and complete the [kernel build](build-kernel.md) first. The module needs the resulting generated headers and symbol-version table.

```sh
python3 graphics/mbx/build.py module \
    --checkpoint 30fps-20261104 \
    --work /tmp/mbx-30fps-module \
    --kernel-source /tmp/n810-kernel-build/linux-5.15.224 \
    --kernel-build /tmp/n810-kernel-build/build

python3 graphics/mbx/build.py mesa \
    --checkpoint 30fps-20261104 \
    --work /tmp/mbx-30fps-mesa --jobs 4
```

Both commands require new output directories. They verify the snapshot before copying source into their work directories. Mesa uses the existing checksum-pinned Mesa 22.3.6 archive and Debian armel sysroot packages. An optional `--download-cache /path/to/downloads` reuses matching archives from an earlier graphics build; each reused file is checked before copying.

Products and receipts are written to `package/` beneath each work directory. The commands perform local compilation. Hardware loading and display ownership belong to the attended bring-up procedure.

## Run the offline regression tests

The suite uses Python 3 and a C compiler with AddressSanitizer and UndefinedBehaviorSanitizer. On Debian, `build-essential`, `libasan8` and `libubsan1` provide the host compiler and sanitizer runtimes. The archive saved by the Mesa build supplies two pristine upstream source files for the topology and sampler comparisons.

```sh
python3 graphics/mbx/checkpoints/30fps-20261104/verify.py

python3 graphics/mbx/checkpoints/30fps-20261104/test.py \
    --work /tmp/mbx-30fps-tests \
    --mesa-archive /tmp/mbx-30fps-mesa/downloads/mesa.tar.xz
```

The test runner verifies the archive checksum, reconstructs the gears fixture, compiles the tests and writes a log for each suite plus `results.json`. It exercises fifteen suites. The FIFO test checks 3,540 occupancy/drain schedules for each scalar/batch and 0/16/32-poll combination, as well as invalid commands, faults and timeouts. The command-reuse test compares successful output and rejected input against full encoding. The allocator test injects allocation and DMA-remapping failures.

One test needed an import correction. Its archived expectations still described the old 629-command prototype. The corrected test checks the frozen 227-command packet's program, uniform and immediate values, original vertex attributes, capacity rejection, terminal command and untouched output tail. The manifest records both test hashes and the reason for the change. Production source retains the archived bytes.

## Identify the measured configuration

| Setting in the physical test harness | Value |
|---|---|
| `N810_MBX_WIRE_REPLAY` | `1` |
| `N810_MBX_FIFO_SPIN_POLLS` | `16` |
| `N810_MBX_FIFO_BATCH` | `0` |
| `N810_MBX_ASYNC` | `0` |
| `N810_MBX_ASYNC_FENCES` | `0` |

These are the recorded harness options. The module exposes `gpu_wire_replay`, `gpu_fifo_spin_polls` and `gpu_fifo_batch`; Mesa owns the asynchronous-presentation options. The physical runs used the single-image synchronous path, the original 400 by 400 gears workload, and a temporarily paused Pocket UI.

## Recorded build results

The local ARM module build passed all 64 imported symbol-version checks against the maintained kernel build. Its code, data and relocation sections match the sealed physical-test module. Debug information and the GNU build-ID note differ between the two build locations.

The Mesa rebuild produced SHA-256 `02878840d6bacadc155ca6278ce617c0b14e265428c811327b3a06611876e66d`, exactly matching the library used in the two physical runs. All fifteen offline suites passed after the archived packet test was corrected. The [verification receipt](../assets/source/gpu-30fps/VERIFICATION.json) records the hashes and checks; the [physical measurement record](../assets/results/gpu-30fps-20261104.json) records the earlier device runs.

[GPU journal](../posts/2026-11-04-gpu-performance.md) · [Graphics inputs](../reference/graphics-inputs.md)
