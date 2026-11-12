# N810 Setup

Run `make setup` from the Pocket directory to open **N810 Setup**. The setup
screen is also available in the application menu. Start it directly through
either frontend with `make tui EXTRA=--setup` or `make gui EXTRA=--setup`.

N810 Setup builds and checks a private internal-install kit and identifies the
tablet. Its RAM-installer route has not completed a physical installation. The
tested macOS route uses the tablet's stock Maemo USB mass-storage export to
write and read back all 2 GB, then uses native 0xFFFF to flash the matching
kernel. No SD card is involved.

**Build kit from source** in Setup runs `make n810-build-internal` with Docker.
Enter a new local kit folder, an Ed25519 public key file, and a local `nokia`
password in the guided fields. The password is hidden and cleared from the form
when the build starts. The Make target builds the kernel, MBX module, Mesa,
Pocket release runtime, and Debian root from tracked source, then packs and
verifies the internal kit. It does not access a tablet. A RAM-installer output
is optional for its separate development path.

## Use the app

For a physical installation on macOS, boot stock Maemo on the new tablet and
export its internal USB storage. Run `sudo -v` in the terminal that launches
Setup. Enter that tablet's `/dev/diskN` whole disk and USB location in the Mac
fields, then choose **Install Debian + Pocket**. Setup checks the disk model,
exact 2 GB capacity, and USB location, writes the image, and reads back the
entire disk. It builds the pinned host flasher before writing, then waits for
you to return **that tablet** to update mode and
flashes the matching kernel. The install resumes from its verified write receipt
if you reopen Setup before the kernel flash. To check the disk without writing,
choose **Check Mac N810 disk**. The shared CLI and Make commands are:

```sh
make n810-write-macos-internal INTERNAL_KIT=/path/new-kit N810_DISK=/dev/diskN N810_USB_LOCATION=0x02100000
make n810-install-macos INTERNAL_KIT=/path/new-kit N810_DISK=/dev/diskN N810_USB_LOCATION=0x02100000
```

The first command only checks the selected disk. The second performs the same
attended write, readback, and kernel flash as Setup. After a completed write,
rerun it with the same kit to resume waiting for update mode. The disk number
and USB location are examples; read them again for each installation. The root image
does not contain a touchscreen calibration. First boot collects two matching
taps for each target on that tablet before starting Pocket. The internal image
uses SysV init and D-Bus like the original Debian tablet. It creates a unique
Ed25519 host key before starting SSH; RSA key generation is disabled.

The internal image stages the source-built Fn keyboard map, a debounced lock
slider, LCD brightness keys, and a Power menu with battery status, display
controls, charging thresholds when the kernel exposes them, and confirmed
restart or shutdown. The lock service leaves Power and brightness to the key
service and does not enable the older idle timer. These controls still need a
physical check alongside the GPU desktop on the target tablet.

The RAM-installer actions below remain available for development, but their
physical install has not been accepted. **Build from plan** is an advanced path
for reviewed prebuilt Linux inputs:

1. Prepare the root, kernel package, and GPU build directories described
   below, then save a private plan such as:

   ```json
   {
     "root": "/build/debian/rootfs",
     "kernel_package": "/build/n810-kernel/package",
     "gpu_runtime": "/build/pocket-runtime-release",
     "gpu_module_package": "/build/n810-mbx-module",
     "gpu_mesa_package": "/build/n810-mesa/package",
     "size_mib": 1536
   }
   ```

   Include `"recovery": "/build/n810-ram-installer"` only when preparing the
   separate RAM-installer route. The macOS Maemo USB storage route needs no RAM
   boot image.

2. Enter that plan in the first field and a **new** private kit folder in the
   second. Select **Build from plan**. On Linux, authorize the build in the
   launching terminal first with `sudo -v`; Setup invokes only the builder as
   root, not the Pocket desktop.
3. Setup verifies the root image, installed desktop, and permanent kernel.
   It also verifies the RAM-installer inputs when supplied. It then selects the generated
   `INSTALLATION.json` automatically. Choose **Check files** to rerun the full
   local kit check.
4. Choose **Build host flasher**, then **Detect target**. The read-only check
   accepts exactly one Nokia N810 RX-44 in update mode. On macOS, run `sudo -v`
   in the launching terminal before USB actions.
5. Choose **Boot RAM installer**. This loads its matching kernel and initramfs
   in memory and leaves internal storage unchanged.
6. Choose **Erase and write internal storage**. It checks the RAM installer and
   the unique internal MMC, writes the root image, and verifies its complete
   SHA-256 readback. The kit records a private receipt for that exact root and
   kernel.
7. Return the **same physical tablet** to Nokia update mode, then choose **Flash
   kernel and reboot**. The action rechecks RX-44 and the write receipt before
   flashing the matching kernel. Observe the first boot separately; a successful
   flasher exit does not establish that Pocket started correctly.

The kit contains a local password hash, SSH access material, and personal
configuration. Keep the plan, build root, recovery image, and kit private.

Tab and Shift-Tab move between inputs and actions. Arrow/page/Home/End keys
scroll the steps. Cancel stops local checks, copies, and kit builds. Closing the
app requests cancellation. A cancelled or failed image build may leave a private
partial output folder; remove or rename it before another build.

## Manifest contract, version 1

A manifest and all referenced files live under one local directory. Paths are
relative to that directory; parent traversal and symlinks are refused. Each role
and file path is unique. The app bounds manifest size, file count and file size,
streams SHA-256 instead of loading an image into RAM, and does not execute the
contents of any file.

```json
{
  "version": 1,
  "kind": "n810-system",
  "release": "your-reviewed-release",
  "kernel_release": "the-matching-kernel-release",
  "files": [
    {"role": "system-image", "path": "system.ext4", "bytes": 123, "sha256": "64 lowercase hexadecimal characters"},
    {"role": "kernel", "path": "kernel.bin", "bytes": 123, "sha256": "64 lowercase hexadecimal characters"},
    {"role": "modules", "path": "modules.tar.gz", "bytes": 123, "sha256": "64 lowercase hexadecimal characters"},
    {"role": "boot-guide", "path": "BOOT.txt", "bytes": 123, "sha256": "64 lowercase hexadecimal characters"}
  ]
}
```

The example is a schema illustration, **not a downloadable or valid system kit**.
Use the actual byte sizes and digests of reviewed artifacts.

A `pocket-update` manifest requires `payload`, `installer` and `install-guide`
roles instead. Existing Pocket package tools supply the app payload/installer;
their platform/supervisor prerequisites still apply. Native Setup does not relax
or replace the package installer's checks.

A prepared directory contains the verified files, a self-contained
`INSTALLATION.json`, `SETUP-PLAN.json` with `tablet_installed: false`, and a short
`README.txt` pointing to the included guide. Rechecking the prepared manifest
works without the original source directory.

The shared Make and CLI stages are available without the desktop. From a clean
checkout with Docker running, build a new kit as follows:

```sh
make n810-build-internal SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub" INTERNAL_KIT="$PWD/dist/n810-internal"
make n810-check INTERNAL_KIT="$PWD/dist/n810-internal"
```

The source builder uses a fresh random internal-disk partition ID and a tracked
source snapshot. The build needs a terminal for the local password prompt and
enough free disk space for Linux, Mesa, and the root image. `INTERNAL_PLAN` still
selects reviewed prebuilt input directories when that workflow is needed. The
Setup source-build action supplies the local password through stdin to the same
Make target, so the graphical frontend does not need a terminal. The password
is not passed in process arguments or stored in the Setup session. The kit
install command then uses the new kit folder:

```sh
sudo -v
make n810-install-macos INTERNAL_KIT=/path/new-kit N810_DISK=/dev/diskN N810_USB_LOCATION=0x02100000
# When prompted, return only that N810 to update mode.
```

The build plan's input folders come from the Debian root, kernel, MBX module,
Mesa, and Pocket release-runtime build steps. `build_internal_image.py`
requires those five paths; `recovery` and `size_mib` are optional. The latter
defaults to 1536. The kernel package must
use `PARTUUID=<8 lowercase hex digits>-01`. If included, the RAM installer must
use the matching kernel source. The Debian root must already contain the matching
modules, N810 firmware, Pocket runtime, and staged `pocket-desktop.service`;
the internal image builder selects the SysV boot script for the installed root.
The source-input build path runs inside `containers/internal-image.Dockerfile`.
The five directories named by a private plan remain available for advanced
builds and review.

On macOS, the Install action and `make n810-install-macos` use the Maemo USB
storage route. On Linux, the Install action and `make n810-install` use the
optional RAM-installer route. The latter powers off the new tablet after root
readback; hold Home while powering it on into update mode. On macOS, return the
new tablet to update mode after the whole-disk readback. The permanent kernel
flash then completes.
The USB installer uses `169.254.81.1` to keep its connection separate from an
existing tablet at `192.168.10.1`. The Mac USB Ethernet service must allow a
self-assigned link-local address. A saved root-write receipt allows resuming
without repeating the storage write.

## Remaining acceptance work

The automatic internal writer and kernel-flash gates are implemented and covered
with synthetic local fixtures. A tracked-source container build produced an
internal kit whose expanded root and manifests passed `make n810-check` locally.
The graphical Setup source-build path still needs an interactive host check.
The November 12 install of the v4 kit passed full-disk readback and booted
Debian, but RSA host-key generation timed out in the old SSH drop-in, and the
keyboard driver logged I²C errors. GPU Pocket and input need a physical check
after those startup faults are resolved. Host build and check results do not
establish tablet acceptance.

## Validation

Local tests use synthetic artifacts, not OS images or live devices. They cover
the internal kit manifests, RAM boot arguments, target selection, receipt-gated
kernel flash, build-plan validation, Setup actions, cancellation, navigation and
rendering. They establish host behavior, not a tablet installation.
