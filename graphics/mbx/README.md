# MBX driver source

The PowerVR MBX driver source lives in `graphics/mbx/` in the repository.
It provides GPU command encoding, a Linux submission module and Mesa integration
for the N810.

| Path under `graphics/mbx/` | Contents |
| --- | --- |
| `common/` | Command encoders and shared interfaces. |
| `kernel/` | GPU submission, DMA buffers and completion handling. |
| `mesa/` | Mesa rendering and resource adapters. |
| `tests/` | Encoder, resource lifetime and pixel comparison tests. |
| `build-inputs/` | Kernel configuration, compiler and library inputs. |
| `dependencies.lock.json` | Dependency download locations and checksums. |
| `checkpoints/` | Earlier driver versions used by historical benchmarks. |

Start with [Run the N810 GPU desktop](../../docs/how-to/run-n810-gpu.md).
The [driver build guide](../../docs/how-to/build-graphics.md) covers compilation.
The [rendering explanation](../../docs/explanation/rendering.md) describes how
Pocket uses the driver.

Mesa and Linux retain their upstream license terms; source files carry their
applicable notices.
