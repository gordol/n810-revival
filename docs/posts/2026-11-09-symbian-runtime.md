# Bringing the native Symbian runtime into the N810 tree

*9 November 2026.*

The native Symbian runtime and the GPU desktop now share an integration branch.
The runtime executes ARM application code on the N810 and uses the MBX graphics
path. Firmware, system libraries and application installers remain private inputs.

A matched ChessGenius menu test used eleven controls, with logging, tracing and
sampling disabled. The repeated three-Down pass averaged 1.20 seconds to the first
changed framebuffer pixel. The runtime used 0.893 CPU seconds per action and its
native workers used another 0.090 seconds. Runtime RSS was 40.36 MiB. That pass
had no major page faults. Settings and final images matched all 76,800 application
pixels against the reference. These measurements do not establish gameplay FPS.

Input left the control queue in 14.9 milliseconds. Most of the delay therefore
remains after delivery, in runtime and drawing work. The next performance test
must measure that work rather than add input polling or reduce image quality.

The repository now keeps one runtime source directory under `platform/symbian`.
The Mac experiment and checkpoint reports have been removed from this integration.
The EKA2L1 patch records changes against its pinned upstream revision; it is a
build input, not a second runtime driver. A portable build and managed Pocket
launch handoff still require implementation and physical acceptance.

The GPU module and framebuffer driver have different jobs. MBX submits rendering
work. OMAP framebuffer/DSS drives the LCD through RFBI. The partial-update kernel
change modifies that existing display path; it does not add a second framebuffer
owner. Its activation and acceptance must be reported separately from MBX tests.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [Native runtime](../assets/source/journal/platform/symbian/runtime/runtime_main.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/symbian/runtime/runtime_main.cpp))<br>[GPU desktop owner](../assets/source/journal/pocket/platform/n810/native_owner.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/platform/n810/native_owner.py)) |
| Checks and fixtures | [Address layout test](../assets/source/journal/platform/symbian/runtime/test_native_address_layout.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/symbian/runtime/test_native_address_layout.cpp)) |
| Build inputs | [Upstream revision](../assets/source/journal/platform/symbian/PROVENANCE.json.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/symbian/PROVENANCE.json)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-09-symbian-runtime)

Launch handoff and physical boot-chain verification remain incomplete.
<!-- journal-sources:end -->
