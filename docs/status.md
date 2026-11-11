# Current status

Updated 9 November 2026. See the [N810 GPU desktop](posts/2026-11-09-gpu-desktop.md) and [Symbian runtime](posts/2026-11-09-symbian-runtime.md) entries for the latest tablet work.

| Area | Established result | Remaining work |
|---|---|---|
| Debian platform | SD-root operation, USB maintenance, Wi-Fi, Classic Bluetooth, calibrated touch, and console/GUI lifecycle checks. | Broader power calibration, reconnect, and sustained-use coverage. |
| Kernel | Packaged Linux 5.15.224 source changes and build inputs passed an independent fresh-checkout ARM build: generated N810 device tree, 199 modules and 35 external-module CRC checks. Historical November graphics runs identify `5.15.224-n810-mbx-clock-wip1`. | Attended boot acceptance for the newly packaged configuration and broader release coverage. |
| Pocket | Shared desktop and app registry support terminal and native graphical frontends. Help/input and reconnect fixes are included. The fresh-checkout first-session walkthrough and native frontend checks passed on 7 November. The broader source runner passes with generated fictional map and terrain fixtures. | Verify first installation on another N810. See the [fresh-checkout findings](reference/component-build-verification.md#fresh-checkout-walkthrough-7-november). |
| Native Mac/Linux GUI | Source build includes SDL/OpenGL adapters, font and Room mesh preparation, direct Room pixels, input and resize checks. Apple M1 Pro checks and explicit Linux software-GL container checks passed; the ARM framebuffer presenter cross-build passed. | N810 startup is covered by the [GPU run guide](how-to/run-n810-gpu.md). |
| Mac GPU producers | Window composition, Flux/Flurry, map shading, and terrain have dated exact-output comparisons and native desktop execution evidence. | Matched whole-frame performance measurements and integration of the remaining experimental comparison programs. See the [GPU effects entry](posts/2026-11-07-gpu-effects.md). |
| Symbian compatibility | ChessGenius runs native ARM code and draws through MBX on the N810. | Improve responsiveness and finish the managed Pocket launcher. See the [native result](posts/2026-11-06-native-symbian.md) and [GPU work](posts/2026-11-07-symbian-surfaces.md). |
| APRS and SSH | Shared feed ownership; retained packet workspace exercised through physical and SSH terminal clients. | Broader live-radio and interaction checks across current source. |
| Reticulum/LXMF | Normal-TUI Nokia/Mac signed message exchange on 24 October. | Range and sustained recovery testing. |
| HTIT | External microReticulum execution, receiver-verified resources, messaging, and targeted reconnect/resource repairs. | Long-suite watchdog reliability, and fresh end-to-end checks for the 2 November library refresh. |
| MBX | Standard 400 by 400 glxgears with GPU transform, lighting and rasterization; two physical runs at 30.78 and 30.63 completed GPU FPS. | Broader driver coverage and production integration. |
| VGP | Checked diagnostic transform/lighting output and live Mesa integration in the 4 November gears runs. | Broader shader and geometry coverage. |

The [chronological journal](journal.md) preserves the failures and intermediate results behind this table. The [acceleration reference](reference/acceleration.md) distinguishes physical MBX measurements from newer host graphics results. The [roadmap](roadmap.md) tracks the remaining work.

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

## What readers can build now

The [native graphical frontend](pocket/graphics.md), [terminal desktop](tutorials/first-session.md), [kernel](how-to/build-kernel.md), [HTIT firmware](how-to/build-htit.md), and [frozen MBX/Mesa checkpoint](how-to/build-gpu-30fps.md) have source and build inputs in the repository. Regional map and elevation data are acquired with the [map build tools](how-to/build-map-data.md). Generated data and native binaries are built locally.

The November 7 source integration passed a fresh-clone Mac graphics build, focused frontend checks, and the Linux release-container build and source-archive unpack/build checks. Container GUI tests explicitly use Mesa software OpenGL. Physical N810 graphics qualification follows the separate device test path. The journal identifies ongoing candidates that have yet to become published build checkpoints.

## Latest verified container build

On 7 November, [GitHub container build 42434184966](https://github.com/gordol/n810-revival/actions/runs/42434184966)
passed at revision `b331ac7`: 205 source test files, six HTIT wire-protocol
host tests, 28 Python RSN tests and 11 compiled RSN tests. The build completed
its kernel, frozen graphics, firmware and native frontend checks and uploaded
separate source and documentation archives. GUI checks used Mesa software OpenGL.

The [verification record](reference/component-build-verification.md#github-container-build-7-november)
records the tested revision and launcher-test correction. To run the same
container build, follow the [validation guide](how-to/validate.md).
