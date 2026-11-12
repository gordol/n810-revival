# 0xFFFF host flasher

Build the pinned upstream C implementation from the repository root:

```sh
make flasher
make flasher-help
```

On macOS, install Xcode command-line tools and `brew install libusb-compat
pkg-config` first. On Debian, install `build-essential pkg-config libusb-dev`.
The first build downloads the checksum-verified upstream source. Python 3
orchestrates the build; it does not reimplement the flashing protocol.

The output is `dist/flasher/0xFFFF`. `BUILD.json` records the compiler, source
revision, patches and binary checksum. The same folder retains the upstream
source archive and GPL license. Existing output built from different inputs is
refused; select a new `FLASHER_OUTPUT` for a changed build.

Install on the build host with `sudo make flasher-install`. For a filesystem
image, use `make flasher-install DESTDIR=/path/to/root`. This installs a regular
executable, never a setuid binary. USB access may require root or device access
rules. Do not run the entire Pocket desktop as root.

## Nokia as the flashing host

The N810 can run the same source build with a native compiler. For cross builds,
set `FLASHER_TARGET=armel`, `FLASHER_CC` to an ARM EABI cross compiler, and
`FLASHER_USB_FLAGS` to the matching ARM libusb include/library flags. The
bootstrap builder stages a cross build using:

```sh
python3 platform/bootstrap/stage_flasher.py --root /path/to/debian-root \
    --build /path/to/arm-flasher-build
```

It verifies the ARM ELF header, binary/source/patch checksums and USB-only
configuration before installing. The internal image builder requires that staged
flasher. Retain the source and license files when redistributing the image.

Connecting two N810s requires a suitable USB OTG host adapter, a data cable and
sufficient power. The host tablet must support USB host mode; the other tablet
must be in Nokia update mode. Installing this executable does not enable host
mode or reboot either tablet. A two-tablet physical flashing test is still
required.

These builds disable automatic local-device selection: a Nokia running the
flasher searches for the *other* tablet on USB. The macOS build supports NOLO
update mode only; cold flashing is deliberately unavailable on that platform.
Upstream help still lists the other compiled operations. Read-only identification
is `sudo dist/flasher/0xFFFF -I`; interrupt it if the expected tablet is absent.
Never pass flash or reboot flags just to check connectivity.

## Wizard status

Pocket's N810 Setup screen and the root Makefile share the internal installer
backend. Setup builds and checks kits and identifies one RX-44. Its automatic
RAM-installer path has not completed physical acceptance. The verified macOS
route exports internal MMC from stock Maemo and uses
`platform/bootstrap/write_macos_internal.py` for a full-disk write and readback.
The same stages are `make n810-build-internal`,
`n810-check`, `n810-identify`, `n810-boot-installer`, `n810-write-internal` and
`n810-flash-kernel`. The kit-pack step consumes staged Debian, kernel and
RAM-installer directories; composing those inputs from a fresh Linux build and
accepting first boot on a second N810 remain outstanding.

## One-time macOS USB authorization

Builds run in Linux/Docker; USB operations run natively on macOS. No Docker USB
passthrough is required. To prepare the reusable helper installer:

```sh
make flasher-helper-prepare
sudo /bin/sh dist/flasher-helper/install.sh
```

Preparation requires the macOS command-line tools and the normal flasher build
prerequisites. It bundles the verified flasher and its USB libraries, rewrites
library paths to the bundled copies, and signs the binaries locally. The
installer checks the bundle hashes, installs root-owned files under
`/Library/PrivilegedHelperTools/org.n810-revival.flasher`, and validates a sudoers
rule for the invoking local user. Installation does not access a tablet.

The helper accepts only identification, kernel-plus-initramfs RAM boot, and
kernel flash with reboot. Setup and the shared installer CLI select it
automatically when its original binary identity matches the local build. Only
this helper receives passwordless sudo; the desktop runs as the ordinary user.
Its watchdog stops a stalled 0xFFFF child before the installer timeout, so a
timed-out flash cannot remain armed for a later update-mode connection. After
updating the helper source, prepare a new bundle and install it with the
printed `--replace` command before another USB operation.
The helper permits those USB operations whenever invoked by that user, so retain
it only while that ongoing access is wanted. Existing installations are refused
rather than overwritten.

To revoke access, remove `/etc/sudoers.d/n810-revival-flasher` using administrator
privileges. The helper directory can then be removed as well. A changed flasher
build requires a reviewed replacement installation.
