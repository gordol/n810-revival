# Verified 30 FPS graphics source

This snapshot contains the MBX kernel driver, Mesa integration and regression tests used by the 4 November 2026 synchronous GPU-geometry checkpoint. The two physical measurements completed 30.78 and 30.63 GPU frames per second with standard 400 by 400 `glxgears`.

The source came from the sealed command-replay and FIFO-polling archive identified in [SOURCE.json](SOURCE.json). Its archive SHA-256 is `d5b128752a3a39a6eaca91c70cde8fc73b2e9ecf5fc0687e952813b9ab0925ff`. All forty kernel compilation inputs match the tested module's build receipt. The imported production source preserves the archive's bytes. The manifest records one test correction: the earlier batch test expected 629 commands, while this checkpoint uses the validated 227-command compact packet.

## Find the implementation

| Area | Source |
|---|---|
| Command reuse and exact input matching | [mbx_vgp_wire.c](experiments/vgp-service-20261104/common/mbx_vgp_wire.c) |
| Bounded FIFO polling and command credits | [mbx_vgp_stream.c](experiments/vgp-service-20261104/common/mbx_vgp_stream.c) |
| Kernel command-buffer ownership and submission | [mbx_render_service.h](experiments/vgp-service-20261104/kernel/mbx_render_service.h) |
| DMA allocation and ownership | [mbx_dma.c](experiments/vgp-service-20261104/kernel/mbx_dma.c) |
| Mesa GPU-geometry path | [sp_mbx_vgp_impl.h](mesa/sp_mbx_vgp_impl.h) |
| Mesa active-sampler patch | [prepare_sampler_scan.py](mesa/prepare_sampler_scan.py) |
| Command-reuse differential test | [test_wire_replay.c](experiments/vgp-service-20261104/test_wire_replay.c) |
| Scalar/batch FIFO and retry tests | [test_stream_batch.c](experiments/vgp-service-20261104/test_stream_batch.c) |
| Actual-source Mesa sampler comparisons | [test_sampler_scan.py](tests/test_sampler_scan.py) |

The top-level `common/` directory supplies the Mesa-side interfaces and the earlier encoder tests. `experiments/vgp-service-20261104/common/` supplies the service's later encoder. Both paths preserve the archived layout. The adjacent `kernel/` directory contains the exact compilation inputs assembled by the tested module builder.

## Build and verify

Use the [30 FPS build and test guide](../../../../docs/how-to/build-gpu-30fps.md). It includes local source views, the selected options, dependencies, commands and results. The repository's portable builder selects this snapshot with `--checkpoint 30fps-20261104` and writes its products into a new output directory.

`verify.py` checks the manifest and decoded fixture. `test.py` runs fifteen offline suites with AddressSanitizer and UndefinedBehaviorSanitizer. The tests cover command reuse, FIFO credits and bounded retries, primitive assembly, vertex data, color dependencies, allocation failure and Mesa sampler-state handling. The fixture is the archived standard-gears shader/geometry packet represented as hexadecimal text. Its decoded bytes and checksum are recorded in the manifest; the test runner reconstructs it in the output directory.

[VERIFICATION.json](VERIFICATION.json) records the source-import checks, ARM builds and offline tests. The Mesa rebuild reproduced the tested library's exact bytes. The module rebuild preserved its code, data and relocation sections, with changes in debug information and the build-ID note. These local checks accompany the earlier physical results described in the [journal](../../../../docs/posts/2026-11-04-gpu-performance.md#repeating-the-30-fps-result).

This directory preserves the synchronous, single-image checkpoint. Ongoing two-image experiments continue in the separate bring-up workspace.
