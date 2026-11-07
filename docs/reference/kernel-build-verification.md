# Kernel clean-build verification

*Completed locally on 4 November 2026.*

An independent Git clone of the source snapshot built the N810 Linux 5.15.224
kernel from the packaged inputs. The build fetched the pinned upstream archive,
verified its checksum, applied the N810 patch and checked all 55 changed source
files against the maintained revision. The compiler then produced the kernel,
device tree, configured modules and external clock trial module.

| Check | Result |
|---|---|
| Checkout | Clean independent clone, with its own objects and no Git alternates. |
| Build source snapshot | `42e4ff23c4c514613a88d560bddcb8387bebc783`; temporary local verification commit. |
| Maintained source | `6bd43ee8d27b207c958808368251d55ec0475f9e`. |
| Compiler | `arm-linux-gnueabihf-gcc (Debian 14.2.0-19) 14.2.0`. |
| Kernel release | `5.15.224-n810-mbx-clock-wip1`. |
| Kernel modules | 199. |
| External clock-module symbol versions | All 35 matched the freshly built kernel. |
| Combined image | 2,077,084 bytes. |
| Image budget | 2,095,104 bytes, leaving 18,020 bytes. |
| Compiler warning/error lines | 0 / 0. |
| Generated outputs | All 221 file hashes checked after copying the package out of the builder. |

## What was exercised

The test created a Git snapshot of the source, transferred that
snapshot as a Git bundle into the Linux builder, and cloned the bundle into a
new checkout. The build used a new source and output directory. Its only project
inputs were the cloned files; Linux came from the public, checksum-pinned archive.
The existing development kernel checkout, saved object files and historical
module archive supplied no build inputs.

The build command was:

```sh
python3 platform/kernel/build.py --work /tmp/n810-kernel-build --jobs 4
```

The [machine-readable verification record](../assets/kernel/verification.json)
contains the input hashes, output hashes and Debian package versions. The build
script and source-lock hashes in that record match the packaged files. The local
snapshot ID identifies the tested code snapshot; later documentation additions
leave those tested build inputs unchanged.

## Configuration and acceptance

The published configuration uses `/dev/mmcblk0p2` in place of the development
filesystem's partition identifier. The builder fixes the build user, host and
timestamp, and supplies the export-whitelist path for its current checkout.
Those choices produce a new build with its own recorded hashes. The historical
image was 2,077,948 bytes; this verification produced 2,077,084 bytes.
A byte-for-byte comparison requires identical configuration, toolchain and build
metadata.

This verification covers compilation, source reconstruction, image size and module
compatibility. The new image is a local candidate for a separately attended boot
test. Earlier physical runs remain documented in the [kernel checkpoints](kernels.md).

[Build instructions](../how-to/build-kernel.md) | [Input reference](kernel-build-inputs.md)
