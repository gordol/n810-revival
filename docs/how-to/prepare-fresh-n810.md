# Prepare a fresh N810 SD card

Build a personalized Debian armel SD image, write it to a removable card, and
boot the N810 temporarily with the matching kernel. Keep the stock boot route
available during initial checks.

## Before you begin

Have the following ready:

- An N810 (RX-44) and its power supply.
- Docker with Linux containers and ARM emulation, Make, and a repository checkout.
  Docker Desktop supplies ARM emulation on macOS.
- Your Ed25519 SSH public key (`id_ed25519.pub`).
- A removable SD card larger than the selected image and a card reader.
- A Linux host with `0xFFFF` for the temporary tablet boot.

The default image uses a 2 GiB root partition. The first build downloads the
kernel source, compiler packages and Debian packages. Allow enough space in
Docker for those inputs and the generated image.

## 1. Build the image

From the repository root, run:

```sh
make sd-image SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub"
```

When prompted, enter and confirm a password for the `nokia` account. Use this
password for console login and `sudo`. SSH uses your supplied public key.

Wait for the export completion message. The kit is in `dist/n810-sd/`:

- `n810-sd.img`: the complete card image.
- `n810-kernel-ramboot.bin`: the matching kernel for temporary boot.
- `n810-root.ext4` and `n810-modules.tar.gz`: the filesystem and modules.
- `BUILD.json`, `INSTALLATION.json`, and `BOOT.txt`: checksums and kit metadata.

Keep this directory private; the filesystem contains your account's password
hash. Choose a new directory for subsequent builds. For a 4 GiB root partition:

```sh
make sd-image SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub" \
    SD_OUTPUT="$HOME/n810-sd-personal" SD_SIZE_MIB=4096
```

`SD_SIZE_MIB` accepts 1024 through 8191. `SD_USER` changes the account name and
`SD_JOBS` sets kernel compilation parallelism. Docker reuses matching compiler
and kernel layers. Use the chosen output directory in the following commands.

## 2. Write the card

On the Linux host, insert the card and identify its whole-disk path with
`lsblk`. Unmount its partitions. Confirm the disk path before writing; this
operation overwrites the card. For a card identified as `/dev/sdX`:

```sh
sudo dd if=dist/n810-sd/n810-sd.img of=/dev/sdX bs=4M status=progress conv=fsync
sync
```

Reinsert the card. Confirm that it has one ext4 partition, then compare its UUID
with `BUILD.json`. Run `sudo e2fsck -fn /dev/sdX1` on the unmounted partition.
A card exposed as `/dev/mmcblkN` uses that whole-disk name for writing and
`/dev/mmcblkNp1` for the partition check.

## 3. Boot the matching kernel

Insert the card into the N810 and connect it to the Linux flasher host.
Put the tablet into Nokia update mode. Check that `0xFFFF` identifies an RX-44,
then load the supplied kernel into RAM:

```sh
sudo 0xFFFF -I
sudo 0xFFFF -m kernel:dist/n810-sd/n810-kernel-ramboot.bin -l -b
```

This is the documented [temporary RAM-load operation](https://manpages.debian.org/testing/0xffff/0xFFFF.1.en.html).
The kernel expects the SD root at `/dev/mmcblk0p1`. If boot stops at root mounting,
check the tablet's card enumeration and the matching kernel package before
proceeding.

## 4. Set up touch and log in

First boot opens touchscreen setup on the tablet's console. If an existing
Maemo `pointercal` file is available, move the stylus over the preview targets
press Enter to finish the preview, and confirm whether the pointer follows it accurately. Otherwise, press Enter
and tap the five white crosses as they appear. The tool checks the fitted
mapping and saves a Pocket calibration profile.

You can type `skip` to continue to login and calibrate later. Log in as `nokia`
with the password chosen during the build. To repeat setup:

```sh
sudo n810-setup-touch
```

To collect a fresh calibration, run `sudo n810-setup-touch --recalibrate` from
the tablet's text console. The tool temporarily owns the framebuffer; close
any graphical desktop before running it. After login, check `uname -r` and
`ls /lib/modules` against the kernel release in `BUILD.json`.

The [first-boot input reference](../reference/first-boot-inputs.md) explains
which Maemo settings can be reused, where the calibration profile is saved,
and the remaining wireless firmware and device checks.

## 5. Connect over USB SSH

If the tablet exposes `usb0` at `192.168.10.1`, identify the corresponding Linux
host interface with `ip -br link`. Configure that interface:

```sh
sudo ip address add 192.168.10.2/24 dev <HOST_USB_INTERFACE>
sudo ip link set <HOST_USB_INTERFACE> up
ping -c 3 192.168.10.1
```

At the tablet console, run
`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`. Compare that fingerprint with
the first SSH connection prompt on the host, then connect:

```sh
ssh nokia@192.168.10.1
```

The first boot of this generic image still needs attended tablet acceptance.
Use the [status page](../status.md) to check the current installation coverage.
