# N810 Linux 5.15.224

This directory carries the N810 kernel changes and configuration, the external
clock module used for build compatibility checks, and a portable Linux builder.
The builder downloads the exact Linux 5.15.224 release from kernel.org, verifies
its SHA-256, applies the complete maintained kernel-source delta, and checks all
55 changed source files against the maintained revision.

The input lock records upstream commit
`700e62ea909a70b9f72692d8b7a192ac7ebde0aa` and maintained commit
`6bd43ee8d27b207c958808368251d55ec0475f9e`. The N810 board support originates in
[relghuar's Nokia tablet kernel](https://github.com/relghuar/linux-stable-nokia-tablets),
with the subsequent board, console, Wi-Fi, Bluetooth, display and clock changes
carried in this patch. Source copyright and license notices remain in the files;
the upstream archive contains the kernel's COPYING and LICENSES directory.
The clock trial module declares GPL licensing in its source.

## Build on Linux

On Debian, install the build dependencies:

```sh
sudo apt-get install build-essential gcc-arm-linux-gnueabihf \
    binutils-arm-linux-gnueabihf flex bison bc libssl-dev libelf-dev \
    kmod curl ca-certificates xz-utils patch python3
```

From the repository root:

```sh
python3 platform/kernel/build.py --work /tmp/n810-kernel-build --jobs 4
```

The work directory must be new. Allow at least 3 GiB of free space. The source
archive is about 122 MiB. Build outputs and logs stay under the work directory.
The build uses the installed ARM cross-compiler and records its version.
The verification report identifies the toolchain used in the clean build.

The default command line selects `/dev/mmcblk0p2` as an example SD-root layout.
Choose the actual filesystem before preparing an image for a tablet:

```sh
python3 platform/kernel/build.py --work /tmp/n810-kernel-custom \
    --root-device /dev/mmcblk0p2 --jobs 4
```

`--root-device` also accepts `PARTUUID=...`. Such an identifier belongs in the
local build invocation. The checked-in configuration uses a generic device path.
`--archive /path/to/linux-5.15.224.tar.xz` reuses a downloaded source archive after
the same checksum verification.

## Inputs and outputs

| File | Purpose |
|---|---|
| `source.lock.json` | Upstream URL and checksum, source revisions, input hashes, image budget and expected module count. |
| `n810-5.15.224.patch` | All 55 maintained kernel build-source changes relative to Linux 5.15.224. |
| `source-files.json` | SHA-256 for each reconstructed changed source file. |
| `n810.config` | Saved candidate configuration with a generic root path and build-time export-whitelist location. |
| `binding-api-whitelist.txt` | Exports retained for separately built clock/GPU modules. |
| `clock-module/` | Source for the matching clock module used to check kernel symbol versions. |
| `build.py` | Download, verification, compilation, module staging and result manifest. |

The builder produces `package/zImage-omap2420-n810`, the generated device tree,
199 configured kernel modules under `package/root/lib/modules/`, and the separate
clock trial module. It checks the combined image against the recorded
2,095,104-byte NOLO budget, verifies the external module's symbol CRCs and release,
and writes `package/BUILD.json` with output hashes. Kernel, device tree and
modules all come from this build.

The build identity and timestamp are fixed in the script. The toolchain version,
root-device selection and input hashes remain part of the result. The clean-build
report describes the verification actually performed.

The patch includes all maintained kernel build sources. The historical fork's
README and `n810/` helper directory are listed as exclusions in the lock file;
those legacy helpers used workstation paths and older boot/image workflows.
This builder supplies their compilation and packaging role.

Compilation produces a local candidate. Installation and boot acceptance use the
intended tablet's storage layout, firmware, calibration and recovery procedure.
The builder performs source and compiler operations locally.
