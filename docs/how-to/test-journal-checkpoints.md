# Build and test the journal checkpoints

The [journal source index](../reference/journal-sources.md) follows the posts in chronological order. Each entry links its implementation, regression tests and build inputs. The index also provides local copies of the source files.

Run the commands below from the repository root. Each check uses generated fixtures, an isolated virtual display, or a fresh build directory. The device acceptance scripts beside the historical source describe separate, attended tests.

## Inspect the early filesystem tools

The JFFS2 reader reconstructs files from saved flash images. The CAL reader checks Nokia configuration records and their checksums. Their tests generate small inputs in memory, including corrupt records, deleted entries and overlapping file fragments:

```sh
python3 platform/maemo/test_readers.py
python3 platform/maemo/test_image_assembly.py
```

The partition-assembly test scales the layout down to a temporary file and verifies that partition 1 survives byte for byte. The actual assembler retains the N810 layout constants and requires explicit input files.

The Wi-Fi emulator has an additional input contract. Install `platform/maemo/requirements.txt` in a virtual environment, then provide your own saved CAL image and the Maemo `wlan-cal` executable. The harness checks the executable's SHA-256 before using its version-specific ARM hook addresses:

```sh
python3 platform/maemo/emulate-wlan-cal.py \
  --binary /path/to/wlan-cal --cal-image /path/to/saved-config-image \
  --out /path/to/new-private-results
```

It emulates ARM instructions and intercepts CAL access and file writes in memory. The output directory contains device-specific calibration results and belongs with private recovery material. The repository supplies the reader, emulator and synthetic tests. Each owner's firmware and calibration supply the remaining inputs for that investigation.

## Build the platform helpers and test their behavior

Use a Linux build environment with Python 3, GCC, the `gcc-arm-linux-gnueabi` and `libc6-dev-armel-cross` packages, QEMU user emulation, tmux, whiptail and insserv. These are build-machine dependencies. The [kernel guide](build-kernel.md) describes the corresponding kernel toolchain.

```sh
python3 platform/build-tools.py --out /tmp/n810-platform-tools
python3 tools/test-platform.py --work /tmp/n810-platform-tests
sh platform/scripts/test-n810-boot-tags.sh /path/to/reconstructed/linux-5.15.224
```

The first command builds the input, backlight and wake helpers plus the freestanding r14 rescue program. The second exercises power-mode transitions, session switching, key handling, mock input events, tmux resizing and startup ordering. `N810_INSSERV` can select an unpacked insserv executable. The final command compiles the real boot-tag converter and libfdt from the reconstructed kernel, then checks them under ARM1136 emulation.

The r14 rescue source preserves the loader and filesystem checks described in the first post. Its original combined rescue kernel belongs to the older 5.15.86 build lineage. Compiling its init program establishes that this source builds; reproducing that historical boot image additionally requires its exact kernel tree and initramfs configuration. The maintained 5.15.224 kernel has its own [fresh-checkout verification record](../reference/kernel-build-verification.md).

## Check the RGB console patch

```sh
python3 platform/console-rgb/tests/run.py
python3 platform/console-rgb/acceptance/test_console_accept.py
```

The C harness extracts the actual console functions from the retained October source and compiles them with AddressSanitizer and UndefinedBehaviorSanitizer. It checks RGB parsing, all 65,536 RGB565 values, scrolling, insertion, deletion, clipping, inversion and cursor behavior. The Python suite mocks the console to check cleanup, including restoration after a failed test.

`platform/console-rgb/acceptance/console_accept.py` contains the separate physical-console acceptance tool. Its default invocation prints a plan. The [console patch reference](../reference/console-rgb-patch.md) explains the implementation and the original display results.

## Check the sidebar and phone terminal

The earlier X11 desktop is retained under `historical/sidebar-desktop/`. Its rail, Matchbox bindings, Xorg configuration and XFCE configuration belong to that prototype. Install Xvfb, Matchbox, xterm, x11-xserver-utils, libx11-dev and libxtst-dev on a Linux builder, then run:

```sh
sh historical/sidebar-desktop/test-rail.sh
sh historical/sidebar-desktop/build-armel.sh /tmp/n810-sidebar-armel
```

The first command creates an isolated 800 × 480 virtual display. It checks application selection, launch, pointer input, rail resizing and lock behavior. The builder checks downloaded Debian armel library hashes and compiles the rail and its platform helpers. `packages.txt` records the desktop packages used by the prototype.

The phone bridge keeps its web client, SSH/tmux adapter and locked npm dependencies together:

```sh
node historical/phone-terminal/test-client.cjs
node historical/phone-terminal/test-device-input.cjs
node historical/phone-terminal/test-workspace.cjs
npm ci --prefix historical/phone-terminal/runtime
```

The three tests exercise reconnection, foreground/background transitions, key translation and validated tmux session selection with mocks. The dependency installation prepares the HTTPS service. `setup.py` takes an explicit bind address, SSH target and control socket, and generates credentials in an ignored `.private` directory. `verify.cjs` checks a deliberately started bridge; using its real SSH path requires a configured target. The October post records the earlier transport test separately from these offline checks.

## Repeat the CPU and DSP checks

The retained 18 October source includes the original scalar, short-vector and matrix workloads:

```sh
python3 historical/compute/vfp/build_probe.py --out /tmp/n810-vfp-scalar
python3 historical/compute/vfp/build_shortvec.py --out /tmp/n810-vfp-vector
```

These commands require the ARM cross-compiler and `qemu-arm`. They check numerical agreement and the Debian armel calling convention. The short-vector suite also removes FPSCR and register restoration in separate negative controls and checks that both failures are detected. Emulation establishes these properties; the tablet timings quoted in the journal remain the recorded physical runs.

The DSP model checks run on the host with Python and a C compiler:

```sh
python3 historical/compute/open-c55x/test_subset.py --out /tmp/n810-dsp-subset
python3 historical/compute/open-c55x/test_fir8.py --out /tmp/n810-dsp-fir
python3 historical/compute/open-c55x/test_wrapper.py --out /tmp/n810-dsp-wrapper
```

The tests construct their numerical fixtures, compare the FIR model with Python and C, and check the restricted instruction encodings. `open-c55x/artifacts.json` pins the public assembler snapshot and TI manual. `recover.py` checks or fetches those inputs; `build.py` documents the Linux tools and explicit `config.sub` and `config.guess` inputs needed to build that assembler. The source also retains the control-relocation patch and its before/after hashes. Physical DSP execution remains a separate milestone.

## Repeat the Morse decoder tests

```sh
python3 -B -m unittest discover \
  -s pocket/shell/vendor/apps/cw-reference -p 'test_*.py' -q
```

The 26 tests generate synthetic Morse audio with known text, noise, speed and tone. They cover end-of-file handling, chunk boundaries, sample-rate conversion, rejected interference and stream discontinuities. The fictional callsign in these fixtures is independent of the operator's identity.

## Build the microLXMF reproductions

Use a C++17 compiler, CMake, Python, Git and bzip2 development headers:

```sh
cmake -S hardware/htit/tests/native -B /tmp/n810-lxmf-tests \
  -DRNS_SANITIZE=ON -DCMAKE_BUILD_TYPE=Debug -DHTIT_LATE_CLOSE=ON
cmake --build /tmp/n810-lxmf-tests --parallel 4
ctest --test-dir /tmp/n810-lxmf-tests --output-on-failure
```

CMake fetches the pinned public dependencies and applies the firmware's MessagePack preparation step in the build directory. The tests use the imported microReticulum and microLXMF source. They exercise stale-link recovery, receipt callbacks, resource storage, fixed-array bounds, deeply nested fields and a signed proof arriving after router destruction. Their in-memory transport makes the lifetime and parser failures repeatable on a host.

The [HTIT build guide](build-htit.md) covers the ESP32 firmware. The [Pocket validation guide](validate.md) covers the integrated application and radio tests, while the [map build guide](build-map-data.md) covers geographic input preparation. Existing GPU checks remain documented in the [frozen checkpoint guide](build-gpu-30fps.md).
