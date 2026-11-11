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

The managed launcher now accepts requests from Pocket's menu and Make. It
releases the desktop's rendering context, runs the application, then restores
the saved desktop. See [Run Symbian applications](../how-to/run-symbian.md).

For the tablet setup and graphical desktop, follow [N810 setup](../start.md) and
[the GPU run guide](../how-to/run-n810-gpu.md).

## 10 November: resident GPU masks

Masked images now stay in GPU storage through composition and drawing. Native-size
images reuse bounded staging storage, and font atlases pack the same glyphs more
compactly. Physical pixel checks matched exactly.

Masked sprites can now share a GPU atlas page and one composition job. Exact
image, mask and generation matches also reuse completed pages across draw barriers.
The Nokia passed 230,400 pixel comparisons with unchanged output.

In an isolated 60-second ChessGenius test, mask pages reduced GPU submissions from
228 to 196 and CPU time from 25.87 to 24.74 seconds, with no mask readbacks. A
separate matched test of completed-page reuse reduced CPU time another 3%.
Input still takes seconds and varies with paging; reducing runtime handoffs and
the remaining redraw work is the next priority. These measurements used completed
GPU frames offscreen, with Pocket stopped and debug logging disabled.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [Native runtime](../assets/source/journal/platform/symbian/runtime/runtime_main.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/symbian/runtime/runtime_main.cpp)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-09-symbian-runtime)
<!-- journal-sources:end -->
