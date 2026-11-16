# N810 Setup

Run `make setup` from the Pocket directory to open **N810 Setup**. The setup
screen is also available in the application menu. Start it directly through
either frontend with `make tui EXTRA=--setup` or `make gui EXTRA=--setup`.

N810 Setup builds complete Debian/Pocket kits for internal storage or a removable
SD card. Building a kit, writing storage, and flashing a tablet are separate
operations. A successful build does not establish first-boot hardware acceptance.

## Host requirements and platform support

The build toolchain lives in `containers/internal-image.Dockerfile`. You do not
need an ARM compiler installed on your laptop. The kernel builder checks GCC
**12.2.0** and binutils **2.40**; installing GCC 14 on the host does not change
that selection. Kernel and modules must come from the same kit.

For either complete kit, use:

- A clean, committed Git checkout, Python **3.11 or newer**, GNU Make, Bash,
  and tar with `--null`/`-T` support. Run the commands from the repository root.
- Docker with a running **Linux** engine, BuildKit, and working ARM Linux
  `binfmt` emulation for the armel chroot. The build runs ARM programs as well
  as cross-compiling them. Docker Desktop supplies emulation on our macOS host;
  a Linux host must provide it too.
- Network access for the first build, space for compiler/kernel/Mesa layers and
  the Debian root, and a new output directory below an existing parent directory.
- An Ed25519 SSH **public** key. The private key stays on your computer.

The base container digest, kernel toolchain, source revisions and archive hashes
are pinned. Debian build and root packages come from the **2026-11-15 UTC
snapshot**, with repository signatures still checked. Python build tools and
optional-service wheels are version/hash locked, including transitive build-tool
dependencies. Kits include `debian.sources.list`, `builder-requirements.lock`,
`BUILDER-PACKAGES.tsv` and `ROOT-PACKAGES.tsv`. Updating dependencies is an explicit
source change followed by rebuilding both kits. Personalized disk IDs, filesystem
UUIDs and account inputs mean two kits need not be byte-identical.

Reserve **30 GiB free inside Docker** and **5 GiB free in the output filesystem**
for a default 1536 MiB kit. Reserve **8 GiB of output space** to retain both kits
and their build logs. With Docker Desktop, reserve **40 GiB free on the host**
for virtual-disk growth and outputs; if Docker's virtual disk is on another
volume, that volume also needs room to grow. Larger roots require at least twice
the selected root size plus 2 GiB output space. Docker needs at least **4 GiB RAM**;
**8 GiB and four CPU cores** are recommended. The source checkout is about 55 MiB,
excluding Git history, build outputs and downloaded offline data. The Make targets
check output and engine space before compilation. Build caches accumulate across
source revisions; these figures are free-space allowances for the requested build,
not a maximum lifetime cache size.

| Host | Complete kit build | Storage and USB installation |
|---|---|---|
| macOS | Docker Linux builder; exercised on Apple Silicon | Native internal writer and SD writer; native NOLO flasher. The new complete SD route still needs physical acceptance. |
| Linux | Same pinned Docker builder; requires ARM binfmt emulation | Guarded internal/SD writer and native flasher. Readback and port-bound receipts are required; physical tablet acceptance is separate. |
| Windows | No native PowerShell build path. A Linux VM/WSL environment is a candidate, not a validated recipe. | No supported native writer/flasher integration. USB and disk access require separate host support. |
| BSD | No native full-kit build path. A Linux VM is a candidate, not a validated recipe. | No supported guarded writer/flasher integration. |

A remote Docker engine is not interchangeable with a local one here: the build
bind-mounts your public key and output folder from the engine's host. Do not
assume a container can access a laptop's USB ports or card reader.

Building a kit does **not** require the Pocket graphical frontend or a host C
compiler. Running Pocket's terminal frontend requires Python and Make. Building
its graphical frontend additionally requires a C compiler, Python development
headers, SDL2 and OpenGL; see [the graphics guide](graphics.md). It renders on
the computer running that frontend. The installed N810 uses its own native
framebuffer/MBX graphics path, independently of a laptop.

Flashing requires a native host tool and USB access. For the macOS route, install
the command-line compiler tools and flasher dependencies, then prepare the
restricted helper from the repository root:

```sh
brew install libusb-compat pkg-config
make flasher-helper-prepare
sudo /bin/sh dist/flasher-helper/install.sh
```

The helper installation accesses no tablet. Linux native flasher builds need a
C compiler, Make, pkg-config and libusb development files. Neither host flasher
uses the kernel's pinned cross-compiler.

## Build a complete kit

**Build kit from source** in Setup runs `make n810-build-internal` with Docker.
A fresh clone has no private installation kit. Setup suggests an output folder
and guides you to **Build kit from source**. Select your Ed25519 public key file.
Existing kits are discovered under `dist/`; Setup initially selects the most
recently written manifest, or restores a saved selection that still exists.
Use **Choose another local kit** to cycle through other discovered kits, then
**Check files** to verify the selected kit. The installation guide is in **? Help**.
The console account
defaults to user `nokia`, password `nokia`; the password field accepts an override.
The password is hidden and cleared from the form
when the build starts. The Make target builds the kernel, MBX module, Mesa,
Pocket release runtime, and Debian root from tracked source, then packs and
verifies the internal kit. It does not access a tablet. A RAM-installer output
is optional for its separate development path.

Create the output parent with `mkdir -p dist` in a fresh checkout. The shared
source build command is:

```sh
make n810-build-internal SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub" \
    INTERNAL_KIT="$PWD/dist/n810-internal"
```

The commands below build on macOS or Linux. Windows/BSD users need a Linux environment with explicit storage/USB access for installation; native Windows/BSD writers are not provided.

Both build targets print a log filename under `dist/build-logs/`. The log retains
Docker compilation and the subsequent root-filesystem assembly output, including
the exit status. Set `N810_BUILD_LOG=/absolute/path/new.log` to select a new log
file. A Docker image build completing is only the first stage; wait for the kit
export and successful exit. Inspect the last error in that log before retrying.
Logs are private files; review them before sharing.

Use your own public key. If you need a new SSH login key, create one on your
computer with `ssh-keygen -t ed25519` first. Only the public key enters the image.
Each tablet generates its own SSH server host key at first boot. Change its
console password later with `passwd`, or supply an override through Setup or
`INTERNAL_PASSWORD_STDIN=1` when building. Firmware is acquired and checked by
the build tools; no calibration or configuration from another tablet is needed.

## Choose internal storage or an SD card

Both targets build the complete lean Debian/Pocket system, native GPU runtime,
matching kernel/modules, system helpers and optional radio runtimes. They do
not copy the OG home, identities or offline datasets. In laptop Setup, open
**Storage, Wi-Fi and startup choices**, select **internal MMC** or **SD card**,
then choose **Build kit from source** with a new output folder.

The shared kit format records `storage_target`. Internal writes reject SD kits;
the removable-card writer rejects internal kits. Each kit has a new MBR disk ID
and a matching kernel that forces `root=PARTUUID=<disk-id>-01`. Both layouts
use one ext4 root partition beginning at 1 MiB. This is a new matched kit, not
an unchanged OG kernel expecting the OG card's partition-2 identity. Keep each
kernel with its own prepared root/card; do not duplicate disk identities among
attached media. The root expands within that partition at first boot.

For SD, build from the repository root:

```sh
make n810-build-sd SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub" \
    SD_KIT="$PWD/dist/n810-sd-new"
```

Internal builds continue to use `make n810-build-internal`. Both accept the
private Wi-Fi/startup input options described below. SD root image sizes may be
1024–8191 MiB through `INTERNAL_SIZE_MIB`; internal roots remain limited to
1024–1900 MiB. The prepared image must fit the selected card. The default 1536 MiB root needs
a card of at least **2 GB**; larger custom roots need the selected root size plus
1 MiB for the partition offset. Offline maps and other data need additional space.

### Prepare an SD card on macOS

Insert the card in the laptop reader. Identify its whole disk with
`diskutil list`; do not reuse a disk number from an earlier connection. The
writer requires a physical, writable disk marked as removable by macOS. The
USB location below is the **new N810's update-mode port**, not the card reader.
It pins the subsequent kernel flash to that port.

```sh
# Check the kit and card without writing anything.
make n810-write-sd SD_KIT="$PWD/dist/n810-sd-new" \
    N810_DISK=/dev/diskN N810_USB_LOCATION=0x02100000

# Explicitly erase the partition table and write the new root image.
sudo python3 platform/bootstrap/write_sd_card.py \
    --kit "$PWD/dist/n810-sd-new" --disk /dev/diskN \
    --usb-location 0x02100000 --write
```

The writer rechecks media identity after unmounting, writes the MBR and root,
and verifies the complete written region by readback. It does not zero the
unused remainder of a large card or claim secure erasure of prior card data.
A failed readback produces no flash receipt. A successful write saves a
kit-specific receipt and ejects the card. The writer currently uses macOS
`diskutil`; the source image builder remains Linux/Docker.

Insert the verified card into the new N810, put that tablet in Nokia update
mode, and flash the matching kernel:

```sh
sudo -v
make n810-flash-kernel INTERNAL_KIT="$PWD/dist/n810-sd-new"
```

This uses the existing shared flash command; `INTERNAL_KIT` is its retained
Make variable name for either storage target. It checks the SD write receipt,
kernel hash and pinned tablet USB location. The N810 internal MMC is not
written by this route. A card-reader installation does not require a Maemo
mass-storage export. Observe first boot, keyboard, display and radio behavior
separately from a successful write or flash command.

In Pocket Setup, **Check target disk** performs the card check; **Write target
disk** or **Install Debian + Pocket** writes and verifies the SD card. Then
insert it into the tablet and use **Flash kernel** separately. Internal mode
retains the existing attended Maemo-write/return-to-update-mode sequence.

## Install on Linux

Build `0xFFFF` on the Linux host with `make flasher` (a C compiler, Make,
`pkg-config` and libusb development files are required). Building the kit in
Docker does not give the container access to your USB ports; run installation
commands on the native Linux host.

First identify the target tablet in Nokia update mode:

```sh
sudo -v
make n810-identify
```

The result includes `usb_port`, for example `1-2.3`. Keep the tablet on that
physical port, including the same hub connection. Only one Nokia USB device may
be connected when identifying or flashing. For internal installation, return the
tablet to stock Maemo and export internal storage over USB. For SD installation,
insert the card in the host reader instead. Identify the whole disk using
`lsblk -o NAME,SIZE,MODEL,TRAN,RM,MOUNTPOINTS`. Unmount its mounted partitions and
disable any swap on that selected disk before proceeding.

Set the kit, current whole-disk path and tablet port explicitly:

```sh
make n810-write-linux INTERNAL_KIT="$PWD/dist/n810-internal-new" \
    N810_DISK=/dev/sdX N810_USB_PORT=1-2.3

sudo python3 platform/bootstrap/linux_storage.py \
    --kit "$PWD/dist/n810-internal-new" --disk /dev/sdX --usb-port 1-2.3 --write
```

For SD, use your SD kit directory instead. Native card slots may use
`/dev/mmcblkN`. The writer refuses mounted/claimed disks, partitions, host fixed
storage and mismatched N810 identity. It takes an exclusive block-device handle,
checks identity again, writes the partition table and root, flushes Linux block
buffers, and reads back the written region. It does not securely erase unused
sectors. It saves a receipt only after successful verification.

Disconnect the exported storage after completion. Insert the SD card if applicable
and put the target tablet in update mode on the recorded port:

```sh
sudo -v
make n810-flash-kernel INTERNAL_KIT="$PWD/dist/n810-internal-new"
```

Flashing requires a matching write receipt and the same USB topology port.
Changing hosts or ports invalidates that binding; do not edit the receipt to
bypass it. In laptop Pocket Setup, the disk check/write controls use this same
Linux writer. **Install** writes and verifies storage; **Flash kernel** is a
separate explicit step after returning the tablet to update mode.

## Provision another N810 from an N810

New images include `n810-provision`, the Linux writer, and the verified ARM
flasher with its provenance. Supply an already-built complete kit on storage
accessible to the provisioning tablet. The provisioning tablet needs space for
the compressed kit (currently about 200 MB; allow **512 MiB** for the default kit)
and logs. It streams decompression during writing, so it does not need a second
uncompressed 1.5 GiB copy. Larger/custom kits require their actual compressed size
plus headroom. Docker and a compiler are not required on that tablet.

The provisioning tablet must be in USB **host** mode, with a suitable OTG host
connection and adequate power for the other device/card reader. Software alone
cannot supply USB power or change a peripheral-only cable into a host cable.
Run provisioning from the tablet console or over Wi-Fi: its USB port will be
occupied as the host connection, so USB gadget networking cannot remain the
control connection. The USB host, power and two-tablet flashing combination still
needs a physical test. Keep an independent recovery route available.

```sh
n810-provision check --kit /path/to/kit
sudo n810-provision identify
sudo n810-provision write --kit /path/to/kit --disk /dev/sdX --usb-port 1-1
# After inspecting the selected disk, explicitly write it:
sudo n810-provision write --kit /path/to/kit --disk /dev/sdX --usb-port 1-1 --erase
# Return the target to update mode on the same port:
sudo n810-provision flash --kit /path/to/kit
```

The host tablet's own mounted root is rejected by the disk checks. Its internal
MMC is not a removable SD card and is rejected as an SD target. Verify host-mode enumeration on the provisioning tablet before attempting any
write to a second tablet.

### Validate the Linux block writer without a tablet

After building the Docker image, this opt-in test allocates a disposable 16 MiB
loop device, checks mounted-disk exclusion, and exercises real block writes,
Linux buffer flushing and readback. It detaches its fixture on completion.
Run it in a disposable Linux VM/container, not against a real card:

```sh
docker run --rm --privileged -e N810_LOOP_TEST=1 \
    --mount "type=bind,src=$PWD,dst=/validation,readonly" \
    n810-internal-builder:local python3 -m unittest discover \
    -s /validation/platform/bootstrap -p test_linux_block_device.py
```

This tests Linux block I/O; it does not replace physical N810 USB/flashing checks.

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

The kernel builder includes the recovered 330–480 MHz CPU profile and records
its source patch hash. The default powersave governor starts at 330 MHz; the guarded CPU policy can select up to 480 MHz. The kernel,
modules, Mesa and native pixel Pocket runtime are built together. This source
profile still requires first-boot acceptance on the destination tablet.

Keep other tablets out of update mode. Disk numbers can change after ejection
or reconnection; read `diskutil list` again instead of reusing an old number.
The writer also requires the selected tablet's exact USB location. A failed
identity check writes nothing. If NOLO reports the kernel flash complete but
its reboot request fails, inspect the saved operation log and receipt before
doing anything else; repeating the flash is not a connectivity check.

This initial installation path starts with working stock Maemo and its USB
storage export. It does not need another tablet's filesystem, calibration,
SSH keys, or private development directories. Reinstallation after replacing
the kernel needs a recovery boot first. Preserve an owner-supplied stock Maemo
kernel and its provenance for that purpose; it is a separate recovery input,
not part of the source-built Debian kit. The guided automatic Maemo recovery
step has not been completed.

The internal image stages the source-built Fn keyboard map, a debounced lock
slider, LCD brightness keys, and a Power menu with battery status, display
controls, charging thresholds when the kernel exposes them, and confirmed
restart or shutdown. The wake service owns the slider, idle dim/off and keyboard wake. Displayd owns
Power and brightness; the duplicate display-keys service is disabled. Charger
boot detection runs before touch setup and the graphical desktop. These controls still need a
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

## Wi-Fi and optional services

Before **Build kit from source**, open **Wi-Fi and startup choices**. Leave the
SSID blank to configure networking later, or enter the access point SSID,
passphrase and two-letter country. This joins an existing Wi-Fi access point;
it does not make the N810 host an access point. The password is masked, passed
through stdin, cleared when the build starts and omitted from saved UI sessions
and public build receipts. The root image contains a protected WPA key and must
remain private.

**APRS receive**, **HTIT / MeshCore**, and **Reticulum** default off. Their code,
locked dependencies and native microReticulum library are installed regardless
of startup choices. An enabled service still needs this tablet's own endpoint
configuration. Pairing, firmware flashing and radio transmission are separate
explicit actions. The image never copies another tablet's identities or bonds.

The Make interface accepts the same choices with `INTERNAL_SETUP_STDIN=1` and
one JSON line on stdin. For example, to opt into APRS receive after configuring
the receiver on the tablet:

```sh
printf '%s\n' '{"startup":{"receive":true}}' | make n810-build-internal \
    SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub" \
    INTERNAL_KIT="$PWD/dist/n810-internal-new" INTERNAL_SETUP_STDIN=1
```

A private profile may also contain
`"wifi":{"ssid":"network","passphrase":"...","country":"US"}`. Use the masked
UI or a protected input file for credentials. When `INTERNAL_PASSWORD_STDIN=1`
is also set, supply the console password on the first line and the JSON profile
on the second line. Source changes must be committed before building an
identified kit; use a new output folder for each build.

## Recreate system behavior without copying the old home

The source build installs system services and their helper dependencies. It does
not import another tablet's home, identities, Bluetooth bonds, shell history or
offline data. Keep those outside the base installation. Maps and identity
import remain optional tools, not prerequisites for installing Pocket.

Power and brightness use the wake helper. Its Power menu opens on a temporary
console and returns to the native Pocket session when closed. The menu includes
quiet charging, airplane mode, CPU policy and charging controls. The installer
stages the associated fixed helpers and bounded privilege policies. A dependency
check rejects missing commands, privilege groups or duplicate key-event owners
before generating the root image.

## Finish setup on the new tablet

On an installed N810, **N810 Setup** opens Device Setup rather than the laptop
image builder. Finish these steps after the base installation:

1. In **Wi-Fi**, enter the network details and choose **Save and join Wi-Fi**.
   USB networking also works without Wi-Fi. Wi-Fi changes use a restricted
   helper; passwords travel over stdin.
2. Pair the UV-Pro and HTIT with this tablet. From its terminal, run
   `sudo n810-bluetooth on`, `sudo n810-bluetooth discover 20`, then
   `sudo n810-bluetooth pair ADDRESS`. Confirm the PIN in the terminal and on
   the peripheral when required. Use the discovered address for this device.
3. In **Radio**, enter the station callsign and explicit endpoints, then choose
   **Save radio profiles**. The UV-Pro uses its Bluetooth address. A serial
   MeshCore peripheral uses `/dev/ttyUSB0`; a shared HTIT companion uses its
   configured `htit://...` endpoint. An RNode uses its serial path or a configured
   `hub://...` LoRa service. Enter the allowed RNode transmit-power bounds for
   your hardware; saving the profile does not select a transmit frequency or
   start transmission. Configure any RFCOMM binding for this tablet rather
   than reusing another tablet's controller address. These fields save Pocket's
   profiles; they do not program the UV-Pro's own callsign, channels or RF policy.
   For a Classic Bluetooth RNode, pair first, then save this tablet's addresses
   with the fixed setup helper. These are fictional example addresses:

   ```sh
   printf '%s\n' '{"controller":"02:00:00:00:00:01","address":"02:00:00:00:00:02"}' | sudo n810-rnode-configure --stdin
   ```

   Replace `controller` with the address reported by `bluetoothctl show` on the
   new tablet and `address` with its paired RNode. This saves a protected endpoint
   policy; it does not pair, bind or open a radio. Choose `/dev/rfcomm0` in Device
   Setup and save the radio profile. Connections then invokes the no-argument
   preparation helper, which verifies the controller, bond and unused mapping
   before a radio connection. USB and shared-hub endpoints skip this helper.
4. Select **Startup** choices and save. Saving changes the next startup; it does
   not stop an existing service. **Start APRS now** is a separate action.
   Use **Connections** to start or attach Reticulum and MeshCore explicitly,
   and their radio controls to connect the selected peripheral. The native
   Reticulum owner starts idle; starting the owner alone does not open RF.
5. Use **Identity** to import a 64-byte Reticulum private identity before
   connecting a new local session, or export the generated identity to a new
   private file. Import requires stopped owners and preserves an existing
   identity. Disable startup and reboot before restoring when an owner is
   still active. Local identity state lives in
   `~/.local/state/pocket-reticulum/identity`; external executor identities
   remain on their own board. Keep backups private.
6. Build and flash HTIT firmware separately on the laptop, following the
   [HTIT build guide](../../docs/how-to/build-htit.md). Choose hub firmware for
   multiplexed companion services or executor firmware for onboard
   microReticulum. Preserve the generated private PIN header. From the built
   source directory, PlatformIO's explicit upload action is
   `pio run -e ENVIRONMENT -t upload --upload-port SERIAL_PORT`; use the
   environment from that build and verify the selected board and serial port.
   The N810 installer never flashes a connected HTIT automatically.
7. Prepare regional maps and terrain on the laptop using **Offline Data**.
   Run `make maps-deps` once from `pocket/`, enter your bounds, matching OSM
   extract URL and output folder, then choose **Plan**. Planning does not
   download. **Download and build** performs the existing geography and fine
   elevation pipeline and reuses completed inputs. Closing requests cancellation.
   See [map data](map-data.md) for the CLI and storage details. Legacy Map Library
   resources are separate compatibility inputs, not the regional acquisition
   path.
8. Transfer prepared runtime data into `/usr/share/pocket/data` on the new
   tablet, or set `POCKET_DATA_ROOT` for its launcher. Keep raw OSM/GeoTIFF
   downloads on the laptop. Include the selected `elevation.json` catalogue and
   its referenced fine/overview packs. The internal MMC is only 2 GB, so select
   a small area or wait for SD storage before copying large collections.
9. In **ULS Lookup**, explicitly choose **Download/update FCC data** if desired.
   The base image does not download the national database or regional map data.
   Confirm storage first. **Connections** reports owner and radio status;
   verify receive and an intended peer exchange separately.

The shared receive code is installed under `/usr/local/lib/n810-radio`, with
state under `~/.local/state/n810-aprs`. It no longer depends on loose Python
scripts in `/home/nokia`. Startup preferences live in
`~/.config/pocket/services.json`; radio profiles and Wi-Fi credentials remain
private. Reticulum and HTIT runtimes live in `/opt/n810-mesh` and
`/opt/pocket-htit`. Advanced build plans must supply those prepared runtimes as
well as the verified desktop and native library.

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
with synthetic local fixtures. A tracked-source container build produced a v5
internal kit whose expanded root, manifest, SysV packages, and startup links
passed local checks.
The graphical Setup source-build path still needs an interactive host check.
The November 12 install of the v4 kit passed full-disk readback and booted
Debian, but RSA host-key generation timed out in the old SSH drop-in, and the
keyboard driver logged I²C errors. The v5 kit has not been installed; GPU
Pocket, SSH, and input still need a physical check on the new tablet. Host build
and check results do not establish tablet acceptance.

## Validation

Local tests use synthetic artifacts, not OS images or live devices. They cover
the internal kit manifests, RAM boot arguments, target selection, receipt-gated
kernel flash, build-plan validation, Setup actions, cancellation, navigation and
rendering. They establish host behavior, not a tablet installation.
