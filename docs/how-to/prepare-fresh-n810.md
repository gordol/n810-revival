# Prepare a fresh N810 SD card

This path starts with an N810 that can enter Nokia update mode. It builds a new
Debian Bookworm armel system on a Linux computer or VM and writes that system to
a removable SD card. The owner chooses the local account password during the
build and supplies their own SSH public key. There is no shared password or SSH
host key in the image.

The tablet's stored Maemo image and calibration data are not copied or changed
by the builder. Keep the stock boot path available while testing the new SD
system. [The boot history](../posts/beginnings.md#keeping-a-way-back-to-a-working-kernel)
explains how the project used NOLO and a temporary RAM boot.

## Build the matching kernel

Use a Debian Linux builder or VM with the packages in the [kernel build guide](build-kernel.md).
The SD image has one ext4 partition, so select its first partition for the
kernel's root device:

```sh
python3 platform/kernel/build.py --work /tmp/n810-kernel-sd \
    --root-device /dev/mmcblk0p1 --jobs 4
```

Keep the resulting `package/` directory. The SD builder checks its kernel
release, combined image, root-device setting, and modules. A kernel built for
`/dev/mmcblk0p2` does not match this one-partition layout.

## Build the personalized SD image

On the same Linux builder, install `mmdebstrap`, `qemu-user-static`,
`binfmt-support`, and `e2fsprogs`. Enable the ARM userspace emulator for
cross-architecture chroots. Make or select an SSH public key on your own
computer; use an Ed25519 `.pub` file as the input. From the repository root:

```sh
sudo python3 platform/bootstrap/build_sd.py \
    --work /tmp/n810-fresh-sd \
    --kernel-package /tmp/n810-kernel-sd/package \
    --ssh-key /path/to/id_ed25519.pub
```

The program asks you to set and confirm the `nokia` account's password through
Debian's `passwd` program. It is the local console and `sudo` password. SSH uses
the supplied key and rejects password authentication. The password is not
accepted as a command-line argument and is not written to the build manifest.
The working directory contains a password hash inside the root filesystem and
must be kept private. The SSH host keys and machine identity are generated on
first boot, so each tablet gets its own identity. When run through `sudo`, the
finished kit files are returned to the invoking user's ownership; the staging
root filesystem stays root-owned.

The output contains `n810-sd.img`, `n810-root.ext4`,
`n810-kernel-ramboot.bin`, `n810-modules.tar.gz`, `BOOT.txt`, `BUILD.json`,
and `INSTALLATION.json`. The raw
image has an MBR with one ext4 partition beginning at 1 MiB. By default the
partition is 2 GiB; `--size-mib` can change it. The build creates files on the
Linux computer and never writes a card or a tablet directly. Its manifest
records the image hash, kernel image hash, account name, public-key fingerprint,
and partition layout. The Debian base, security, and updates archives are
included during the build; the package database hash records the exact package
set used. `INSTALLATION.json` lets [Pocket Setup](../pocket/bootstrap.md)
verify and prepare a local kit from these files. Setup does not write the SD card.

## Write and check the card

Insert a card with capacity greater than the image. Identify its whole-disk
device with `lsblk` and unmount its partitions. Writing the image overwrites the
card, so check the device path carefully. For a card that Linux lists as
`/dev/sdX`, the operation is:

```sh
sudo dd if=/tmp/n810-fresh-sd/n810-sd.img of=/dev/sdX bs=4M status=progress conv=fsync
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
sudo 0xFFFF -m kernel:/tmp/n810-fresh-sd/n810-kernel-ramboot.bin -l -b
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
