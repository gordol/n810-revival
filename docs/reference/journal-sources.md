# Journal source index

This index follows the journal from the first recovery work through the latest documented investigations. Each source link opens a local text copy from this checkout; the adjacent GitHub link identifies its repository location. Build guides open inside this site.

The [checkpoint test guide](../how-to/test-journal-checkpoints.md) gives the commands and external inputs. Each entry identifies its source version and the scope of its tests.

<a id="beginnings"></a>

## Recovering the machine and booting Debian

[Read the journal entry](../posts/beginnings.md)

| Material | Repository files |
|---|---|
| Implementation | [JFFS2 extractor](../assets/source/journal/platform/scripts/n810-jffs2-extract.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-jffs2-extract.py))<br>[CAL record reader](../assets/source/journal/platform/scripts/n810-cal-inspect.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-cal-inspect.py))<br>[Merged-/usr rescue](../assets/source/journal/platform/scripts/n810-merged-usr-rescue-r14-init.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-merged-usr-rescue-r14-init.c))<br>[Partition assembler](../assets/source/journal/platform/scripts/assemble-clean-n810-emmc.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/assemble-clean-n810-emmc.py)) |
| Checks and fixtures | [Synthetic flash records](../assets/source/journal/platform/maemo/test_readers.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/maemo/test_readers.py))<br>[Partition preservation](../assets/source/journal/platform/maemo/test_image_assembly.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/maemo/test_image_assembly.py))<br>[Boot-tag converter regression](../assets/source/journal/platform/scripts/test-n810-boot-tags.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/test-n810-boot-tags.c)) |
| Build inputs | [ARM helper builder](../assets/source/journal/platform/build-tools.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/build-tools.py))<br>[Maintained kernel pins](../assets/source/journal/platform/kernel/source.lock.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/source.lock.json))<br>[Kernel configuration](../assets/source/journal/platform/kernel/n810.config.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/n810.config)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md) · [Chronological source index](../reference/journal-sources.md#beginnings)

The rescue init source and its compiler inputs are retained. Its historical 5.15.86 combined boot image still needs the exact earlier kernel tree and initramfs configuration. Original flash backups and device calibration remain private inputs.

<a id="2026-10-03-wifi"></a>

## Recovering the complete Wi-Fi firmware

[Read the journal entry](../posts/2026-10-03-wifi.md)

| Material | Repository files |
|---|---|
| Implementation | [Maemo helper emulator](../assets/source/journal/platform/maemo/emulate-wlan-cal.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/maemo/emulate-wlan-cal.py))<br>[Wi-Fi service](../assets/source/journal/platform/scripts/n810-wifi-service.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-wifi-service))<br>[Maintained SPI/Wi-Fi changes](../assets/source/journal/platform/kernel/n810-5.15.224.patch.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/n810-5.15.224.patch)) |
| Checks and fixtures | [CAL corruption checks](../assets/source/journal/platform/maemo/test_readers.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/maemo/test_readers.py))<br>[Kernel source inventory](../assets/source/journal/platform/kernel/source-files.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/source-files.json)) |
| Build inputs | [Emulator dependencies](../assets/source/journal/platform/maemo/requirements.txt.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/maemo/requirements.txt))<br>[Kernel builder](../assets/source/journal/platform/kernel/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/build.py))<br>[Wi-Fi configuration](../assets/source/journal/platform/scripts/n810-wifi-config.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-wifi-config)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md) · [Chronological source index](../reference/journal-sources.md#2026-10-03-wifi)

The maintained patch contains p54spi.c and spi-omap2-mcspi.c. The ARM helper emulator requires the hash-identified Maemo executable and the owner's CAL image. The physical association and transfer results are historical device observations.

<a id="2026-10-05-power-display-input"></a>

## Bringing up charging, display wake, and input

[Read the journal entry](../posts/2026-10-05-power-display-input.md)

| Material | Repository files |
|---|---|
| Implementation | [Wake and input policy](../assets/source/journal/platform/scripts/n810-wake.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-wake.c))<br>[Screen wake sequence](../assets/source/journal/platform/scripts/n810-screen.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-screen))<br>[Charging-mode transitions](../assets/source/journal/platform/scripts/n810-mode.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-mode))<br>[Touch calibration](../assets/source/journal/platform/scripts/n810-touch-calibrate.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-touch-calibrate.c))<br>[Maintained power/display changes](../assets/source/journal/platform/kernel/n810-5.15.224.patch.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/n810-5.15.224.patch)) |
| Checks and fixtures | [Mock input events](../assets/source/journal/platform/scripts/test-n810-wake-input.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/test-n810-wake-input.py))<br>[Charging-mode recovery](../assets/source/journal/platform/scripts/test-n810-mode.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/test-n810-mode.py))<br>[Brightness remapping](../assets/source/journal/platform/scripts/test-n810-brightness-remap.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/test-n810-brightness-remap.py)) |
| Build inputs | [ARM helper builder](../assets/source/journal/platform/build-tools.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/build-tools.py))<br>[Kernel file inventory](../assets/source/journal/platform/kernel/source-files.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/source-files.json))<br>[Platform test runner](../assets/source/journal/tools/test-platform.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/tools/test-platform.py)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md) · [Chronological source index](../reference/journal-sources.md#2026-10-05-power-display-input)

The kernel patch retains Retu, Tahvo, board and RFBI changes. The input suites use generated events and mock commands; the display and charging measurements in the post came from the tablet.

<a id="2026-10-05-sidebar-desktop"></a>

## Building the first sidebar desktop

[Read the journal entry](../posts/2026-10-05-sidebar-desktop.md)

| Material | Repository files |
|---|---|
| Implementation | [Application rail](../assets/source/journal/historical/sidebar-desktop/n810-rail.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/sidebar-desktop/n810-rail.c))<br>[X session](../assets/source/journal/historical/sidebar-desktop/session.sh.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/sidebar-desktop/session.sh))<br>[Touch-to-X mapping](../assets/source/journal/historical/sidebar-desktop/xorg-config.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/sidebar-desktop/xorg-config.py)) |
| Checks and fixtures | [Virtual-display rail test](../assets/source/journal/historical/sidebar-desktop/test-rail.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/sidebar-desktop/test-rail.c))<br>[Isolated X test launcher](../assets/source/journal/historical/sidebar-desktop/test-rail.sh.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/sidebar-desktop/test-rail.sh))<br>[Session restoration](../assets/source/journal/platform/scripts/test-n810-session.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/test-n810-session.py)) |
| Build inputs | [Pinned ARM build](../assets/source/journal/historical/sidebar-desktop/build-armel.sh.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/sidebar-desktop/build-armel.sh))<br>[Desktop packages](../assets/source/journal/historical/sidebar-desktop/packages.txt.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/sidebar-desktop/packages.txt))<br>[Xorg configuration](../assets/source/journal/historical/sidebar-desktop/xorg.conf.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/sidebar-desktop/xorg.conf)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md) · [Chronological source index](../reference/journal-sources.md#2026-10-05-sidebar-desktop)

The original sidebar and XFCE prototype are retained as historical source. The current terminal desktop has a separate build and launcher.

<a id="2026-10-13-sd-bluetooth"></a>

## Moving Debian to SD and connecting peripherals

[Read the journal entry](../posts/2026-10-13-sd-bluetooth.md)

| Material | Repository files |
|---|---|
| Implementation | [SD image assembly](../assets/source/journal/platform/scripts/assemble-n810-minisd-inplace.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/assemble-n810-minisd-inplace.py))<br>[Bluetooth control](../assets/source/journal/platform/scripts/n810-bluetooth.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-bluetooth))<br>[Maintained Bluetooth driver changes](../assets/source/journal/platform/kernel/n810-5.15.224.patch.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/n810-5.15.224.patch)) |
| Checks and fixtures | [Swap preservation](../assets/source/journal/platform/scripts/test-n810-zram.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/test-n810-zram.py))<br>[Bluetooth fallback](../assets/source/journal/pocket/tests/test_bluetooth_hardware_fallback.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_bluetooth_hardware_fallback.py)) |
| Build inputs | [zram service](../assets/source/journal/platform/device/n810-zram.init.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/device/n810-zram.init))<br>[SD package-cache settings](../assets/source/journal/platform/config/n810-apt-sd.conf.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/config/n810-apt-sd.conf))<br>[Kernel configuration](../assets/source/journal/platform/kernel/n810.config.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/n810.config)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md) · [Chronological source index](../reference/journal-sources.md#2026-10-13-sd-bluetooth)

The maintained source includes hci_nokia.c. A complete historical SD installation additionally requires its root-filesystem and owner-specific firmware inputs. The current kernel build is documented separately.

<a id="2026-10-14-aprs"></a>

## Starting with APRS and the handheld radio

[Read the journal entry](../posts/2026-10-14-aprs.md)

| Material | Repository files |
|---|---|
| Implementation | [APRS decoder](../assets/source/journal/pocket/shell/vendor/packet-console/n810-aprs-decode.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/packet-console/n810-aprs-decode.py))<br>[Packet viewer](../assets/source/journal/pocket/shell/vendor/packet-console/n810-aprs-view.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/packet-console/n810-aprs-view.py))<br>[Radio owner](../assets/source/journal/pocket/shell/vendor/packet-console/n810-aprs-services.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/packet-console/n810-aprs-services.py))<br>[Map demonstration](../assets/source/journal/tools/docs/aprs_map_preview.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/tools/docs/aprs_map_preview.py))<br>[tmux demonstration](../assets/source/journal/tools/docs/tmux_preview.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/tools/docs/tmux_preview.py)) |
| Checks and fixtures | [Packet decoding](../assets/source/journal/pocket/shell/vendor/packet-console/test-aprs-decode.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/packet-console/test-aprs-decode.py))<br>[Workspace selection](../assets/source/journal/pocket/shell/vendor/packet-console/test-packet-workspace-tui.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/packet-console/test-packet-workspace-tui.py))<br>[Radio banks](../assets/source/journal/pocket/shell/vendor/packet-console/test-radio-banks.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/packet-console/test-radio-banks.py))<br>[Walk history](../assets/source/journal/pocket/shell/vendor/packet-console/test-walk-history.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/packet-console/test-walk-history.py)) |
| Build inputs | [Workspace contract](../assets/source/journal/pocket/shell/vendor/packet-console/fixtures/tui-window-contract.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/packet-console/fixtures/tui-window-contract.json))<br>[Map build targets](../assets/source/journal/pocket/maps.mk.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/maps.mk))<br>[tmux configuration](../assets/source/journal/platform/config/tmux-n810.conf.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/config/tmux-n810.conf)) |

[Build and test instructions](../how-to/build-map-data.md) · [Chronological source index](../reference/journal-sources.md#2026-10-14-aprs)

The demonstrations use generated packets and reviewed public map data. The original personal walk recordings remain private; synthetic fixtures preserve the protocol and history tests.

<a id="2026-10-16-radio-ssh"></a>

## One radio receiver, several terminal views

[Read the journal entry](../posts/2026-10-16-radio-ssh.md)

| Material | Repository files |
|---|---|
| Implementation | [SSH service attachment](../assets/source/journal/pocket/shell/device_connection.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/device_connection.py))<br>[Phone bridge](../assets/source/journal/historical/phone-terminal/server.cjs.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/phone-terminal/server.cjs))<br>[tmux session validation](../assets/source/journal/historical/phone-terminal/workspace.cjs.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/phone-terminal/workspace.cjs)) |
| Checks and fixtures | [SSH attachment](../assets/source/journal/pocket/tests/test_device_connection.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_device_connection.py))<br>[Browser reconnects](../assets/source/journal/historical/phone-terminal/test-client.cjs.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/phone-terminal/test-client.cjs))<br>[Phone keys](../assets/source/journal/historical/phone-terminal/test-device-input.cjs.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/phone-terminal/test-device-input.cjs))<br>[Session selection](../assets/source/journal/historical/phone-terminal/test-workspace.cjs.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/phone-terminal/test-workspace.cjs)) |
| Build inputs | [Phone dependencies](../assets/source/journal/historical/phone-terminal/runtime/package-lock.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/phone-terminal/runtime/package-lock.json))<br>[Private configuration generator](../assets/source/journal/historical/phone-terminal/setup.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/phone-terminal/setup.py))<br>[Service attachment fixtures](../assets/source/journal/pocket/tests/test_owner_attachments.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_owner_attachments.py)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md) · [Chronological source index](../reference/journal-sources.md#2026-10-16-radio-ssh)

<a id="2026-10-16-16-bit-console"></a>

## Extending the Linux console to RGB565

[Read the journal entry](../posts/2026-10-16-16-bit-console.md)

| Material | Repository files |
|---|---|
| Implementation | [October console patch](../assets/source/journal/platform/patches/console-rgb.patch.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/patches/console-rgb.patch))<br>[Retained VT source](../assets/source/journal/platform/console-rgb/after/drivers/tty/vt/vt.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/console-rgb/after/drivers/tty/vt/vt.c))<br>[Retained framebuffer-console source](../assets/source/journal/platform/console-rgb/after/drivers/video/fbdev/core/fbcon.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/console-rgb/after/drivers/video/fbdev/core/fbcon.c)) |
| Checks and fixtures | [C regression harness](../assets/source/journal/platform/console-rgb/tests/test.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/console-rgb/tests/test.c))<br>[Extract-and-compile runner](../assets/source/journal/platform/console-rgb/tests/run.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/console-rgb/tests/run.py))<br>[Console cleanup](../assets/source/journal/platform/console-rgb/acceptance/test_console_accept.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/console-rgb/acceptance/test_console_accept.py)) |
| Build inputs | [Console acceptance program](../assets/source/journal/platform/console-rgb/acceptance/console_accept.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/console-rgb/acceptance/console_accept.py))<br>[Maintained kernel configuration](../assets/source/journal/platform/kernel/n810.config.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/n810.config)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md#check-the-rgb-console-patch) · [Chronological source index](../reference/journal-sources.md#2026-10-16-16-bit-console)

<a id="2026-10-16-pocket-desktop"></a>

## Moving the desktop into the terminal

[Read the journal entry](../posts/2026-10-16-pocket-desktop.md)

| Material | Repository files |
|---|---|
| Implementation | [Desktop launcher](../assets/source/journal/pocket/shell/launch.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/launch.py))<br>[Native compositor](../assets/source/journal/pocket/shell/native/cell_engine.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/native/cell_engine.c))<br>[Native windows](../assets/source/journal/pocket/shell/native/window_host.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/native/window_host.c)) |
| Checks and fixtures | [Window composition](../assets/source/journal/pocket/tests/test_native_window_host.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_native_window_host.py))<br>[Keyboard navigation](../assets/source/journal/pocket/tests/test_native_navigation.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_native_navigation.py))<br>[Desktop control](../assets/source/journal/pocket/tests/test_desktop_control.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_desktop_control.py)) |
| Build inputs | [Native build helper](../assets/source/journal/pocket/tools/build_native.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tools/build_native.py))<br>[Pocket build targets](../assets/source/journal/pocket/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/Makefile)) |

[Build and test instructions](../how-to/build-native.md) · [Chronological source index](../reference/journal-sources.md#2026-10-16-pocket-desktop)

<a id="2026-10-16-cw"></a>

## Decoding Morse recordings and preparing an audio input

[Read the journal entry](../posts/2026-10-16-cw.md)

| Material | Repository files |
|---|---|
| Implementation | [Tone detector](../assets/source/journal/pocket/shell/vendor/apps/cw-reference/reference.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/cw-reference/reference.py))<br>[Recording decoder](../assets/source/journal/pocket/shell/vendor/apps/cw-reference/decode.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/cw-reference/decode.py))<br>[PCM adapter](../assets/source/journal/pocket/shell/vendor/apps/cw-reference/pcm_input.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/cw-reference/pcm_input.py))<br>[Stream decoder](../assets/source/journal/pocket/shell/vendor/apps/cw-reference/stream_cw.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/cw-reference/stream_cw.py))<br>[Replay process](../assets/source/journal/pocket/shell/vendor/apps/domains/workbench/runner.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/domains/workbench/runner.py)) |
| Checks and fixtures | [Generated Morse fixtures](../assets/source/journal/pocket/shell/vendor/apps/cw-reference/test_decode.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/cw-reference/test_decode.py))<br>[Stream boundary checks](../assets/source/journal/pocket/shell/vendor/apps/cw-reference/test_stream_cw.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/cw-reference/test_stream_cw.py))<br>[Resampling and noise rejection](../assets/source/journal/pocket/shell/vendor/apps/cw-reference/test_pcm_input.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/cw-reference/test_pcm_input.py)) |
| Build inputs | [Synthetic tone generator](../assets/source/journal/pocket/shell/vendor/apps/cw-reference/test_reference.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/cw-reference/test_reference.py))<br>[Replay application model](../assets/source/journal/pocket/shell/vendor/apps/domains/workbench/model.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/domains/workbench/model.py)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md) · [Chronological source index](../reference/journal-sources.md#2026-10-16-cw)

The restored suites generate their audio and expected text. Personal recordings and the separate annotated recording corpus are outside this reproducible synthetic test set.

<a id="2026-10-18-cpu-acceleration"></a>

## Measuring the ARM CPU before moving work elsewhere

[Read the journal entry](../posts/2026-10-18-cpu-acceleration.md)

| Material | Repository files |
|---|---|
| Implementation | [Scalar workload](../assets/source/journal/historical/compute/vfp/kernel.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/vfp/kernel.c))<br>[Short-vector assembly](../assets/source/journal/historical/compute/vfp/shortvec.S.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/vfp/shortvec.S))<br>[Timing workload](../assets/source/journal/historical/compute/vfp/benchmark.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/vfp/benchmark.c))<br>[DSP instruction encoder](../assets/source/journal/historical/compute/open-c55x/subset.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/open-c55x/subset.py))<br>[FIR model](../assets/source/journal/historical/compute/open-c55x/fir_model.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/open-c55x/fir_model.py)) |
| Checks and fixtures | [VFP scalar/ABI probe](../assets/source/journal/historical/compute/vfp/build_probe.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/vfp/build_probe.py))<br>[Vector/context negative controls](../assets/source/journal/historical/compute/vfp/build_shortvec.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/vfp/build_shortvec.py))<br>[DSP FIR comparisons](../assets/source/journal/historical/compute/open-c55x/test_fir8.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/open-c55x/test_fir8.py))<br>[DSP context checks](../assets/source/journal/historical/compute/open-c55x/test_wrapper.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/open-c55x/test_wrapper.py)) |
| Build inputs | [Assembler source pins](../assets/source/journal/historical/compute/open-c55x/artifacts.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/open-c55x/artifacts.json))<br>[Assembler builder](../assets/source/journal/historical/compute/open-c55x/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/open-c55x/build.py))<br>[Independent C reference](../assets/source/journal/historical/compute/fir_q15.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/historical/compute/fir_q15.c)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md) · [Chronological source index](../reference/journal-sources.md#2026-10-18-cpu-acceleration)

The imported source comes from the retained 18 October checkpoint. ARM emulation and host numerical tests reproduce correctness checks. The speed ratios quoted in the post remain physical-device measurements.

<a id="2026-10-20-water-and-idle"></a>

## Rendering water and measuring idle work

[Read the journal entry](../posts/2026-10-20-water-and-idle.md)

| Material | Repository files |
|---|---|
| Implementation | [Session persistence](../assets/source/journal/pocket/shell/session.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/session.py))<br>[Native scene preparation](../assets/source/journal/pocket/shell/native/scene_host.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/native/scene_host.c))<br>[Cell composition](../assets/source/journal/pocket/shell/native/cell_engine.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/native/cell_engine.c)) |
| Checks and fixtures | [Saved-session migration](../assets/source/journal/pocket/tests/test_desktop_session_migration.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_desktop_session_migration.py))<br>[Scene output](../assets/source/journal/pocket/tests/test_native_scene_host.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_native_scene_host.py))<br>[Retained rendering](../assets/source/journal/pocket/tests/test_render_pass_reuse.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_render_pass_reuse.py)) |
| Build inputs | [Native build helper](../assets/source/journal/pocket/tools/build_native.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tools/build_native.py))<br>[Scene data preparation](../assets/source/journal/pocket/tools/prepare_loader_ambient.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tools/prepare_loader_ambient.py)) |

[Build and test instructions](../how-to/build-native.md) · [Chronological source index](../reference/journal-sources.md#2026-10-20-water-and-idle)

These links identify the integrated implementation and its tests. The post's idle and 726-point water measurements describe the earlier physical runs.

<a id="2026-10-24-maps-with-an-edge"></a>

## Preparing maps and preserving the last usable view

[Read the journal entry](../posts/2026-10-24-maps-with-an-edge.md)

| Material | Repository files |
|---|---|
| Implementation | [Offline renderer](../assets/source/journal/pocket/shell/offline_map.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/offline_map.py))<br>[Touch process](../assets/source/journal/pocket/shell/touch_process.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/touch_process.py))<br>[Geography builder](../assets/source/journal/pocket/tools/build_map_geography.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tools/build_map_geography.py))<br>[Shoreline builder](../assets/source/journal/pocket/tools/build_desktop_shoreline.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tools/build_desktop_shoreline.py)) |
| Checks and fixtures | [Geographic fixtures](../assets/source/journal/pocket/tests/test_map_geography.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_geography.py))<br>[Drag scheduling](../assets/source/journal/pocket/tests/test_drag_model_schedule.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_drag_model_schedule.py))<br>[Terrain worker lifecycle](../assets/source/journal/pocket/tests/test_terrain_worker.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_terrain_worker.py))<br>[Input generations](../assets/source/journal/pocket/tests/test_touch_worker.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_touch_worker.py))<br>[Real map builds](../assets/source/journal/tools/test-map-builds.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/tools/test-map-builds.py)) |
| Build inputs | [Map dependency pins](../assets/source/journal/requirements-maps.txt.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/requirements-maps.txt))<br>[Map build targets](../assets/source/journal/pocket/maps.mk.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/maps.mk)) |

[Build and test instructions](../how-to/build-map-data.md) · [Chronological source index](../reference/journal-sources.md#2026-10-24-maps-with-an-edge)

Reviewed OSM and elevation inputs are included. The original 15 October local TIFF remains an archival gap; the guide rebuilds local terrain from the retained 2 November export.

<a id="2026-10-24-lxmf"></a>

## Sending LXMF messages through the terminal interface

[Read the journal entry](../posts/2026-10-24-lxmf.md)

| Material | Repository files |
|---|---|
| Implementation | [Contact key storage](../assets/source/journal/pocket/shell/vendor/apps/domains/reticulum/contacts.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/domains/reticulum/contacts.py))<br>[LXMF owner](../assets/source/journal/pocket/shell/vendor/apps/domains/reticulum/lxmf_owner.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/domains/reticulum/lxmf_owner.py))<br>[Saved peer restart probe](../assets/source/journal/pocket/shell/vendor/apps/domains/reticulum/tests/private_contact_restart.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/domains/reticulum/tests/private_contact_restart.py)) |
| Checks and fixtures | [Message behavior](../assets/source/journal/pocket/tests/test_chat.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_chat.py))<br>[Session recovery](../assets/source/journal/pocket/tests/test_connection_recovery.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_connection_recovery.py))<br>[Reticulum controls](../assets/source/journal/pocket/tests/test_reticulum_controls.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_reticulum_controls.py)) |
| Build inputs | [Native dependency revisions](../assets/source/journal/pocket/shell/native/reticulum/dependencies.lock.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/native/reticulum/dependencies.lock))<br>[Native preparation](../assets/source/journal/pocket/shell/native/reticulum/prepare.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/native/reticulum/prepare.py)) |

[Build and test instructions](../pocket/native-reticulum.md) · [Chronological source index](../reference/journal-sources.md#2026-10-24-lxmf)

The links follow the current integrated implementation. The October bidirectional signed exchange is a recorded hardware result; repeating it requires two configured identities and an explicitly selected transport.

<a id="2026-10-29-htit"></a>

## Moving Reticulum execution onto the HTIT

[Read the journal entry](../posts/2026-10-29-htit.md)

| Material | Repository files |
|---|---|
| Implementation | [Executor framing](../assets/source/journal/hardware/htit/microreticulum/executor/Transport.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/microreticulum/executor/Transport.cpp))<br>[Host reassembly](../assets/source/journal/pocket/shell/vendor/apps/domains/reticulum/node_transport.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/domains/reticulum/node_transport.py))<br>[Bluetooth buffers](../assets/source/journal/hardware/htit/microreticulum/Bluetooth.h.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/microreticulum/Bluetooth.h)) |
| Checks and fixtures | [Host executor protocol](../assets/source/journal/pocket/tests/test_external_node.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_external_node.py))<br>[Shared HTIT transport](../assets/source/journal/pocket/tests/test_htit_shared_link.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_htit_shared_link.py))<br>[Encrypted Wi-Fi frames](../assets/source/journal/hardware/htit/experiments/ibss-rsn/test_ccmp.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/experiments/ibss-rsn/test_ccmp.py)) |
| Build inputs | [Firmware builder](../assets/source/journal/hardware/htit/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/build.py))<br>[PlatformIO targets](../assets/source/journal/hardware/htit/microreticulum/platformio.ini.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/microreticulum/platformio.ini))<br>[IBSS upstream pins](../assets/source/journal/hardware/htit/experiments/ibss-rsn/rsn-port/upstream_adapter.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/experiments/ibss-rsn/rsn-port/upstream_adapter.py)) |

[Build and test instructions](../how-to/build-htit.md) · [Chronological source index](../reference/journal-sources.md#2026-10-29-htit)

Firmware, vendored libraries and protocol tests are included. Pairing credentials are generated per build. The transfer times in this entry remain associated with their October device trials.

<a id="2026-10-30-htit-recovery"></a>

## Debugging HTIT reconnects and internal RAM pressure

[Read the journal entry](../posts/2026-10-30-htit-recovery.md)

| Material | Repository files |
|---|---|
| Implementation | [LXMF router lifetime](../assets/source/journal/hardware/htit/microreticulum/executor-libs/microLXMF/src/LXMF/LXMRouter.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/microreticulum/executor-libs/microLXMF/src/LXMF/LXMRouter.cpp))<br>[Transport callbacks](../assets/source/journal/hardware/htit/microreticulum/executor-libs/microReticulum/src/microReticulum/Transport.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/microreticulum/executor-libs/microReticulum/src/microReticulum/Transport.cpp))<br>[Resource storage](../assets/source/journal/hardware/htit/microreticulum/executor-libs/microReticulum/src/microReticulum/Resource.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/microreticulum/executor-libs/microReticulum/src/microReticulum/Resource.cpp)) |
| Checks and fixtures | [Recovery and resource regression](../assets/source/journal/hardware/htit/tests/native/lxmf_recovery.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/tests/native/lxmf_recovery.cpp))<br>[Host reconnect behavior](../assets/source/journal/pocket/tests/test_connection_recovery.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_connection_recovery.py)) |
| Build inputs | [Native test build](../assets/source/journal/hardware/htit/tests/native/CMakeLists.txt.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/tests/native/CMakeLists.txt))<br>[Firmware build](../assets/source/journal/hardware/htit/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/build.py)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md#build-the-microlxmf-reproductions) · [Chronological source index](../reference/journal-sources.md#2026-10-30-htit-recovery)

<a id="2026-10-31-gpu-clocks"></a>

## Bringing up the graphics clock domain

[Read the journal entry](../posts/2026-10-31-gpu-clocks.md)

| Material | Repository files |
|---|---|
| Implementation | [Clock commit](../assets/source/journal/graphics/mbx/kernel/clock_commit.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/kernel/clock_commit.c))<br>[Clock lifecycle](../assets/source/journal/platform/kernel/clock-module/mbx_clock_lifecycle.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/clock-module/mbx_clock_lifecycle.c))<br>[Maintained clock-provider changes](../assets/source/journal/platform/kernel/n810-5.15.224.patch.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/n810-5.15.224.patch)) |
| Checks and fixtures | [Kernel/module verification](../assets/source/journal/platform/kernel/verification.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/verification.json))<br>[Kernel source hashes](../assets/source/journal/platform/kernel/source-files.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/source-files.json)) |
| Build inputs | [Clock module makefile](../assets/source/journal/platform/kernel/clock-module/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/clock-module/Makefile))<br>[Kernel builder](../assets/source/journal/platform/kernel/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/build.py)) |

[Build and test instructions](../how-to/build-kernel.md) · [Chronological source index](../reference/journal-sources.md#2026-10-31-gpu-clocks)

These clock sources accompany the maintained 5.15.224 kernel inputs. The temporary 5.15.86 clock experiment is documented as a historical boot result.

<a id="2026-11-02-gpu-command-stream"></a>

## Reconstructing the MBX command stream

[Read the journal entry](../posts/2026-11-02-gpu-command-stream.md)

| Material | Repository files |
|---|---|
| Implementation | [Command encoding](../assets/source/journal/graphics/mbx/common/mbx_packets.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/common/mbx_packets.c))<br>[Context setup](../assets/source/journal/graphics/mbx/common/mbx_context.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/common/mbx_context.c))<br>[Geometry stream](../assets/source/journal/graphics/mbx/common/mbx_vgp_stream.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/common/mbx_vgp_stream.c))<br>[DMA lifecycle](../assets/source/journal/graphics/mbx/kernel/mbx_dma.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/kernel/mbx_dma.c)) |
| Checks and fixtures | [Packet fields](../assets/source/journal/graphics/mbx/tests/test_packets.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/tests/test_packets.c))<br>[Context protocol](../assets/source/journal/graphics/mbx/tests/test_context_protocol.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/tests/test_context_protocol.c))<br>[DMA checks](../assets/source/journal/graphics/mbx/tests/test_dma_verification.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/tests/test_dma_verification.py)) |
| Build inputs | [Graphics input pins](../assets/source/journal/graphics/mbx/dependencies.lock.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/dependencies.lock.json))<br>[Graphics builder](../assets/source/journal/graphics/mbx/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/build.py))<br>[Test runner](../assets/source/journal/graphics/mbx/test.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/test.py)) |

[Build and test instructions](../how-to/build-graphics.md) · [Chronological source index](../reference/journal-sources.md#2026-11-02-gpu-command-stream)

Links use the existing imported graphics checkpoint. The Symbian ROM used for research remains an external historical reference; the repository contains the authored encoders and tests.

<a id="2026-11-02-microlxmf"></a>

## Repairing microLXMF parsing and object lifetime

[Read the journal entry](../posts/2026-11-02-microlxmf.md)

| Material | Repository files |
|---|---|
| Implementation | [Router repair](../assets/source/journal/hardware/htit/microreticulum/executor-libs/microLXMF/src/LXMF/LXMRouter.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/microreticulum/executor-libs/microLXMF/src/LXMF/LXMRouter.cpp))<br>[Bounded LXMF parser](../assets/source/journal/hardware/htit/microreticulum/executor-libs/microLXMF/src/LXMF/LXMessage.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/microreticulum/executor-libs/microLXMF/src/LXMF/LXMessage.cpp))<br>[MessagePack bounds](../assets/source/journal/hardware/htit/microreticulum/executor-libs/MsgPack/MsgPack/Unpacker.h.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/microreticulum/executor-libs/MsgPack/MsgPack/Unpacker.h)) |
| Checks and fixtures | [Signed proof after destruction](../assets/source/journal/hardware/htit/tests/upstream/lxmf_signed_proof_uaf.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/tests/upstream/lxmf_signed_proof_uaf.cpp))<br>[Nested-field input](../assets/source/journal/hardware/htit/tests/upstream/lxmf_nested_fields.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/tests/upstream/lxmf_nested_fields.cpp))<br>[Fixed-array bounds](../assets/source/journal/hardware/htit/tests/native/msgpack_fixed_array.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/tests/native/msgpack_fixed_array.cpp))<br>[Lifetime and cache regression](../assets/source/journal/hardware/htit/tests/native/lxmf_recovery.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/tests/native/lxmf_recovery.cpp)) |
| Build inputs | [Sanitizer build](../assets/source/journal/hardware/htit/tests/native/CMakeLists.txt.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/tests/native/CMakeLists.txt))<br>[Firmware header preparation](../assets/source/journal/hardware/htit/microreticulum/executor/prepare_native.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/hardware/htit/microreticulum/executor/prepare_native.py)) |

[Build and test instructions](../how-to/test-journal-checkpoints.md#build-the-microlxmf-reproductions) · [Chronological source index](../reference/journal-sources.md#2026-11-02-microlxmf)

The restored host reproductions use the imported, repaired libraries. Synthetic messages and an in-memory transport exercise the actual parser and callback paths. The recorded ESP32 resets and later provisioning check are separate hardware results.

<a id="2026-11-03-kernel"></a>

## Maintaining the N810 changes on Linux 5.15.224

[Read the journal entry](../posts/2026-11-03-kernel.md)

| Material | Repository files |
|---|---|
| Implementation | [Maintained N810 patch](../assets/source/journal/platform/kernel/n810-5.15.224.patch.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/n810-5.15.224.patch))<br>[Clock module](../assets/source/journal/platform/kernel/clock-module/n810_mbx_clock_trial.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/clock-module/n810_mbx_clock_trial.c)) |
| Checks and fixtures | [Fresh-checkout result](../assets/source/journal/platform/kernel/verification.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/verification.json))<br>[Source hashes](../assets/source/journal/platform/kernel/source-files.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/source-files.json))<br>[Boot-tag regression](../assets/source/journal/platform/scripts/test-n810-boot-tags.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/test-n810-boot-tags.c)) |
| Build inputs | [Source lock](../assets/source/journal/platform/kernel/source.lock.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/source.lock.json))<br>[Kernel config](../assets/source/journal/platform/kernel/n810.config.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/n810.config))<br>[Builder](../assets/source/journal/platform/kernel/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/build.py)) |

[Build and test instructions](../how-to/build-kernel.md) · [Chronological source index](../reference/journal-sources.md#2026-11-03-kernel)

<a id="2026-11-03-mbx-rendering"></a>

## Rendering standard glxgears on the MBX

[Read the journal entry](../posts/2026-11-03-mbx-rendering.md)

| Material | Repository files |
|---|---|
| Implementation | [Mesa integration](../assets/source/journal/graphics/mbx/mesa/prepare_mesa.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/mesa/prepare_mesa.py))<br>[X11 shared image](../assets/source/journal/graphics/mbx/mesa/mbx_shared_image.h.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/mesa/mbx_shared_image.h))<br>[ARM vertex emitter](../assets/source/journal/graphics/mbx/mesa/draw_mbx_arm_jit.h.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/mesa/draw_mbx_arm_jit.h))<br>[Display lifecycle](../assets/source/journal/graphics/mbx/mesa/desktop_pause.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/mesa/desktop_pause.py)) |
| Checks and fixtures | [Shared-image comparisons](../assets/source/journal/graphics/mbx/tests/test_shared_image.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/tests/test_shared_image.c))<br>[ARM arithmetic](../assets/source/journal/graphics/mbx/tests/test_arm_vertex_jit.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/tests/test_arm_vertex_jit.py))<br>[Display pause](../assets/source/journal/graphics/mbx/tests/test_desktop_pause.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/tests/test_desktop_pause.py)) |
| Build inputs | [Pinned Mesa build](../assets/source/journal/graphics/mbx/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/build.py))<br>[Graphics dependencies](../assets/source/journal/graphics/mbx/dependencies.lock.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/dependencies.lock.json)) |

[Build and test instructions](../how-to/build-graphics.md) · [Chronological source index](../reference/journal-sources.md#2026-11-03-mbx-rendering)

The earlier graphics snapshot contains these implementations and tests. The later 30 FPS snapshot includes the command-reuse and FIFO changes described in the next GPU entry.

<a id="2026-11-04-pocket-0-1-0"></a>

## Integrating the Pocket applications into version 0.1.0

[Read the journal entry](../posts/2026-11-04-pocket-0-1-0.md)

| Material | Repository files |
|---|---|
| Implementation | [Integrated launcher](../assets/source/journal/pocket/shell/launch.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/launch.py))<br>[Map view](../assets/source/journal/pocket/shell/offline_map.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/offline_map.py))<br>[Service selection](../assets/source/journal/pocket/shell/device_connection.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/device_connection.py)) |
| Checks and fixtures | [Release identity](../assets/source/journal/pocket/tests/test_release_version.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_release_version.py))<br>[Line-of-sight refinement](../assets/source/journal/pocket/tests/test_los_resolution.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_los_resolution.py))<br>[Service recovery](../assets/source/journal/pocket/tests/test_service_recovery.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_service_recovery.py))<br>[UI navigation](../assets/source/journal/pocket/tests/test_navigation_audit.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_navigation_audit.py)) |
| Build inputs | [Pocket build targets](../assets/source/journal/pocket/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/Makefile))<br>[Nokia package builder](../assets/source/journal/pocket/tools/package_nokia.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tools/package_nokia.py))<br>[Offline suite runner](../assets/source/journal/tools/check-source.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/tools/check-source.py)) |

[Build and test instructions](../how-to/validate.md) · [Chronological source index](../reference/journal-sources.md#2026-11-04-pocket-0-1-0)

<a id="2026-11-04-gpu-performance"></a>

## Moving geometry onto the GPU and reaching 30 FPS

[Read the journal entry](../posts/2026-11-04-gpu-performance.md)

| Material | Repository files |
|---|---|
| Implementation | [Frozen command reuse](../assets/source/journal/graphics/mbx/checkpoints/30fps-20261104/experiments/vgp-service-20261104/common/mbx_vgp_wire.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/experiments/vgp-service-20261104/common/mbx_vgp_wire.c))<br>[Frozen FIFO path](../assets/source/journal/graphics/mbx/checkpoints/30fps-20261104/experiments/vgp-service-20261104/common/mbx_vgp_stream.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/experiments/vgp-service-20261104/common/mbx_vgp_stream.c)) |
| Checks and fixtures | [Frozen test runner](../assets/source/journal/graphics/mbx/checkpoints/30fps-20261104/test.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/test.py))<br>[Verified result](../assets/source/journal/graphics/mbx/checkpoints/30fps-20261104/VERIFICATION.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/VERIFICATION.json)) |
| Build inputs | [Source hashes](../assets/source/journal/graphics/mbx/checkpoints/30fps-20261104/SOURCE.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/checkpoints/30fps-20261104/SOURCE.json))<br>[Checkpoint builder](../assets/source/journal/graphics/mbx/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/graphics/mbx/build.py)) |

[Build and test instructions](../how-to/build-gpu-30fps.md) · [Chronological source index](../reference/journal-sources.md#2026-11-04-gpu-performance)

This frozen checkpoint contains the driver and Mesa changes behind the two physical 30 FPS runs, together with the offline regression tests and pinned build inputs.

<a id="2026-11-05-help-and-input"></a>

## Following our own keyboard instructions

[Read the journal entry](../posts/2026-11-05-help-and-input.md)

| Material | Repository files |
|---|---|
| Implementation | [Help browser](../assets/source/journal/pocket/shell/on_device_manual/browser.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/on_device_manual/browser.py))<br>[Navigation dispatcher](../assets/source/journal/pocket/shell/native_navigation.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/native_navigation.py)) |
| Checks and fixtures | [Help focus regression](../assets/source/journal/pocket/tests/test_help_focus.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_help_focus.py))<br>[Application focus checks](../assets/source/journal/pocket/tests/test_app_focus_consistency.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_app_focus_consistency.py)) |
| Build inputs | [Pocket build targets](../assets/source/journal/pocket/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/Makefile)) |

[Build and test instructions](../how-to/validate.md) · [Chronological source index](../reference/journal-sources.md#2026-11-05-help-and-input)

The linked files are the reconciled current source. The post identifies the historical observations and their validation scope.

<a id="2026-11-06-session-recovery"></a>

## Keeping session state correct across reconnects

[Read the journal entry](../posts/2026-11-06-session-recovery.md)

| Material | Repository files |
|---|---|
| Implementation | [Radio state ownership](../assets/source/journal/pocket/shell/radio_state.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/radio_state.py))<br>[Session attachments](../assets/source/journal/pocket/shell/system_links.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/system_links.py)) |
| Checks and fixtures | [Retained radio snapshots](../assets/source/journal/pocket/tests/test_radio_snapshot_cache.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_radio_snapshot_cache.py))<br>[Attachment tests](../assets/source/journal/pocket/tests/test_system_attachment.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_system_attachment.py)) |
| Build inputs | [Pocket build targets](../assets/source/journal/pocket/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/Makefile)) |

[Build and test instructions](../how-to/validate.md) · [Chronological source index](../reference/journal-sources.md#2026-11-06-session-recovery)

The linked files are the reconciled current source. The post identifies the historical observations and their validation scope.

<a id="2026-11-06-native-symbian"></a>

## Playing a Symbian chess game through native ARM execution

[Read the journal entry](../posts/2026-11-06-native-symbian.md)


[Chronological source index](../reference/journal-sources.md#2026-11-06-native-symbian)

The native backend extends EKA2L1. Its loader, kernel/service model, and Window Server come from that upstream project, linked in the narrative. The native backend and physical acceptance runner remain experimental and await a public source checkpoint.

<a id="2026-11-07-map-resizing"></a>

## Resizing the map without stretching its annotations

[Read the journal entry](../posts/2026-11-07-map-resizing.md)

| Material | Repository files |
|---|---|
| Implementation | [Retained map sampling](../assets/source/journal/pocket/shell/offline_map.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/offline_map.py))<br>[Station projection](../assets/source/journal/pocket/shell/station_workspace.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/station_workspace.py))<br>[Elevation sampling](../assets/source/journal/pocket/shell/desktop_elevation.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/desktop_elevation.py))<br>[Map build commands](../assets/source/journal/pocket/tools/maps.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tools/maps.py)) |
| Checks and fixtures | [Resize and sampling regressions](../assets/source/journal/pocket/tests/test_map_latency_regressions.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_latency_regressions.py))<br>[Incremental regions](../assets/source/journal/pocket/tests/test_map_incremental_regions.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_incremental_regions.py)) |
| Build inputs | [Pocket build targets](../assets/source/journal/pocket/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/Makefile)) |

[Build and test instructions](../how-to/validate.md) · [Chronological source index](../reference/journal-sources.md#2026-11-07-map-resizing)

The linked files are the reconciled current source. The post identifies the historical observations and their validation scope.

<a id="2026-11-07-symbian-surfaces"></a>

## Teaching the MBX path the drawing operations that Symbian apps use

[Read the journal entry](../posts/2026-11-07-symbian-surfaces.md)


[Chronological source index](../reference/journal-sources.md#2026-11-07-symbian-surfaces)

These driver candidates extend the published MBX/Mesa foundation. Their physical results are dated here; their candidate source and real-application acceptance are still in progress. Use the frozen 30 FPS build guide for the currently published checkpoint.

<a id="2026-11-07-native-desktop"></a>

## Running the Pocket desktop in a native Mac window

[Read the journal entry](../posts/2026-11-07-native-desktop.md)

| Material | Repository files |
|---|---|
| Implementation | [Shared platform adapter](../assets/source/journal/pocket/graphics/full.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/full.py))<br>[Native launcher](../assets/source/journal/pocket/graphics/run.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/run.py))<br>[Pixel composition](../assets/source/journal/pocket/graphics/pixel_compositor.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/pixel_compositor.py)) |
| Checks and fixtures | [Desktop acceptance runner](../assets/source/journal/pocket/graphics/check.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/check.py))<br>[Frontend tests](../assets/source/journal/pocket/tests/test_graphical_frontend.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_graphical_frontend.py))<br>[Build-input tests](../assets/source/journal/pocket/tests/test_graphics_build_inputs.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_graphics_build_inputs.py)) |
| Build inputs | [Native build](../assets/source/journal/pocket/graphics/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/build.py))<br>[Source identities](../assets/source/journal/pocket/graphics/SOURCES.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/SOURCES.json))<br>[Make targets](../assets/source/journal/pocket/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/Makefile))<br>[Optional Mac compute dependencies](../assets/source/journal/pocket/requirements-graphics-macos.txt.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/requirements-graphics-macos.txt)) |

[Build and test instructions](../pocket/graphics.md) · [Chronological source index](../reference/journal-sources.md#2026-11-07-native-desktop)

Source integration: [d7cbc64](https://github.com/gordol/n810-revival/commit/d7cbc64d8324e4f948426b37fc91c46fe32d73ff). The linked files are included in this checkout. Historical Mac captures and measurements describe their dated experimental runs; Linux software-GL checks and ARM cross-builds establish separate build/test results.

<a id="2026-11-07-surface-room"></a>

## Adding movement, aiming, and targets to Surface Room

[Read the journal entry](../posts/2026-11-07-surface-room.md)

| Material | Repository files |
|---|---|
| Implementation | [Target game](../assets/source/journal/pocket/graphics/native/game.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/native/game.c))<br>[Native input](../assets/source/journal/pocket/graphics/native/desktop_input.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/native/desktop_input.c))<br>[Room pixels](../assets/source/journal/pocket/graphics/native/room_pixels.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/native/room_pixels.c))<br>[Exploration controls](../assets/source/journal/pocket/graphics/explore_controls.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/explore_controls.py)) |
| Checks and fixtures | [Native input tests](../assets/source/journal/pocket/graphics/native/test_desktop_input.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/native/test_desktop_input.c))<br>[Desktop and Room integration](../assets/source/journal/pocket/graphics/check.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/check.py)) |
| Build inputs | [Native build](../assets/source/journal/pocket/graphics/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/build.py))<br>[Source identities](../assets/source/journal/pocket/graphics/SOURCES.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/SOURCES.json))<br>[Make targets](../assets/source/journal/pocket/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/Makefile))<br>[Optional Mac compute dependencies](../assets/source/journal/pocket/requirements-graphics-macos.txt.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/requirements-graphics-macos.txt)) |

[Build and test instructions](../pocket/graphics.md) · [Chronological source index](../reference/journal-sources.md#2026-11-07-surface-room)

Source integration: [d7cbc64](https://github.com/gordol/n810-revival/commit/d7cbc64d8324e4f948426b37fc91c46fe32d73ff). The linked files are included in this checkout. Historical Mac captures and measurements describe their dated experimental runs; Linux software-GL checks and ARM cross-builds establish separate build/test results. The earlier standalone hit/reset acceptance sequence has yet to join the integrated test runner.

<a id="2026-11-07-gpu-effects"></a>

## Moving desktop effects and terrain work onto the Mac GPU

[Read the journal entry](../posts/2026-11-07-gpu-effects.md)

| Material | Repository files |
|---|---|
| Implementation | [Flux producer](../assets/source/journal/pocket/shell/flux.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/flux.py))<br>[Flurry producer](../assets/source/journal/pocket/shell/flurry.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/flurry.py))<br>[DEM preparation and shading](../assets/source/journal/pocket/shell/desktop_elevation.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/desktop_elevation.py))<br>[GPU provider](../assets/source/journal/pocket/graphics/effects/provider.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/effects/provider.py))<br>[Effect shaders](../assets/source/journal/pocket/graphics/effects/gpu_effects.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/effects/gpu_effects.c))<br>[Map compute](../assets/source/journal/pocket/graphics/effects/map_gpu.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/effects/map_gpu.py))<br>[Terrain shading](../assets/source/journal/pocket/graphics/effects/terrain_shading.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/effects/terrain_shading.py))<br>[Pixel compute](../assets/source/journal/pocket/graphics/effects/pixel_gpu.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/effects/pixel_gpu.py)) |
| Checks and fixtures | [Integrated desktop check](../assets/source/journal/pocket/graphics/check.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/check.py))<br>[Frontend tests](../assets/source/journal/pocket/tests/test_graphical_frontend.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_graphical_frontend.py)) |
| Build inputs | [Native build](../assets/source/journal/pocket/graphics/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/build.py))<br>[Source identities](../assets/source/journal/pocket/graphics/SOURCES.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/SOURCES.json))<br>[Make targets](../assets/source/journal/pocket/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/Makefile))<br>[Optional Mac compute dependencies](../assets/source/journal/pocket/requirements-graphics-macos.txt.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/requirements-graphics-macos.txt)) |

[Build and test instructions](../pocket/graphics.md) · [Chronological source index](../reference/journal-sources.md#2026-11-07-gpu-effects)

Source integration: [d7cbc64](https://github.com/gordol/n810-revival/commit/d7cbc64d8324e4f948426b37fc91c46fe32d73ff). The linked files are included in this checkout. Historical Mac captures and measurements describe their dated experimental runs; Linux software-GL checks and ARM cross-builds establish separate build/test results. The detailed experimental effect/terrain comparison programs remain separate from the included desktop smoke check.

<a id="2026-11-09-gpu-desktop"></a>

## The N810 GPU runs the desktop

[Read the journal entry](../posts/2026-11-09-gpu-desktop.md)

| Material | Repository files |
|---|---|
| Implementation | [Desktop rendering](../assets/source/journal/pocket/graphics/gpu_scene.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/gpu_scene.py)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-09-gpu-desktop)

<a id="2026-11-09-symbian-runtime"></a>

## Symbian applications on the N810

[Read the journal entry](../posts/2026-11-09-symbian-runtime.md)

| Material | Repository files |
|---|---|
| Implementation | [Native runtime](../assets/source/journal/platform/symbian/runtime/runtime_main.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/symbian/runtime/runtime_main.cpp)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-09-symbian-runtime)
