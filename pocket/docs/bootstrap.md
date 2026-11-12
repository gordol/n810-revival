# N810 Setup

Run `make setup` from the Pocket directory to open **N810 Setup**. The setup
screen is also available in the application menu. Start it directly through
either frontend with `make tui EXTRA=--setup` or `make gui EXTRA=--setup`.

N810 Setup builds and checks a private internal-install kit and identifies the
tablet. Its RAM-installer route has not completed a physical installation. The
tested macOS route uses the tablet's stock Maemo USB mass-storage export to
write and read back all 2 GB, then uses native 0xFFFF to flash the matching
kernel. No SD card is involved.

The kit builder runs on a Linux host or VM with administrator access. It packs
an already staged Debian root, matching kernel package, Pocket release runtime,
MBX module, and Mesa build. A RAM-installer output is optional for its separate
development path. The builder does not create those build inputs from an empty
checkout. It stages the GPU desktop for `nokia`.

## Use the app

For a physical installation on macOS, boot stock Maemo on the target and export
its internal USB storage. In Setup, enter the target's `/dev/diskN` whole disk
and USB location in the two Mac fields. Select **Check Mac N810 disk**, then
**Write Mac N810 disk**. The writer checks the disk model, exact 2 GB capacity,
and USB location, writes the image, and reads back the entire disk. Return that
tablet to update mode and select **Flash kernel and reboot**. The same actions
are available through the shared CLI and Make target:

```sh
python3 platform/bootstrap/write_macos_internal.py --kit dist/n810-internal --disk /dev/diskN --usb-location 0x02100000
sudo python3 platform/bootstrap/write_macos_internal.py --kit dist/n810-internal --disk /dev/diskN --usb-location 0x02100000 --write
```

The first command only checks the selected disk. The second erases it and
verifies the entire disk before recording a receipt. The disk number and USB
location are examples; read them again for each installation. The root image
does not contain a touchscreen calibration. First boot collects two matching
taps for each target on that tablet before starting Pocket.

The RAM-installer actions below remain available for development, but their
physical install has not been accepted.

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
   second. Select **Build internal kit**. On Linux, authorize the build in the
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

The shared Make and CLI stages are available without the desktop. `INTERNAL_PLAN`
names the JSON input above, and `INTERNAL_KIT` selects a new output folder:

```sh
sudo -v
sudo make n810-build-internal INTERNAL_PLAN=/path/internal-plan.json INTERNAL_KIT=/path/new-kit
make n810-check INTERNAL_KIT=/path/new-kit
make n810-write-macos-internal INTERNAL_KIT=/path/new-kit N810_DISK=/dev/diskN N810_USB_LOCATION=0x02100000
sudo make n810-write-macos-internal INTERNAL_KIT=/path/new-kit N810_DISK=/dev/diskN N810_USB_LOCATION=0x02100000 N810_ERASE=1
# Return only that N810 to update mode.
make n810-flash-kernel INTERNAL_KIT=/path/new-kit
```

The build plan's input folders come from the Debian root, kernel, MBX module,
Mesa, and Pocket release-runtime build steps. `build_internal_image.py`
requires those five paths; `recovery` and `size_mib` are optional. The latter
defaults to 1536. The kernel package must
use `PARTUUID=<8 lowercase hex digits>-01`. If included, the RAM installer must
use the matching kernel source. The Debian root must already contain the matching
modules, N810 firmware, Pocket runtime, and enabled `pocket-desktop.service`.
These source-input build steps still need to be composed into a fresh-checkout
one-command builder.

The Install action and `make n810-install` use the optional RAM-installer route.
After root readback, they power off the new tablet and wait for you to hold Home
while powering it on into update mode. The permanent kernel flash then completes.
The USB installer uses `169.254.81.1` to keep its connection separate from an
existing tablet at `192.168.10.1`. The Mac USB Ethernet service must allow a
self-assigned link-local address. A saved root-write receipt allows resuming
without repeating the storage write.

## Remaining acceptance work

The automatic internal writer and kernel-flash gates are implemented and covered
with synthetic local fixtures. The remaining acceptance work is to produce the
matching Debian, kernel, firmware, and Pocket inputs from a clean Linux builder,
then run the guided install and verify first boot on a second
N810. No tablet install or first-boot acceptance is implied by host tests.

## Validation

Local tests use synthetic artifacts, not OS images or live devices. They cover
the internal kit manifests, RAM boot arguments, target selection, receipt-gated
kernel flash, build-plan validation, Setup actions, cancellation, navigation and
rendering. They establish host behavior, not a tablet installation.
