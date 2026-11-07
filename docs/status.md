# Current status

These results were recorded by 4 November 2026. Each row separates the tested capability from the work still needed.

| Area | Established result | Remaining work |
|---|---|---|
| Debian platform | SD-root operation, USB maintenance, Wi-Fi, Classic Bluetooth, calibrated touch, and console/GUI lifecycle checks. | Broader power calibration, reconnect, and sustained-use coverage. |
| Kernel | Packaged Linux 5.15.224 source changes and build inputs passed an independent fresh-checkout ARM build: generated N810 device tree, 199 modules and 35 external-module CRC checks. Historical November graphics runs identify `5.15.224-n810-mbx-clock-wip1`. | Attended boot acceptance for the newly packaged configuration and broader release coverage. |
| Pocket | Integrated 0.1.0 source, terminal windows, shared navigation, applications, and local/remote service adapters. | Current whole-desktop responsiveness and clean installation coverage. |
| APRS and SSH | Shared feed ownership; retained packet workspace exercised through physical and SSH terminal clients. | Broader live-radio and interaction checks across current source. |
| Reticulum/LXMF | Normal-TUI Nokia/Mac signed message exchange on 24 October. | Range and sustained recovery testing. |
| HTIT | External microReticulum execution, receiver-verified resources, messaging, and targeted reconnect/resource repairs. | Long-suite watchdog reliability and fresh end-to-end checks for the 2 November library refresh. |
| MBX | Standard 400 by 400 glxgears with GPU transform, lighting and rasterization; two physical runs at 30.78 and 30.63 completed GPU FPS. | Broader driver coverage and production integration. |
| VGP | Checked diagnostic transform/lighting output and live Mesa integration in the 4 November gears runs. | Broader shader and geometry coverage. |

The [chronological journal](journal.md) preserves the failures and intermediate results behind this table. The latest graphics measurements are in the [acceleration reference](reference/acceleration.md).

## Building and installing the platform

The repository carries the maintained kernel changes, configuration,
export whitelist, external clock-module source and portable build script. The
builder verifies Linux 5.15.224 from kernel.org and reconstructs the maintained
source at `6bd43ee8d27b207c958808368251d55ec0475f9e`.

On 4 November, an independent source checkout completed the
ARM build with 199 modules and all 35 external-module symbol-version checks. Its
combined image is 2,077,084 bytes. The [verification record](reference/kernel-build-verification.md)
describes the fresh checkout, toolchain, configuration and output checks. The
[kernel guide](how-to/build-kernel.md) gives the repeatable command.

The [component verification page](reference/component-build-verification.md) records HTIT firmware, graphics, and map builds. A complete installable root-filesystem image still requires a Debian root, device firmware, an installation policy, and an integrated image-assembly check. The [platform reference](reference/platform-files.md) identifies the available services and configuration files.
