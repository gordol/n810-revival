# N810 first-boot inputs

The SD image supplies Debian, the maintained kernel and modules, and touchscreen
setup tools. Its first boot creates SSH host keys and a machine identity.
The owner supplies an SSH public key and chooses the local account password
while building the image.

## Touchscreen

The TSC2005 driver reports raw stylus coordinates. A userspace transform maps
those coordinates onto the 800 by 480 display. Maemo's `/etc/pointercal` uses
[tslib's linear-transform format](https://github.com/libts/tslib/blob/master/plugins/linear.c).
Pocket stores its transform as JSON with the detected input-device identity,
axis ranges and display geometry.

`n810-setup-touch` converts a seven-integer tslib transform into Pocket's format.
It checks `/etc/pointercal`, `/mnt/maemo/etc/pointercal` and
`/media/maemo/etc/pointercal`. The owner checks an imported mapping using the
stylus preview before accepting it. An unavailable or rejected mapping leads to
fresh five-target calibration. The historical collector records four corners
and a center target; the fitter checks the center independently and rejects
excessive error.

The shipped kernel has `CONFIG_JFFS2_FS` disabled. Maemo's internal root filesystem
therefore requires a separate recovery/export procedure before its files can be
made available here. The first-boot service uses available files and the stylus
calibration fallback. It leaves internal flash alone.

The resulting profile is `/etc/n810/touch-calibration.json`. The image creates a
link at `~/.local/state/current-world/touch-calibration.json` for the selected
account, matching the existing Pocket session path. The first-boot service runs
on tty1 before the login prompt. A skipped or failed calibration can be repeated
with `sudo n810-setup-touch`; `--recalibrate` collects new targets. To use a
previously exported file from your own tablet, run
`sudo n810-setup-touch --pointercal /path/to/pointercal`.

## Wireless and other device inputs

| Component | Current input path and setup boundary |
|---|---|
| Wi-Fi | The maintained p54 SPI driver requests `3826.arm` firmware and reads the radio's EEPROM. Firmware acquisition and validation still need a device setup path. The Maemo WLAN CAL emulation harness is a research tool with recorded limitations. |
| Bluetooth | The Nokia driver requests `nokia/bc4fw.bin`. The existing `n810-bluetooth-address` helper can preserve a supplied address or generate a stable locally administered address. Installing firmware and the Bluetooth service remains separate platform integration work. |
| Touch | The first-boot service reuses an available tslib transform after visual confirmation or collects a fresh mapping. |
| Battery and power | CAL inspection includes the BME PMM block used during power research. Automatic import of that block into a Debian power-management service remains unimplemented. |
| SSH and account identity | The builder installs the owner's public key. First boot generates host keys and machine identity. |

The SD builder supplies a base system. Pocket supervisor installation and the
wireless firmware steps remain work items in the [status page](../status.md).

## Verification

On 7 November 2026, the initial Docker Make target built the real Linux 5.15.224
kernel with 199 modules and 35 symbol checks. A clean build with caching disabled
produced a 2 GiB ext4 partition in a 2,148,532,224-byte SD image. The kit hashes,
partition contents, filesystem, and first-boot identity settings passed checks.

Touch setup conversion tests cover normal, swapped and inverted axes, invalid
coefficients, and the current Pocket profile schema. The ARM collector is
cross-compiled with warnings treated as errors. Stylus collection and first-boot
service behavior require attended tablet verification.
