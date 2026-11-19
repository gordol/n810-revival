# Install an SD A/B system

This experimental installer gives an N810 two replaceable SD operating-system
slots, a shared persistent data partition, and an internal recovery system.
Initial installation erases the selected card and internal 2 GB storage.
It does not replace Nokia's bootloader. Hardware acceptance must be completed
before treating a new build as a release.

## Requirements

Build with Python 3.11 or newer, Git, Make, tar, and a Linux Docker engine.
The container pins its base image, Debian snapshot, Python dependencies, kernel
source, and compiler. No host ARM compiler is required. Give Docker at least
4 GiB RAM (8 GiB recommended) and 30 GiB free storage. Reserve at least 6 GiB
for the default kit; on Docker Desktop reserve 40 GiB host free space for
container growth and output. A card of at least 4 GB is required for the default
1536 MiB slots. Larger cards allocate the remaining space to persistent data.

The card writer supports native Linux and macOS. Windows and BSD can use a
Linux machine with direct access to the card reader and tablet USB device;
native raw-device installation on those hosts is not implemented.

## Build and configure

From a clean, committed source checkout:

```sh
make n810-build-ab SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub" \
  AB_KIT="$PWD/dist/n810-ab" N810_CONFIGURE=1
make n810-check-ab AB_KIT="$PWD/dist/n810-ab"
```

The interactive prompt collects optional Wi-Fi settings, service startup
choices, and a login password. The supplied public key enables SSH. Credentials
are private kit inputs; do not publish the kit or its persistent-data image.
Radio receive, MeshCore, and Reticulum startup are opt-in. Device pairing,
firmware, callsigns, and offline downloads remain separate setup operations.

## Fresh installation

Connect only the intended N810 in Nokia update mode. Put its SD card into the
host reader. Build the host flasher with `make flasher`. On Linux, install the
host iproute2 tools and OpenSSH client. The installer configures only the network
interface on the tablet USB port it identified; disk and network setup require
root privileges or an authorized sudo session.

Check the card using `make n810-write-ab AB_KIT=PATH N810_DISK=DEVICE`.
On macOS DEVICE is a whole `/dev/diskN`; on Linux it is `/dev/sdX` or
`/dev/mmcblkN`. Run the same target with root privileges and `N810_ERASE=1`
to write and read back the card. This is a fresh-install operation, never an
OS-update command.

Insert the verified card into the intended tablet and enter Nokia update mode.
Use `ab_install.py boot-sd --kit PATH --flasher PATH` to load the temporary
bootstrap kernel into RAM. Its filesystem and separately matched modules are
on the card. It starts only a console and key-only USB SSH, not Pocket or radio
services, and does not flash the kernel or write internal storage.

Use `ab_install.py inspect --kit PATH --key SSH_PRIVATE_KEY` to read the internal
MMC identity. The host needs a USB address on the `169.254.0.0/16` subnet; the
installer listens on `169.254.81.1`, using the kit's pinned SD host key.

Write internal recovery using `ab_install.py write-recovery --kit PATH
--key SSH_PRIVATE_KEY --expected-cid CID --erase`. The CID must be the one
reported by the inspection. The writer verifies the isolated SD environment and read-only root, internal
MMC type, capacity, identity, and mounted-state guards, then reads back every
written byte.

Leave the verified SD card inserted and return the same tablet to update mode on the
same USB port. Run `ab_install.py flash-recovery --kit PATH --flasher PATH`.
It requires matching successful SD and recovery receipts and flashes only the
shared kernel. On the next boot, early internal startup waits up to 120 seconds
for the configured card, prepares the selected slot and persistent mounts, and
switches into that root filesystem before starting services. The kernel keeps
running throughout; normal SD boot does not use kexec.

### The USB icon and the A/B boot selection

With the N810 connected to the host over USB, the USB icon appears briefly during
reboot. A host already listening can catch the Nokia bootloader during that
window. Holding the front Swap key (the Home key, marked with two overlapping
rectangles on the N810) at power-on keeps the tablet in update mode so the host
has time to connect.

A host tool could automate this handoff by starting its USB listener first,
requesting a normal reboot of the connected tablet, then identifying the same
tablet as soon as its bootloader appears. If the host misses the window, hold
Swap at the next power-on and retry.

The current A/B installer automates the steps after that handoff. Start the flash
step with the tablet in update mode. The installer checks the install receipts
and USB target, flashes the shared kernel, and requests the following reboot.
Arming the listener and requesting the initial reboot are still open work.

An ordinary A/B update takes a different path. On reboot the tablet starts its
existing kernel, then early startup reads the slot selection from the SD card
and mounts the chosen Debian filesystem. Switching slots needs no host at the
USB icon and writes nothing to kernel flash.

## Storage and updates

| Location | Purpose |
|---|---|
| SD partition 1 | Boot selection and trial-attempt record. |
| SD partition 2 | Read-only OS A and modules matching the flashed kernel. |
| SD partition 3 | Read-only OS B and modules matching the flashed kernel. |
| SD partition 4 | User homes, service state, network settings, and identities. |
| Internal 2 GB | Recovery filesystem, USB SSH, console and repair tools. |
| Internal kernel flash | Shared kernel for SD operation and internal recovery. |

The OS mounts read-only. A persistent `/etc` overlay preserves edits and atomic
file replacements while untouched configuration comes from the selected OS.
The writable `/var` view starts from the selected OS defaults; declared configuration and service-state paths point to the data
partition. User application state and downloads under home survive updates.
Application binaries and package-manager metadata belong to the OS image.
Files manually installed into the OS are not persistent application data.

For an update, copy a matching `UPDATE.json` and `slot.ext4` into a directory on
persistent storage, then run `sudo n810-ab update --bundle DIRECTORY`. The
updater requires the exact flashed kernel build and data schema, refuses mounted
slot targets, verifies the image and full readback,
and selects the inactive slot for up to three trial boots. Reboot normally to
select the trial during early startup. Updates never write the data
partition, card partition table, or flashed kernel. A kernel change is a
separate maintenance operation that must supply matching modules to recovery
and both slots; ordinary OS updates cannot silently replace it.

The health check confirms a boot after persistent mounts, a read-only root,
and a live fault-free GPU desktop are observed across three samples. An
unconfirmed boot consumes one attempt; after three attempts, the next recovery
boot selects the previously confirmed slot. A hard hang still requires a
restart; autonomous watchdog recovery is not established. A five-minute health
timeout leaves the boot unconfirmed rather than interrupting calibration.

Data-schema changes are rejected by the updater. They require a separate,
backed-up migration compatible with the rollback policy. A/B images alone do
not roll back shared database changes.

## Development updates

Application changes can be tested without rebooting or replacing an OS slot.
Stop Pocket through its service so the owner releases the display and GPU,
apply the changed runtime files, then start Pocket again. On the read-only OS,
a temporary bind mount can expose a verified development file from persistent
storage. Keep the original file available underneath for rollback. Native
library changes must also match the graphics release manifest checked by the
launcher.

These temporary mounts disappear at reboot. Save changes in source and rebuild
a kit after the development round, then test a normal slot update and boot.
An in-place application test does not establish that a fresh image boots or
that an update preserves data. Kernel and boot-layout changes need their own
boot tests; ordinary Python, app and compatible library edits do not.

## Recovery

With the card absent, the internal system remains available through USB SSH
and the console after the bounded card-detection wait. A `stay-in-recovery`
file on the card's control partition prevents SD boot. An administrator can
also create `/etc/n810-ab/stay-in-recovery` on internal recovery to bypass
card selection until that file is removed.

From the running SD system, `sudo n810-ab stay-recovery` makes the next normal
reboot stop in recovery. Use `sudo n810-ab resume-sd` there to clear that request,
then `sudo n810-ab boot` to reboot normally and select the SD root. `sudo n810-ab status`
shows the confirmed slot, pending trial, and remaining attempts.

The kit records separate SSH host public keys for recovery and the SD system.
Use `recovery-known-hosts` or `slot-known-hosts` with SSH's
`UserKnownHostsFile` option. The SD identity persists across slot updates.
The temporary SD installer uses that SD host identity and enables key-only root SSH only for the installation session. Normal slot boot retains its normal SSH policy.

The SD system creates a 512 MiB swapfile at `/data/.swapfile` on first boot.
Both OS slots reuse it. Run `cat /proc/swaps` to check the two entries.
Compressed RAM swap on `/dev/zram0` has priority 100. The SD file has priority
10, so Linux uses it for overflow. Internal storage holds recovery.

## Desktop crash recovery

An ordinary app callback failure stops that app and displays an error in its
window. Press **R** to retry it. The desktop log records the app name, operation,
and traceback. This boundary contains Python exceptions; native crashes and
shared GPU failures can still end the desktop process.

After an unexpected desktop exit, the owner restores the display and releases
the GPU before attempting one recovery launch. If cleanup fails, or the recovery
launch also fails, it stays stopped instead of looping. The recovery desktop
starts without restoring saved windows or their background effects. It shows
the failure and the archived log path under `/var/log/n810-pocket-native/`.

In Desktop Recovery, press **A** to restore all saved apps, or select an app
with the arrow keys and press **Enter** to restore just that app. **S** leaves
recovery open so apps can be opened individually from Applications. Recovery
protects the saved desktop from being overwritten. Press **C** only when ready
to keep the current desktop and resume saving it.

The image build includes the Doom engine, bridge library, checksum-pinned
Freedoom data, and their license notices. Games do not download dependencies
at launch. Personal maps, radio identities, and optional third-party Symbian
applications remain separately supplied data.

## Optional offline maps and terrain

Prepare regional data using [the map data guide](build-map-data.md). Keep raw GIS
imports on the build host. The tablet needs the generated `maps/`, geography,
hydrography and selected elevation packs, rather than the raw downloads.

In N810 Setup, open **Storage, Wi-Fi and startup choices**, select **SD A/B**,
and enter the optional offline maps/elevation folder. Use the separate map views
field only when those prepared files live outside that folder. Then choose
**Build kit from source**. These host paths are build inputs; they are not saved
in the tablet's configuration.

For `make n810-build-ab`, set `REFERENCE_DATA` and, if needed, `REFERENCE_MAPS`
to those folders. To invoke the builder directly, add
`--reference-data /absolute/path/to/pocket/data` to
`platform/bootstrap/build_ab_host.py`. If the prepared legacy map views are kept
separately, also pass `--reference-maps /absolute/path/to/maps`. The builder
validates selected elevation tile checksums before building. It seeds the data
partition once, increases its initial size to fit, and leaves the two system
slots free of reference datasets. Reserve the normal build space plus three
times the selected data size for staging and image output.

To install or refresh prepared data on an existing tablet, the installed
`n810-install-reference-data` tool supports `--source DIR --target DIR` and
`--verify DIR`. Run it as `nokia` with the target
`/home/nokia/.local/share/pocket`. It preserves unrelated files and skips unchanged
files. Its `--stream` mode writes a tar stream directly to standard output for
transfer without an intermediate archive; `--plan` validates inputs and reports
file count and size without installing anything. Restart Pocket after changing
the selected data so its existing workers reopen the catalogue.

Prepared reference data can include `map-overview.json`, the 192 by 96 regional
preview used by the overview loader. Importing the original filesystem's map
folder also discovers its checksum-pinned preview beside the legacy runtime.
The host builder mounts that file explicitly into the build container and seeds
it with the reference data, so opening the sidebar does not regenerate regional
terrain. `build_ab_host.py --reference-overview FILE` selects it explicitly.

Map display overviews and LOS use different sampling: rendering may use reduced
levels, while path calculations use selected fine elevation. Missing coverage
is unknown, never evidence of a clear path. A successful software LOS calculation
is not a radio link test.

## Sound

Fresh images include the ALSA utilities, the N810 audio helper, and a boot service
that initializes the speakers at a quiet level. The `nokia` account belongs to
the `audio` group. Both OS slots use modules built for the shared flashed kernel.

After boot, check the sound card and play a short test:

```sh
/usr/local/sbin/n810-audio status
/usr/local/sbin/n810-audio pcm-status
/usr/local/sbin/n810-audio play-test
```

The boot service checks the OMAP2420 McBSP2 device-tree configuration before
enabling the test helper. If streaming is blocked, inspect
`sudo /etc/init.d/n810-audio start` and `dmesg`; do not create an approval file
manually. Older images need the matching kernel/device tree, machine driver,
ALSA tools, and boot service together. Installing only `alsa-utils` does not
repair an incompatible kernel configuration.

To capture five seconds from the internal microphone and listen to it:

```sh
/usr/local/sbin/n810-audio record-test "$HOME/audio-test.wav"
aplay -D hw:N810,0 "$HOME/audio-test.wav"
rm "$HOME/audio-test.wav"
```

Speaker playback and microphone capture are separate checks. ALSA reporting
success does not establish that a speaker is audible or a recording is clear.
