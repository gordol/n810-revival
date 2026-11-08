# N810 radio firmware sources

The SD builder acquires two radio images outside the project source tree. It
checks their complete SHA-256 values before installation and records the source,
size, hash and license-review status in the generated `FIRMWARE.json` and
`BUILD.json`.

| Installed file | Pinned input | Acquisition source |
|---|---|---|
| `/usr/lib/firmware/3826.arm` | STLC4560 firmware `2.13.0.0.a.22.8` | [Prism54 firmware archive](https://daemonizer.de/prism54/prism54-fw/), linked by [Linux Wireless](https://wireless.docs.kernel.org/en/latest/en/users/drivers/p54.html). Its hash matches the project's working live-Maemo copy. |
| `/usr/lib/firmware/nokia/bc4fw.bin` | CSR BlueCore4 image, 2034 bytes | [OpenWrt commit dbc2e084](https://github.com/openwrt/openwrt/commit/dbc2e08418a5f6dfd911f32ea9e0c5d69408142b), which added the N810 Bluetooth firmware. |

The exact URLs and SHA-256 values are in
[`platform/bootstrap/firmware.lock.json`](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/firmware.lock.json).
OpenWrt's [Prism54 recipe](https://github.com/openwrt/openwrt/blob/main/package/firmware/prism54-firmware/Makefile)
uses the same archive but selects the older `a.13.14` SPI image. This builder
selects the `a.22.8` image used in the project's later working installation.

## License findings

On 7 November 2026, review found public distribution records for both blobs but
no blob-specific vendor grant establishing the project's redistribution rights.
The archive's firmware-header descriptions identify the Wi-Fi version. The
OpenWrt addition identifies the Bluetooth file and its history. GPL notices on
the download recipe, Linux driver or repository establish terms for those
sources; this review found no separate grant attached to the firmware files.

Debian distributes many firmware packages through
[`non-free-firmware`](https://wiki.debian.org/Firmware/). Neither exact filename
appeared in the Bookworm `non-free-firmware` all-architecture file index checked
during this review. This builder therefore acquires them directly from the
recorded sources or from the owner's backup.

The project ships the acquisition code and hashes. Downloaded or extracted blobs
stay in the owner's Docker cache and generated image. Publishing or selling an
image containing them needs the relevant firmware permissions established
separately. The lock file records that unresolved status explicitly.

## Owner-supplied backups

`MAEMO_BACKUP` mounts an owner's existing backup directory read-only. The
acquisition code checks exported firmware files and data-only `initfs.jffs2`
and `rootfs.jffs2` partition images. It selects only the required file paths,
checks JFFS2 node/data CRCs and fragment coverage, and validates the reconstructed
firmware against the pinned complete image. It leaves the original backup intact.

The directory can instead contain extracted `3826.arm` and `bc4fw.bin` files.
The usual Maemo initfs path is `/usr/lib/hotplug/firmware/`. A kernel-only backup
contains neither root filesystem file. Raw NAND dumps with spare/OOB bytes,
whole-disk images and Nokia FIASCO update containers require conversion to the
documented partition format before use here.

Firmware files from older or damaged backups may fail the selected-image hash
check. The error identifies that mismatch. Supply a complete matching file or
use the default verified public download path. Internal CAL blocks, account
files, saved networks and messages are outside this firmware extraction step.

## Calibration and startup

The selected kernel has `CONFIG_P54_SPI_DEFAULT_EEPROM=y`: p54 uses a compiled
fallback EEPROM image and accepts an optional `3826.eeprom` override. The firmware
blob is a separate input. The builder uses the kernel's fallback and does not
copy an unvalidated CAL record into an EEPROM file.

Bluetooth address provisioning uses the existing `n810-bluetooth-address`
helper. It creates one stable locally administered address on the tablet and
saves it privately. The BlueZ service requires that provisioning step before
opening the controller. Wi-Fi uses the existing `n810-wifi` service after the
owner creates its network configuration.

The [SD-card how-to](../how-to/prepare-fresh-n810.md) gives the commands.
Container validation establishes acquisition, extraction, packaging and
configuration. Radio operation still requires attended device testing.

## Docker verification

On 7 November 2026, both complete Make builds passed: the default path downloaded
both pinned images into an empty cache, and the backup path extracted them from
a generated JFFS2 partition using an empty cache with firmware downloads disabled.
That partition contained the public firmware copies and fictional test metadata;
private tablet backups were outside this verification.

Fifteen bootstrap tests passed, including the real Maemo directory layout,
corrupt fragments, invalid hashes, symlink escapes, cache reuse, and offline
failure behavior. Inspection of both generated filesystems verified the
installed firmware hashes, BlueZ address-provisioning dependency, and Wi-Fi
service/tools. The final image also passed its module-loading configuration,
kit-hash and filesystem checks.
