# Acceleration checkpoints

Updated 7 November 2026. The physical MBX performance observations below retain their original dates and workloads.

| Component | Recorded result | Work remaining |
|---|---|---|
| RGB console | Twelve exact RGB565 swatches; normal boot verified on 16 October. | Continued console regression coverage. |
| C cell compositor | Loaded and used by an early N810 application; retained buffers and changed-span output measured. | Whole-desktop responsiveness across workloads. |
| ARM VFP | Physical numerical tests and later Mesa native floating-point execution. | Cost reduction across the complete frame pipeline. |
| C55x DSP | Assembler, encoding checks, and numerical models. | Physical loading, execution, and output verification. |
| MBX rasterization | Standard 400 by 400 glxgears rendered on the Nokia. | Broader fixed-function state support and production integration. |
| VGP geometry | Diagnostic transforms and lighting compared with Mesa references; live GPU geometry in the 4 November gears runs. | Broader shader and geometry coverage. |
| Display transfer | Approximately 16.66 DISPC interrupts per second in the earlier comparison and 23.4 in the later GPU-geometry trials. | RFBI/DISPC crop and transfer investigation. |
| Native graphical desktop | Shared desktop model, direct Room pixels, and actual OS resize/input checks on Apple M1 Pro; source builds and explicit software-GL checks in Linux containers. | Physical Nokia frontend and mixed-state rendering acceptance. |
| Mac GPU effects and maps | Exact-output comparisons for Flux, Flurry, windows, DEM shading, and terrain; 738-frame combined experimental run. | Matched timing comparisons, remaining CPU preparation/repairs, and session-save notification follow-up. |
| Symbian GPU drawing | Physical checks of selected clears, retained surfaces, scissor rectangles, and large image sampling. | Full GPU-backed UI and interaction for the test applications. |

The [native frontend guide](../pocket/graphics.md) describes the included source and build commands. The [Mac GPU journal](../posts/2026-11-07-gpu-effects.md) lists the tested stages and CPU work retained. The [Symbian surface journal](../posts/2026-11-07-symbian-surfaces.md) records experimental driver results and failed attempts.

## Selected performance observations

| Workload | Observation | Measurement scope |
|---|---|---|
| Water scene, 20 October | 7.141 s geometry; 65.218 s to coherent app output. | One attended N810 launch. |
| Saved whole gears frame, 3 November | 0.118132 s for one GPU job and 390 primitives. | Offscreen saved-frame execution. |
| Native VFP gears checkpoint, 3 November | 29.2825 FPS median after two startup intervals. | Live application intervals; a slow interval reached 12.373 FPS. |
| Quiet control, 4 November | 30.7405 FPS median; 28.3327 completed GPU FPS across the measured window. | Pocket UI temporarily paused during the bounded run. |
| Quiet optimized, 4 November | 33.596 FPS median; 30.9953 completed GPU FPS across the measured window. | Same application, dimensions, and quality; Pocket UI resumed afterward. |

The later GPU-geometry checkpoint completed **1,864 frames in 60.711 seconds**, or **30.70 FPS** across two repeat intervals. Application CPU cost was **17.65 ms per frame**. The same-module polling-disabled control measured 28.77 FPS and 18.24 ms per frame. The [journal's repeated comparison](../posts/2026-11-04-gpu-performance.md#repeating-the-30-fps-result) includes the physical framebuffer, individual runs, failed alternatives, and downloadable measurements.

GPU completion, application-reported FPS, and physical display transfers measure different stages. The [performance entry](../posts/2026-11-04-gpu-performance.md) explains the background-load and profiling effects.
