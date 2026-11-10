# Host versus Nokia ChessGenius baseline

The physical Nokia baseline is complete. The host CPU renderer is still being
built; no host performance result or host/device speed ratio is established.

## Physical run

Measured on 2026-11-09 Pacific time (2026-11-10 UTC), with native ARM guest
execution, MBX rendering, full GPU verification, the batching experiment off,
and debug logging, sampling, and tracing off. The working installed graphics
stack was not replaced. The isolated service completed 206 GPU jobs.

Eleven bounded ChessGenius controls used eight-second accounting windows.
The repeated three-Down pass measured:

| Metric | Result |
| --- | ---: |
| Mean first changed framebuffer pixel | 1.2018 s |
| Mean control-file consumption | 14.89 ms |
| Runtime process CPU per action | 0.8933 s |
| Native worker CPU per action | 0.0900 s |
| Graphics thread CPU per action | 0.5233 s |
| Main thread CPU per action | 0.3200 s |
| Runtime RSS at final sample | 40.36 MiB |
| Runtime major faults during repeated pass | 0 |

Thread CPU is included in runtime process CPU, not additional to it. Worker
CPU is separate. Accounting windows include subsequent work and idle time;
first-pixel latency does not prove whole-frame completion or LCD scanout.
This static-menu test does not establish gameplay FPS.

Both settings and final captures matched all 76,800 app-region pixels against
the accepted reference. No GPU or graphics errors, routine debug output, or
CPU samples were recorded. Process/import loading took 12.328 s; this excludes
supervisor GPU bring-up and does not establish first-visible-frame time.

Cleanup returned to tty1, unloaded the probe, and verified the same boot.
Pocket and radios were not restarted. The device lock was released.

## Host comparison boundary

The host variant runs in the Mac's AArch64 Linux VM with the dyncom ARM
interpreter and explicit softpipe CPU rendering. It shares runtime code and
fixed-function draw semantics but uses a private RGBA memory sink instead of
the Nokia RGB565 framebuffer and RFBI/LCD. Native guest execution and device
GPU costs therefore cannot be inferred from its total wall time.

Private ROM, DLLs, app installers, and captured images remain outside this
directory and distribution artifacts. Only source and aggregate measurements
are recorded here.
