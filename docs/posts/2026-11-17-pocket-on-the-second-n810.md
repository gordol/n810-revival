# Why enabling sound at boot stopped Pocket

*16–18 November 2026.*

We heard a test tone from the second N810 and rebooted it to check audio startup. The sound driver loaded, and the graphics launcher refused to start Pocket. An earlier audio configuration could lock up the tablet, so the launcher checked for the sound driver and exited if it found the module loaded.

The board driver had been looking for a codec named `tlv320aic3x-codec.1-0018`. We changed that name to match the one Linux registered (`tlv320aic3x.1-0018`) and corrected the device tree entry for McBSP2, the processor's serial audio port. The entry now assigns interrupt 62 to transmit and 63 to receive. When the driver is loaded, the graphics launcher runs `n810-audio pcm-status` to check that the boot service has approved the configuration. After a normal boot from slot A, Pocket drew its desktop and the `nokia` account could play sound and record from the microphone. With audio enabled, the GPU completed 50 jobs with all four fault counters at zero.

## Graphics on the two tablets

We repeated the [original GPU measurements](2026-11-10-gpu-residency-and-480mhz.md) on the second tablet using the same gears and 512-triangle terrain executables. Each rendered a 400 × 400 RGB565 window through Mesa on the MBX GPU, with Xorg displaying the image. The gears runs used identical Mesa libraries (verified by SHA-256). The original 480 MHz terrain run used a different Mesa build.

Each program submitted one GPU job per frame. After the first frame-rate report, we counted completed jobs over three consecutive 30-second intervals at each CPU clock. We also counted display-controller interrupts over the same intervals to measure transfers to the LCD.

| Workload | CPU clock | Original N810 FPS | Second N810 FPS | Second N810 display interrupts/s |
|---|---:|---:|---:|---:|
| Standard gears | 330 MHz | 36.25 | 38.24 | 23.50 |
| Rotating terrain | 330 MHz | 60.96 | 63.75 | 23.46 |
| Standard gears | 480 MHz | 42.74 | 45.34 | 25.71 |
| Rotating terrain | 480 MHz | 71.67 | 74.63 | 25.79 |

Pocket draws its 800 × 480 desktop directly to the framebuffer and can submit several GPU jobs per redraw. We counted completed frames inside Surface Room while turning the camera continuously in a 640 × 416 window, with the animated desktop background off. At 480 MHz Room rendered 131 frames in 45.65 seconds (2.87 FPS).

During testing, the person holding the tablet reported a blank LCD with the backlight on. Over SSH the agent could see that Pocket was running on `tty7` and that the panel had power. The framebuffer overlay was disabled. The agent enabled it and requested a display update, and the person at the tablet confirmed that Pocket was visible again.

## Station Map on the second tablet

We panned and zoomed Station Map and ran a terrain line-of-sight calculation using 4,097 elevation samples. Under load, the first sidebar overview took about five seconds to prepare. The worker produced the overview pixels, but the sidebar could discard them before its next redraw. Pocket now retains that image. The renderer also reuses the visible terrain, which removes the previous prefetch of nine neighboring views.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [map_pixels.py](../assets/source/journal/pocket/graphics/map_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/map_pixels.py))<br>[owner_session.py](../assets/source/journal/platform/bootstrap/gpu_runtime/owner_session.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/gpu_runtime/owner_session.py))<br>[n810-cpu-policy](../assets/source/journal/platform/scripts/n810-cpu-policy.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-cpu-policy))<br>[Desktop presentation and frame counter](../assets/source/journal/pocket/graphics/full.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/full.py))<br>[Surface Room pixel view](../assets/source/journal/pocket/graphics/room_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/room_pixels.py)) |
| Checks and fixtures | [test_gpu_audio_owner.py](../assets/source/journal/platform/bootstrap/test_gpu_audio_owner.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/test_gpu_audio_owner.py))<br>[test_map_pixel_handoff.py](../assets/source/journal/pocket/tests/test_map_pixel_handoff.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_pixel_handoff.py)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-17-pocket-on-the-second-n810)
<!-- journal-sources:end -->
