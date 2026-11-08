# Prepare a fresh N810 SD card

This path starts with an N810 that can enter Nokia update mode. It builds a new
Debian Bookworm armel image inside Docker. A separate step writes the image to
a removable SD card. The owner chooses the local account password during the
build and supplies their own SSH public key. There is no shared password or SSH
host key in the image.

The tablet's stored Maemo image and calibration data are not copied or changed
by the builder. Keep the stock boot path available while testing the new SD
system. [The boot history](../posts/beginnings.md#keeping-a-way-back-to-a-working-kernel)
explains how the project used NOLO and a temporary RAM boot.

## Build the personalized SD image

Use Docker with Linux containers and ARM userspace emulation (Docker Desktop
provides this on macOS), Make, and an interactive terminal. Select your own
Ed25519 SSH public key. From the repository root, run:

```sh
make sd-image SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub"
```

The target installs the Linux build tools in Docker, downloads and builds the
matching kernel for `/dev/mmcblk0p1`, and creates the Debian armel filesystem.
Docker caches the toolchain and kernel layers for later builds. The first run
needs network access and enough Docker disk space for the kernel build and SD
image. Each image build downloads the current Bookworm packages from the base,
security, and updates archives.

The builder asks you to set and confirm the `nokia` account's local console and
`sudo` password. SSH uses the supplied public key. The password goes directly
to Debian's `passwd` prompt inside the container. Keep the resulting image
private because its filesystem contains the password hash and your public key.
SSH host keys and machine identity are generated on first boot.

The finished kit appears in `dist/n810-sd/`. Choose a new output directory for
each build; the target refuses to overwrite an existing directory. For example:

```sh
make sd-image SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub" \
    SD_OUTPUT="$HOME/n810-sd-personal" SD_SIZE_MIB=4096
```

`SD_SIZE_MIB` sets the root partition size (2048 by default, between 1024 and
8191). `SD_USER` selects the local account (default `nokia`), and `SD_JOBS`
controls kernel build parallelism (default 4). The target mounts the selected
public-key file read-only and the output directory writable. Build staging
stays inside the disposable container. The command creates image files; card
writing and tablet booting are separate steps below.

On a Linux Docker host, ARM execution must pass `arch-test armel` inside the
builder container. The target reports an error if the host lacks ARM emulation.

The output contains `n810-sd.img`, `n810-root.ext4`,
`n810-kernel-ramboot.bin`, `n810-modules.tar.gz`, `BOOT.txt`, `BUILD.json`,
and `INSTALLATION.json`. The raw
image has an MBR with one ext4 partition beginning at 1 MiB. By default the
partition is 2 GiB; `SD_SIZE_MIB` can change it. The build creates files on the
Linux computer and never writes a card or a tablet directly. Its manifest
records the image hash, kernel image hash, account name, public-key fingerprint,
and partition layout. The Debian base, security, and updates archives are
included during the build; the package database hash records the exact package
set used. `INSTALLATION.json` lets [Pocket Setup](../pocket/bootstrap.md)
verify and prepare a local kit from these files. Setup does not write the SD card.

## Verified build

On 7 November 2026, the documented Make target completed from a clean source
export on macOS with Docker Desktop. Docker build caching was disabled for that
run. The real Linux 5.15.224 kernel compiled with 199 modules and all 35 external
module symbol checks passing. Its combined image was 2,090,180 bytes.

The generated raw SD image was 2,148,532,224 bytes: a 2 GiB ext4 partition starting
at sector 2048, preceded by the partition table and alignment space. All five
`e2fsck` passes completed successfully. Inspection verified the kit hashes,
partition contents, account settings, supplied fictional public key, empty machine
identity, and first-boot SSH host-key generation. A repeat Docker image build
reused the toolchain and kernel layers. First boot on an N810 remains a separate
hardware acceptance step.

## Write and check the card

Insert a card with capacity greater than the image. Identify its whole-disk
device with `lsblk` and unmount its partitions. Writing the image overwrites the
card, so check the device path carefully. For a card that Linux lists as
`/dev/sdX`, the operation is:

```sh
sudo dd if=dist/n810-sd/n810-sd.img of=/dev/sdX bs=4M status=progress conv=fsync
sync
```

For a card listed as `/dev/mmcblkN`, use that whole-disk path, without a `p1`
suffix. Remove and reinsert the card, then confirm that Linux sees one ext4
partition. You can compare its filesystem UUID with `BUILD.json` and run
`e2fsck -fn` on the unmounted partition. An SD reader may expose the card under
different names on the builder and on the N810; the kernel command line here
expects the N810 to enumerate it as `/dev/mmcblk0p1`.

## First boot and remaining device work

The matching `n810-kernel-ramboot.bin` is beside the SD image. On a Linux
flasher host with `0xFFFF`, put the N810 into update mode, identify it as RX-44,
and load the kernel into RAM:

```sh
sudo 0xFFFF -I
sudo 0xFFFF -m kernel:dist/n810-sd/n810-kernel-ramboot.bin -l -b
```

This uses the [documented RAM-load operation](https://manpages.debian.org/testing/0xffff/0xFFFF.1.en.html)
and omits the NAND flash operation. It is the same boot route used by the
[existing recovery wrapper](https://github.com/gordol/n810-revival/blob/main/pocket/platform/n810/field_kit/pocket-recovery).
The kernel's `/dev/mmcblk0p1` command line is built in. Verify the N810's SD
enumeration, console login, matching
`uname -r` and `/lib/modules`, and USB networking before considering any
permanent flash. The builder does not operate NOLO or install a permanent
kernel. A first-boot run on a second N810 is still needed before this can be
called a complete tablet installer. An ordinary reboot returns to the stored
boot image.

If the N810 shows `usb0` with `192.168.10.1`, connect its USB cable to the
Linux host and find the new host interface with `ip -br link`. Give that
interface the other address on the USB link (replace the placeholder with the
interface you identified):

```sh
sudo ip address add 192.168.10.2/24 dev <HOST_USB_INTERFACE>
sudo ip link set <HOST_USB_INTERFACE> up
ping -c 3 192.168.10.1
```

Before the first SSH connection, read the tablet's new host-key fingerprint
at its console with `ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. Compare
it with the fingerprint SSH shows on the Linux host. Do not accept a different
key or bypass the host-key check. The SSH service creates this key on first
boot; if it has not started, check `systemctl status ssh` on the tablet.

The base system does not include Pocket's device supervisor or private radio
identities. Once USB networking and SSH work, copy a clean repository checkout
from the Linux host and run the portable Pocket desktop on the tablet:

```sh
scp -r pocket nokia@192.168.10.1:~/pocket
ssh nokia@192.168.10.1 'cd pocket && make n810'
```

Run these commands from the repository root and use your SSH key or host alias
as configured. The source runner is separate from the guarded Nokia console
supervisor and native radio package. Those components still need a reviewed
first-install path. Wi-Fi and other hardware may need device-specific firmware
and calibration. Do not publish those owner-supplied files or reuse another
tablet's credentials.
