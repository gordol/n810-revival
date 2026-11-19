# Files installed on the N810

These are source templates for the tablet's root filesystem. They are not a
virtual machine. The matching commands are in `../scripts/`.

| Area | Files to start with |
|---|---|
| Power and display | `n810-charged.*`, `n810-powerd.init`, `n810-displayd.init`, `n810-backlightd.init`, `n810-wake.*`, `n810-debian-lock.conf`, `n810-ledd.init` |
| Input and console | `n810-buttons.map`, `n810-console.map`, `n810-keyboard.service`, `n810-fn-remap.service`, `n810-input-remap.service`, `n810-console-ux.init` |
| Connections | `debian-usb-interfaces`, `n810-wifi.*`, `n810-bluetooth-address.service`, `10-n810-address.conf` |
| Startup and policy | `n810-boot-mode.init`, `n810-zram.*`, `n810-power.sudoers`, `n810-idle.conf` |

Some devices use SysV init, some use systemd units, and a few files are
alternatives from different platform revisions. This source slice is not a
complete installer; check the exact target release before placing a file on
the tablet.

The internal Debian builder uses SysV init like the original Debian tablet and
keeps D-Bus. It selects sequential SysV startup through `.legacy-bootordering`
so Debian's package-generated dependency files cannot skip the staged N810
services. It starts `n810-console-ux` for the Fn translator and keymap,
generates a unique Ed25519 SSH host key before Debian's `ssh` service, then
runs touch setup before the GPU Pocket desktop. The Bluetooth address init
script provisions the controller before BlueZ starts. Internal images use
the original idle configuration: dim after 60 seconds, blank after 300 seconds,
and wake from the keyboard or slider. The full wake helper owns Power and
brightness events; the separate display-keys service is not enabled alongside
it. The ambient LCD daemon runs with its existing display configuration.

The NOLO boot-reason reader and boot-mode service select quiet charging for a
charger-start boot. Touch calibration and Pocket startup defer while that mode
is active. Missing or malformed boot metadata retains normal mode. Time
synchronization uses chrony with the original IPv4/no-seccomp invocation.

The kernel boots with the built-in powersave governor at the lowest supported
CPUFreq step (330 MHz). The source-backed n810-cpu-policy helper supports
explicit privileged save, balanced, and performance selections and restores
the display after each transition. Available steps still reach 480 MHz.
These source changes require rebuilt kernel and root packages; they have not
been accepted on the new tablet by changing repository files alone.

## Recreating the system services

The internal image stages the Power menu entry that `n810-wake` calls. It opens
`n810-power-overlay` on a temporary Linux VT and restores Pocket's VT on exit;
it does not invoke the historical X11 or console-session switcher. The menu
includes screen and charging controls, quiet charging, airplane mode, guarded
CPU policies and confirmed shutdown/restart. Displayd remains the ambient LCD
policy daemon. The wake helper owns Power and brightness events.

The builder creates `n810-power` and `n810-radio` groups for nokia and installs
bounded sudo policies. Power helpers and per-device RNode setup are independent
of optional service startup. The Bluetooth SysV defaults honor the persistent
airplane marker, as the managed Wi-Fi helper already does.

`platform/bootstrap/system_contract.py` runs before packing the internal image.
It checks the system command/helper files, group membership and single wake
owner, and records content hashes in the root bootstrap manifest. New kits identify
this check as `n810-internal-v6`; Check files requires its dependency manifest. It excludes
personal state, identities, radio bonds and offline datasets.

For a Classic Bluetooth RNode, pair it on the destination tablet, then use
`n810-rnode-configure --stdin` as root to save its controller/peripheral address
pair. The generic image contains no endpoint address configuration. The
no-argument SPP helper reads that protected policy, verifies the controller and
bond, and refuses occupied or mismatched mappings. It creates only a lazy
`rfcomm0` mapping on channel 1; it does not open the radio. Connections invokes
it when explicitly connecting a configured `/dev/rfcomm0` RNode.

The complete image builder also accepts `storage_target=sd`. It uses the same
services and a single ext4 partition selected by the kit's unique PARTUUID.
The expansion service resolves that PARTUUID for either medium. The SD writer
operates on a removable card in a macOS reader, while internal writes keep
the existing N810 model/capacity/USB identity checks.
