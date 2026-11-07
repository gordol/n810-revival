# MBX and Mesa source checkpoint

This directory contains the original MBX packet encoders, the experimental GPU module, Mesa integration, presentation helpers and their tests. The top-level directories preserve the earlier 4 November source checkpoint. The later [verified 30 FPS snapshot](checkpoints/30fps-20261104/README.md) contains the frozen production changes and regression tests behind the repeated GPU-geometry result. Its [build guide](../../docs/how-to/build-gpu-30fps.md) selects that source explicitly.

`common/` defines command construction and the supported vertex instructions. `kernel/` owns DMA buffers, submission and completion handling. `mesa/` adapts Mesa 22.3.6 to those interfaces. `runtime/` contains experimental device-side diagnostics. `tests/` exercises the encoders, ownership checks and software reference comparisons.

The source archive and Debian armel sysroot packages are pinned by URL and SHA-256 in `dependencies.lock.json`. The [graphics build guide](../../docs/how-to/build-graphics.md) describes the portable builder. The [verification page](../../docs/reference/component-build-verification.md) records the module and Mesa build results for each checkpoint.

Source files retain their SPDX or upstream license notices. Mesa's upstream archive supplies the licensing terms for its own code. Diagnostic and historical live-packaging helpers require their stated lab inputs; the portable build entry point is `build.py`.
