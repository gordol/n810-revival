# N810 Setup

Run `make setup` from the Pocket directory to open **N810 Setup** in the portable
Pocket desktop. It is also available in the application menu on a configured
Nokia. Existing `make` / `make n810` commands continue to launch the desktop.

This app prepares **local installation kits**. It does not install Debian,
execute an installer, write a tablet disk, change boot configuration, reboot,
flash, download files or contact services. “Files verified” and “Kit prepared”
are preparation states; neither means a tablet is installed.

## Use the app

1. Obtain a reviewed kit manifest and its files. Verify its publisher and release
   separately: checksums supplied alongside files detect changed bytes, not a
   malicious publisher.
2. Enter the local `INSTALLATION.json` path. Tab moves to the destination field,
   then **Check files**. Press Enter on that action to verify the inputs.
3. Enter a **new** ordinary local folder for the kit. Its parent must exist and
   have enough free space. Existing destinations are refused.
4. Tab to **Prepare local kit**, then press Enter. It checks and copies the files
   on a worker, verifies the copied bytes and includes a preparation receipt.
5. Read the kit's included boot/install guide. Device selection and privileged
   device actions are separate from this app and need their own authorization.

Tab and Shift-Tab move between inputs, Check files, Prepare local kit, Cancel and
Setup steps. Arrow/page/Home/End keys scroll the focused steps. Input keeps
literal shortcut characters. Cancel stops local hashing/copying; closing the app
also requests cancellation. Temporary partial kits are removed on failure.

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

The same model is available without the desktop:

```sh
PYTHONPATH=shell python3 -m n810_bootstrap check /path/INSTALLATION.json
PYTHONPATH=shell python3 -m n810_bootstrap prepare /path/INSTALLATION.json /path/new-kit
```

## Fresh SD-card input

The [fresh N810 SD-card guide](../../docs/how-to/prepare-fresh-n810.md) builds a
Debian Bookworm armel card image with matching kernel modules, an owner-chosen
local password, an owner SSH public key, and fresh first-boot identity. Its
`INSTALLATION.json` can be checked and prepared with this app as an `n810-system`
kit. The app only copies and verifies the generated files. The guide covers
writing the card on a Linux host and a temporary kernel boot.

The SD builder and Setup do **not yet provide a complete accepted tablet
installation**. Device-specific firmware and calibration, a full Pocket console
supervisor installation, and a first boot on another N810 remain to be verified.

The historical partition writer is tied to one prepared image and disk layout;
it is not invoked or presented as a general installer here. The on-device
`pocket-install` tool copies an already installed system to a separately mounted
empty target; it is not a standalone RAM recovery image or host bootstrapping
path.

## Validation

Local tests use synthetic artifacts, not OS images or live devices. They cover
checksum failures, required roles, path traversal, symlinks, duplicate manifest
keys, existing destination preservation, cancellation, changed-source cleanup,
literal text entry, shared navigation, and idle rendering. The real `make setup`
terminal path is exercised separately with a synthetic manifest and new temporary
kit directory. These establish preparation behavior, not tablet installation.
