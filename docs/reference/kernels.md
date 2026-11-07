# Kernel checkpoints

Reconciled from retained build and device records on 4 November 2026. These entries describe observed checkpoints; live installed state requires a fresh device check.

| Kernel | Recorded use | Relevant changes |
|---|---|---|
| `5.15.86-n810-debian1+` | Kernel-only installation on 4 October and payload readback on 5 October. | Debian boot, board support, and RFBI display lifecycle repairs. |
| `5.15.86-n810-console-rgb1+` | Normal power-cycle verification on 16 October, with 199 matching modules. | RGB console support alongside the accepted Bluetooth and USB changes. |
| `5.15.86-n810-rgb-sandbox1` | Local kernel and 199-module build. Device validation remained pending. | User, PID, and network namespaces; seccomp and seccomp filtering. |
| `5.15.86-n810-mbx-clock-v1` | Temporary physical boot on 31 October and subsequent clock experiments. | Shared graphics-divider provider and MBX bring-up support. |
| `5.15.224-n810-mbx-clock-wip1` | Identified in physical GPU runs on 3 and 4 November. | Stable-kernel merge with maintained N810 overlays and graphics clock work. |

The 5.15.224 local build produced a 2,077,948-byte combined kernel/DTB image and 199 modules. Its retained image budget was 2,095,104 bytes. The matching MBX clock module passed 35 symbol-version checks. The build note predates the later device evidence.

Kernel release strings and matching module metadata are part of the compatibility contract. The build's module count describes its configured set; additional experimental modules have separate build and load records.

The repository supplies the maintained kernel changes, configuration, export list
and [portable build recipe](../how-to/build-kernel.md), alongside the historical
[October RGB console patch](console-rgb-patch.md). A fresh-checkout build on
4 November produced a new 2,077,084-byte image, 199 modules and 35 matching
external-module symbol checks. Its generic root-device configuration and fixed
build metadata are documented in the [verification report](kernel-build-verification.md).
Firmware, calibration and recovery state remain device-specific inputs.
[Kernel journal entry](../posts/2026-11-03-kernel.md).
