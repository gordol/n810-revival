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

Pocket's N810 Setup screen includes **Build host flasher**, which runs this same
Make build without opening a USB device. It also verifies manifests and prepares local kits. Its
complete build, USB detection, RAM installer boot, internal storage write and
permanent kernel flash flow is still under integration. Those actions are not
performed by Check files or Prepare local kit. Installing this flasher alone
does not complete that wizard.
