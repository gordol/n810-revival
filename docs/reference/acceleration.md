# Acceleration checkpoints

Reconciled on 4 November 2026 from the dated development records.

| Component | Recorded result | Work remaining |
|---|---|---|
| RGB console | Twelve exact RGB565 swatches; normal boot verified on 16 October. | Continued console regression coverage. |
| C cell compositor | Loaded and used by an early N810 application; retained buffers and changed-span output measured. | Whole-desktop responsiveness across workloads. |
| ARM VFP | Physical numerical tests and later Mesa native floating-point execution. | Cost reduction across the complete frame pipeline. |
| C55x DSP | Assembler, encoding checks, and numerical models. | Physical loading, execution, and output verification. |
| MBX rasterization | Standard 400 by 400 glxgears rendered on the Nokia. | Broader fixed-function state support and production integration. |
| VGP geometry | Diagnostic transforms and lighting compared with Mesa references; live GPU geometry in the 4 November gears runs. | Broader shader and geometry coverage. |
| Display transfer | Approximately 16.66 DISPC interrupts per second in the earlier comparison and 23.4 in the later GPU-geometry trials. | RFBI/DISPC crop and transfer investigation. |

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
