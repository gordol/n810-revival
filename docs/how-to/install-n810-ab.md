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
host reader. Build the host flasher with `make flasher`.

Use `ab_install.py boot-ram --kit PATH --flasher PATH` to record the tablet USB
port and load the kit's temporary RAM installer. This does not flash storage.
Use `ab_install.py inspect --kit PATH --key SSH_PRIVATE_KEY` to read the internal
MMC identity. The host needs a USB address on the `169.254.0.0/16` subnet; the
RAM installer listens on `169.254.81.1` with the pinned host key in the kit.

Check the card using `make n810-write-ab AB_KIT=PATH N810_DISK=DEVICE`.
On macOS DEVICE is a whole `/dev/diskN`; on Linux it is `/dev/sdX` or
`/dev/mmcblkN`. Run the same target with root privileges and `N810_ERASE=1`
to write and read back the card. This is a fresh-install operation, never an
OS-update command.

Write internal recovery using `ab_install.py write-recovery --kit PATH
--key SSH_PRIVATE_KEY --expected-cid CID --erase`. The CID must be the one
reported by the inspection. The writer verifies the RAM environment, internal
MMC type, capacity, identity, and mounted-state guards, then reads back every
written byte.

Insert the verified SD card and return the same tablet to update mode on the
same USB port. Run `ab_install.py flash-recovery --kit PATH --flasher PATH`.
It requires matching successful SD and recovery receipts and flashes only the
recovery kernel. The next boot enters internal recovery, waits ten seconds,
then loads the selected SD kernel through kexec.

## Storage and updates

| Location | Purpose |
|---|---|
| SD partition 1 | Boot selection and trial-attempt record. |
| SD partition 2 | OS A, including its kernel and matching modules. |
| SD partition 3 | OS B, including its kernel and matching modules. |
| SD partition 4 | User homes, service state, network settings, and identities. |
| Internal 2 GB | Recovery filesystem, USB SSH, console and repair tools. |
| Internal kernel flash | Fixed-root recovery kernel. |

The OS mounts read-only. A persistent `/etc` overlay preserves edits and atomic
file replacements while untouched configuration comes from the selected OS.
The writable `/var` view starts from the selected OS defaults; declared configuration and service-state paths point to the data
partition. User application state and downloads under home survive updates.
Application binaries and package-manager metadata belong to the OS image.
Files manually installed into the OS are not persistent application data.

For an update, copy a matching `UPDATE.json` and `slot.ext4` into a directory on
persistent storage, then run `sudo n810-ab update --bundle DIRECTORY`. The
updater refuses mounted slot targets, verifies the image and full readback,
and selects the inactive slot for up to three trial boots. Reboot normally to
return through recovery and enter the trial. Updates never write the data
partition, card partition table, or flashed recovery kernel.

The health check confirms a boot after persistent mounts, a read-only root,
and a live fault-free GPU desktop are observed across three samples. An
unconfirmed boot consumes one attempt; after three attempts, the next recovery
boot selects the previously confirmed slot. A hard hang still requires a
restart; autonomous watchdog recovery is not established. A five-minute health
timeout leaves the boot unconfirmed rather than interrupting calibration.

Data-schema changes are rejected by the updater. They require a separate,
backed-up migration compatible with the rollback policy. A/B images alone do
not roll back shared database changes.

## Recovery

With the card absent, the internal system remains available through USB SSH
and the console. During its ten-second delay, creating
`/run/n810-stay-in-recovery` prevents SD boot for that session. A
`stay-in-recovery` file on the card's control partition also prevents SD boot.
Charger-only boot remains in recovery's charging mode.

The kit records separate SSH host public keys for recovery and the SD system.
Use `recovery-known-hosts` or `slot-known-hosts` with SSH's
`UserKnownHostsFile` option. The SD identity persists across slot updates.
The RAM installer has its own pinned host key under `ram-installer/`.

The initial implementation retains compressed RAM swap. It does not allocate
all internal storage to disk swap or enable an unmeasured swap policy.
