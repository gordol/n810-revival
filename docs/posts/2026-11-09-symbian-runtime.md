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


## 10 November: testing the 480 MHz setup

We repeated the earlier ChessGenius test twice with the exact same native ARM
runtime, Mesa library, 240×320 surface and Down/Up input sequence. Pocket and
radio owners stayed stopped. Debug logging and sampling were off. The new kernel
reported 480 MHz at both ends of each sample; no frequency setting changed.

| Measurement | Earlier 330 MHz setup | Two 480 MHz runs |
| --- | ---: | ---: |
| CPU time in the 60-second application run | 24.46 s | 19.79 / 18.26 s |
| First completed image | 16.87 s | 12.89 / 10.91 s |
| Down → next completed image | 1.86 s | 1.86 / 1.41 s |
| Up → next completed image | 2.84 s | 1.19 / 0.97 s |
| Runtime peak RSS | 40.8 MiB | 52.5 / 52.6 MiB |
| Major page faults | 1,736 | 871 / 811 |

CPU time fell 19–25%, and Up responded faster in both runs. Down improved in one
run. These are offscreen completed-image timings, not physical button-to-LCD
latency or gameplay FPS. All 230,400 mask-fixture pixels matched exactly; both
applications exited normally and the module unloaded without a reboot.

This compares complete setups, not frequency alone: the kernel and GPU service
configuration also changed. GPU submissions rose from 191 to 259, and counters
reported two readbacks totaling 462,720 bytes per run, versus none previously.
Memory use also increased. Those discrepancies need tracing before calling this
an unchanged rendering pipeline or enabling the newer cache optimizations.


## 11 November: tracing the extra reads

A bounded Nokia diagnostic traced both 231,360-byte reads to Mesa's ordinary
render-target path. Runtime surface logging identified a 240×241 temporary made
by age-based redraw-history compaction. That temporary does not fit the retained
128×128 or 240×320 image classes.

An opt-in runtime change keeps up to 64 stored commands instead of rasterizing
that small history merely because it aged. The existing segment limit and
large-history compaction remain. All 5,656 sanitized history cases preserved
command order, and the ARM build passed. The change stays disabled by default.

The device comparison stopped before loading its test module because the kernel
had recorded a zram decompression failure during swap-in. No reboot was issued;
the GPU was unloaded and Pocket stayed stopped. Physical acceptance and the
memory-growth investigation remain open. The sampled resident memory includes
anonymous heaps and mapped code, so peak RSS alone does not establish an
allocation leak or attribute the increase to those two reads.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [Native runtime](../assets/source/journal/platform/symbian/runtime/runtime_main.cpp.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/symbian/runtime/runtime_main.cpp)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-09-symbian-runtime)
<!-- journal-sources:end -->
