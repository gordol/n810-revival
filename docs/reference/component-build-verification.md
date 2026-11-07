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
