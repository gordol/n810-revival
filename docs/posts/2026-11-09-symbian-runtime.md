# Symbian applications on the N810

*9 November 2026.*

The [GPU desktop work](2026-11-09-gpu-desktop.md) provides the rendering path for
another use: running Symbian applications on the N810's ARM processor.

The compatibility layer uses EKA2L1's application loader and system services,
with a native ARM execution path and adapters for our MBX driver. It loads the
application, resolves its library imports, handles requests and sends drawing
operations to the GPU.

ChessGenius reaches its menus and board on the tablet. The current menu test
averages about 1.2 seconds for a visible response and uses about 40 MiB of runtime
memory. Input reaches the queue in about 15 milliseconds, so reducing redraw and
runtime work remains the priority. The application needs faster responses before
this is comfortable for everyday use.

Users supply compatible Symbian system libraries and application installers in
private storage. The runtime source is under `platform/symbian/`.

The next integration step is a Pocket launcher that hands graphics ownership to
the runtime and returns it when the application closes. Once that handoff is
ready, the same launch command will serve the desktop menu and Make.

For the tablet setup and graphical desktop, follow [N810 setup](../start.md) and
[the GPU run guide](../how-to/run-n810-gpu.md).

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [Native runtime](../assets/source/journal/platform/symbian/runtime/runtime_main.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/symbian/runtime/runtime_main.cpp)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-09-symbian-runtime)
<!-- journal-sources:end -->
