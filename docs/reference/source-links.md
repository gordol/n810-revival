# Source and upstream reading

The project repository is [gordol/n810-revival on GitHub](https://github.com/gordol/n810-revival). The manuals, [RGB console patch](console-rgb-patch.md), and [journal source excerpts](journal-sources.md) are also available inside this site.

## Follow the code

| Area | Documentation in this site | Implementation on GitHub |
|---|---|---|
| RGB console | [Patch, files, and validation](console-rgb-patch.md) | [October kernel patch](https://github.com/gordol/n810-revival/blob/main/platform/patches/console-rgb.patch) |
| Desktop startup | [First session](../tutorials/first-session.md) | [Launcher](https://github.com/gordol/n810-revival/blob/main/pocket/shell/launch.py) |
| Remote services | [Connections](../pocket/connections.md) | [SSH attachment](https://github.com/gordol/n810-revival/blob/main/pocket/shell/device_connection.py) |
| Cell composition | [Rendering](../explanation/rendering.md) | [Native cell engine](https://github.com/gordol/n810-revival/blob/main/pocket/shell/native/cell_engine.c) |
| Saved desktop state | [Idle-work investigation](../posts/2026-10-20-water-and-idle.md) | [Session collection and saving](https://github.com/gordol/n810-revival/blob/main/pocket/shell/session.py) |
| Map preparation | [Map investigation](../posts/2026-10-24-maps-with-an-edge.md) | [Offline renderer](https://github.com/gordol/n810-revival/blob/main/pocket/shell/offline_map.py) |
| Touch acquisition | [Touch implementation](../pocket/touch-acquisition.md) | [Process adapter](https://github.com/gordol/n810-revival/blob/main/pocket/shell/touch_process.py) |
| External radio execution | [Executor protocol](../pocket/external-node.md) | [Framed node connection](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/apps/domains/reticulum/node_transport.py) |
| Native Reticulum | [Build and operation](../pocket/native-reticulum.md) | [Build integration and dependency pins](https://github.com/gordol/n810-revival/tree/main/pocket/shell/native/reticulum) |
| Tablet services | [Platform file map](platform-files.md) | [OS-side commands](https://github.com/gordol/n810-revival/tree/main/platform/scripts) |

Links to `main` show the current repository code. Journal excerpts pinned to a commit identify the source from which they were taken. A section labeled “Reading the current code” connects a historical problem to today's implementation.

## Historical source and build inputs

The repository contains Pocket, platform runtime files, maintained kernel inputs, HTIT firmware, the frozen MBX/Mesa checkpoints, and the earlier sidebar, phone-terminal, CPU and DSP experiments. The [chronological journal index](journal-sources.md) links each post to its code, tests and build inputs, including local source copies.

The [checkpoint test guide](../how-to/test-journal-checkpoints.md) covers the flash readers, console harness, platform tests, historical desktop, and microLXMF reproductions. It identifies the additional inputs required by the historical rescue image and device-specific tools. The [map build guide](../how-to/build-map-data.md) describes the retained elevation export and the original terrain data still needed for an exact historical rebuild.

## Read about the underlying systems

| Subject | Primary reference |
|---|---|
| OMAP2420 hardware | [TI architecture brief](https://www.ti.com/pdfs/wtbu/TI_omap2420.pdf) |
| Linux interrupts | [Generic IRQ handling](https://docs.kernel.org/core-api/genericirq.html) |
| Linux clocks | [Common clock framework](https://docs.kernel.org/driver-api/clk.html) |
| CPU/device memory | [Linux 5.15 DMA guide](https://docs.kernel.org/5.15/core-api/dma-api-howto.html) |
| Console graphics | [Framebuffer console](https://docs.kernel.org/fb/fbcon.html) |
| Framebuffer X11 | [Xorg fbdev manual](https://xorg.freedesktop.org/archive/X11R7.5/doc/man/man4/fbdev.4.html) |
| ARM compilation | [GCC ARM options](https://gcc.gnu.org/onlinedocs/gcc/ARM-Options.html) |
| Mesa drivers | [Mesa platforms and drivers](https://docs.mesa3d.org/systems.html) |
| Remote terminals | [OpenSSH manual](https://man.openbsd.org/ssh), [tmux manual](https://man.openbsd.org/tmux.1) |
| Reticulum networking | [Reticulum manual](https://reticulum.network/manual/) |
| ESP32 memory | [Espressif external RAM guide](https://docs.espressif.com/projects/esp-idf/en/v4.4.7/esp32/api-guides/external-ram.html) |

The entries also link these references at the point where a mechanism first matters, so a reader can continue from the explanation directly into the relevant API or hardware documentation.
