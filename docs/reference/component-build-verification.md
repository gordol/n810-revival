# Component build verification

*Updated 7 November 2026. Kernel, frozen graphics, and HTIT build results below were recorded on 4 November; the native frontend and integrated Pocket checks were recorded on 7 November.*

| Component | Inputs checked | Result |
|---|---|---|
| Native graphical frontend | Included SDL/OpenGL adapter, font/mesh generators, and source-release build inputs. | Fresh-clone Mac build and focused frontend checks passed. Linux release-container and unpacked source-archive builds passed; GUI checks used software OpenGL. Physical Nokia acceptance remains separate. [Build guide](../pocket/graphics.md). |
| Integrated Pocket | Shared desktop and application sources, isolated test state. | 761 tests completed with 14 skips on 7 November. The [native desktop entry](../posts/2026-11-07-native-desktop.md) describes the integration and its limits. |
| Linux 5.15.224 | Pinned upstream archive, 55 maintained source changes, configuration and export whitelist. | Independent fresh-checkout ARM build; 199 modules and 35 clock-module symbol checks. [Full kernel record](kernel-build-verification.md). |
| MBX module checkpoint | Imported GPU source and the completed kernel build. | Module compilation passed; all 63 imported symbol versions matched. |
| Mesa checkpoint | Mesa 22.3.6 and 34 checksum-pinned Debian sysroot packages. | ARM `libGL.so.1` build passed. Required versions reached GLIBC 2.34, GLIBCXX 3.4 and CXXABI 1.3.9, within the selected Bookworm limits. |
| Verified 30 FPS snapshot | Sealed module/Mesa production source, standard-gears fixture and fifteen offline regression suites. | ARM module built with 64 matching symbol versions; Mesa rebuilt to the exact physical-test library hash. All fifteen suites pass. [Source and commands](../how-to/build-gpu-30fps.md). |
| HTIT hub | Imported ESP-IDF source and Espressif32 6.10.0. | Independent-clone firmware compilation passed. |
| HTIT executor | Imported microReticulum firmware, vendored executor libraries and Espressif32 6.12.0. | Independent-clone firmware compilation passed. The build used a locally generated private pairing PIN. |
| Map conversion | Builders and generated fictional OSM/height fixtures; public regional data is downloaded separately. | Offline fixture checks cover OSM import, geography/water tiles, terminal raster, terrain pyramid, bands and walk layers. Historical regional builds are recorded in the journal. |

These are compilation and local-test results. Physical installation and device acceptance have their own records in the journal. The two graphics checkpoints have separate source identities and build commands.

The kernel builder records the selected compiler, configuration, source hashes and output checks. The graphics builders record dependency hashes and symbol or library compatibility checks. The HTIT wrapper records the source tree, PlatformIO version, environment and output hashes in its private build directory. Generated firmware carries the locally selected PIN, so independently generated executor builds have distinct bytes.

The full Pocket and bundled radio suites use isolated temporary home directories. Packet fixtures contain synthetic traffic. Geography tests use public reference data and landmarks. The HTIT tests cover C/Python framing, an emulated radio engine, the official MeshCore client over local pseudo-terminals, CCMP validation and in-memory RSN peers. See the [validation guide](../how-to/validate.md) for the repeatable commands.

[HTIT build](../how-to/build-htit.md) · [Map build](../how-to/build-map-data.md)

## Fresh-checkout walkthrough, 7 November

This walkthrough cloned public revision `4b1262a` into an isolated Linux ARM64
Docker container. It followed the reader commands with fresh build directories.
The container had no host checkout, USB devices, or radio services mounted.
Native display checks used Xvfb and Mesa llvmpipe.

The first-session walkthrough launched with `make`, opened Help and Calendar,
searched Help for “pairing,” switched windows with F6 and Shift-F6, quit with
Ctrl-] then q, and restored all three windows on the next launch. The native
compositor built, and the graphical frontend passed its input, frame-border,
resize, and direct Room checks. `make gui` also launched under Xvfb as a normal
user. Map configuration, planning, and fictional elevation/geography pipeline
tests passed; this walkthrough did not download a regional map.

The manual Mesa command initially failed during configuration because the
selected Python/Meson environment lacked required compatibility dependencies.
The [corrected guide](../how-to/build-graphics.md) creates the same pinned virtual
environment used by the container build. With that environment, the frozen
30 FPS and earlier Mesa sources compiled successfully. All fifteen offline
checkpoint suites passed. Both frozen MBX modules compiled against the newly
built kernel, with 65 checked symbol versions for the 30 FPS module and 63 for
the earlier module.

The kernel build completed with 199 modules and 35 clock-module symbol checks.
Its combined image was 2,090,132 bytes, below the 2,095,104-byte limit. This is a
new compiler-run result; the earlier image sizes above remain historical results.
The executor and hub firmware both built, and the RSN checks passed 28 Python tests and
11 compiled-host tests.

### Failures exposed by the reader commands

The normal-user source run completed 198 test files: 178 passed, 19 failed, and
one (`test_station_terrain_tools.py`) exceeded the runner’s 240-second limit.
These are test-file counts, rather than individual test-case counts.

The broad source runner still reaches legacy regional-data tests. They expect
files such as `tahoma-3dep.json`, `walk-layers.n8w`, and `lakewood-relief.json.gz`
in historical paths that the source release does not populate. The new
area-selected map pipeline has its own passing fixture tests. Completing that
migration requires changes to the legacy tests and packaging inputs.

The HTIT wire-protocol host test fails with GCC 12: `wire.c` compares a `size_t`
loop index with `9 + f->len`, and its `-Werror` build rejects the signed/unsigned
comparison. The independent RSN checks pass. The host-test failure remains open.

Run the source suite as a normal user. Nokia session checks deliberately reject
root. Linux radio-proxy tests also need D-Bus and GLib bindings for the Python
interpreter actually running the suite; installing Debian bindings for a
different Python version leaves those imports unavailable.
