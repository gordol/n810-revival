# The N810 GPU runs the desktop

*9 November 2026.*

The MBX work now powers Pocket's graphical desktop on the physical N810.
The driver that first ran glxgears is handling the framework's windows,
text, images and interactive scenes. Surface Room and its target game use that
same rendering framework.

The recent desktop work raised the measured rate from 18.93 to 20.97 frames per
second while reducing application CPU time from 38.76 to 33.86 milliseconds per
redraw. Rendering quality stayed the same. These numbers describe the tested
desktop workload; glxgears has its own workload and measurements.

The improvements come from retaining work between frames: reusing prepared
commands and image resources, batching draws, and updating the regions that
changed. Less CPU preparation leaves more time for applications and input.

MBX produces the image. The OMAP display subsystem sends it to the LCD through
RFBI, the parallel display interface. Work on partial display transfers targets
that next stage of the pipeline.

The installed N810 supervisor selects the graphics release, starts Pocket and
restores the console when it exits. The [run guide](../how-to/run-n810-gpu.md)
gives the command. For another tablet, begin with [N810 setup](../start.md).

This also gives the Symbian runtime a graphics backend. The
[next entry](2026-11-09-symbian-runtime.md) follows ChessGenius through that path.

<!-- journal-sources:start -->
## Follow the implementation

| Material | Repository files |
|---|---|
| Implementation | [Desktop rendering](../assets/source/journal/pocket/graphics/gpu_scene.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/gpu_scene.py)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-09-gpu-desktop)
<!-- journal-sources:end -->
