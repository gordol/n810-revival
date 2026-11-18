# The speaker worked. Where did the desktop go?

*16–18 November 2026. Sound, graphics and maps on the second Nokia N810.*

We heard the test tone. Then we rebooted the N810 to see whether sound would come back on its own. It did. Pocket didn't.

The clue was in the graphics launcher. An earlier audio configuration could hard-lock the tablet, so the launcher refused to start whenever it found the sound driver loaded. Making sound start reliably at boot had made the desktop stop reliably at boot.

## What should the launcher check?

The audio repair had corrected two details of how Linux described the board. The driver was looking for a codec named `tlv320aic3x-codec.1-0018`, while Linux had registered it as `tlv320aic3x.1-0018`. The processor's serial audio port, McBSP2, also had an extra interrupt in the device tree. The corrected entry identifies the port and assigns interrupt 62 to transmit and 63 to receive.

That gave the launcher a more useful question. When the driver is loaded, it now asks `n810-audio pcm-status` whether the boot service validated the audio configuration. On the next slot A boot, Pocket drew its desktop. The ordinary `nokia` account could play sound and record from the microphone. The GPU completed 50 jobs with all four fault counters at zero. We checked those changes on both SD roots updated in place. A fresh installation is a separate test.

## Fifty GPU jobs tell us the driver is alive. How fast is it?

Doom ran once we supplied its missing engine, bridge and game data. It still felt slow, as did the animated Flux background. Had we lost the graphics gains from the first tablet? We had kept the original gears and rotating-terrain programs, so we could ask both machines to draw the same scenes.

Each program rendered a 400 × 400 RGB565 window. Mesa used the MBX GPU for transformation, lighting and rasterization, and a temporary Xorg server displayed the result. Each completed GPU job represented one frame in **these two programs**. On the second tablet we counted jobs over three consecutive 30-second intervals at each CPU clock, starting after the first frame-rate report. [Original measurements and framebuffer captures](2026-11-10-gpu-residency-and-480mhz.md)

| Workload | CPU clock | Original N810 FPS | Second N810 FPS | Second N810 display interrupts/s |
|---|---:|---:|---:|---:|
| Standard gears | 330 MHz | 36.25 | 38.24 | 23.50 |
| Rotating terrain | 330 MHz | 60.96 | 63.75 | 23.46 |
| Standard gears | 480 MHz | 42.74 | 45.34 | 25.71 |
| Rotating terrain | 480 MHz | 71.67 | 74.63 | 25.79 |

Gears gave us the cleanest comparison. The executable and Mesa library matched the original run by SHA-256, and the second tablet slightly exceeded the first at both clocks. The terrain executable matched too, though the original 71.67 FPS run used a different Mesa library build. All twelve new samples finished with zero GPU faults. The last column measures activity farther downstream: at nearly 75 completed terrain frames a second, we counted about 26 display-transfer interrupts a second.

Pocket takes a different route to the LCD. It composes an 800 × 480 desktop and submits updates directly to the framebuffer. One desktop redraw can submit several GPU jobs, so we needed a counter closer to the application. Counting finished frames inside Pocket instead gave **131 Surface Room frames in 45.65 seconds**, or **2.87 FPS**, while turning the camera in a 640 × 416 window at 480 MHz. That number describes the Room proof of concept. Gears answers the narrower question about whether the standalone graphics path survived the move.

The person at the tablet caught something the agent at the SSH prompt couldn't see. Pocket still had a running process, the panel reported power, and the backlight was on. The LCD was blank. The framebuffer overlay that supplies the pixels was disabled. Restoring it and requesting a display update made Pocket visible again. That last observation came from someone looking at the glass.

## The map had already done the work

Station Map could pan, zoom and calculate a terrain line of sight from 4,097 elevation samples. Yet opening the map could leave us looking at “Preparing map features,” and its little sidebar overview took about five seconds the first time under load. The worker could finish drawing the overview only for the sidebar to discard the pixels before the next redraw. Keeping that image and reusing visible terrain eliminated duplicate work, including an attempt to prepare nine neighboring views.

The original tablet had been useful in two quite different ways. Its filesystem told us [which programs and data to put back](2026-11-16-second-n810.md). Its saved benchmarks let us decide where to look when the new machine felt slow. In the map's case, the wait was visible before the GPU even had the features to draw.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [map_pixels.py](../assets/source/journal/pocket/graphics/map_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/map_pixels.py))<br>[owner_session.py](../assets/source/journal/platform/bootstrap/gpu_runtime/owner_session.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/gpu_runtime/owner_session.py))<br>[n810-cpu-policy](../assets/source/journal/platform/scripts/n810-cpu-policy.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-cpu-policy))<br>[Desktop presentation and frame counter](../assets/source/journal/pocket/graphics/full.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/full.py))<br>[Surface Room pixel view](../assets/source/journal/pocket/graphics/room_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/room_pixels.py)) |
| Checks and fixtures | [test_gpu_audio_owner.py](../assets/source/journal/platform/bootstrap/test_gpu_audio_owner.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/test_gpu_audio_owner.py))<br>[test_map_pixel_handoff.py](../assets/source/journal/pocket/tests/test_map_pixel_handoff.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_pixel_handoff.py)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-17-pocket-on-the-second-n810)
<!-- journal-sources:end -->
