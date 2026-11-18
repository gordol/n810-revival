# Running Pocket on the second N810

*16–18 November 2026. Pocket on the physical Nokia N810.*

Surface Room ran in a window on the second N810. At full screen, Pocket handed the renderer an 800 × 480 region. The largest region it accepted was 400 × 400. Splitting the draw into smaller regions let Room fill the display, and target practice worked on the tablet. Doom also ran once the installer included its engine, bridge and game data. Doom and the Flux background were both visibly slow.

On the original N810 at 480 MHz, gears averaged 42.74 frames per second and rotating terrain averaged 71.67, each in a 400 × 400 target. [Original GPU measurements](2026-11-10-gpu-residency-and-480mhz.md)

## 18 November: measure Surface Room on the installed desktop

At 480 MHz, Surface Room rendered **2.87 frames per second** while the camera turned continuously. Pocket drew the desktop directly to the 800 × 480 framebuffer with the animated background off. The Room window measured 82 × 28 terminal cells, giving the scene a 640 × 416 pixel interior. We counted completed Room frames and desktop presentations separately after four seconds of warm-up.

| Sample | Elapsed seconds | Room frames | Desktop frames |
|---|---:|---:|---:|
| 1 | 15.37 | 44 | 45 |
| 2 | 15.28 | 44 | 44 |
| 3 | 15.00 | 43 | 43 |
| Total | 45.65 | 131 | 132 |

The desktop averaged 2.89 frames per second over the same interval. This workload includes Pocket's window composition and display submission. The original gears and terrain tests rendered standalone windows through Xorg.

In an earlier check we sent four turn inputs a second to Surface Room at 330 MHz. In three ten-second intervals the MBX driver completed 195, 195 and 197 jobs. The display controller counted 48 interrupts in each interval. All four GPU fault counters stayed at zero. A Pocket redraw can submit several jobs, so those counts cannot be compared directly with the original tablet's gears frame rate.

The LCD subsequently showed only the backlight. Pocket still owned tty7 and the panel was powered. The framebuffer was in manual update mode with its overlay disabled. Restoring the overlay and automatic updates preserved the running desktop. After switching the CPU back to 480 MHz, the display interrupt count advanced by 120 between readbacks and the framebuffer contained image data.

## Repeat the standalone GPU tests

We ran the original gears and 512-triangle terrain executables in 400 × 400 RGB565 windows. A temporary Xorg framebuffer server displayed the images. Mesa's MBX path transformed, lit and rasterized the geometry. Each frame submitted one GPU job. We sampled the completed-job counter over three consecutive 30-second intervals per workload and CPU clock, after the first FPS report. The display controller has its own interrupt counter.

| Workload | CPU clock | Original N810 FPS | Second N810 FPS | Second N810 display interrupts/s |
|---|---:|---:|---:|---:|
| Standard gears | 330 MHz | 36.25 | 38.24 | 23.50 |
| Rotating terrain | 330 MHz | 60.96 | 63.75 | 23.46 |
| Standard gears | 480 MHz | 42.74 | 45.34 | 25.71 |
| Rotating terrain | 480 MHz | 71.67 | 74.63 | 25.79 |

The second N810 ran its installed kernel-matched MBX module. The gears executable and Mesa library matched the original gears run by SHA-256. The terrain executable also matched. Its original 71.67 FPS run recorded a different Mesa library hash, so the terrain figures include that software difference. All four GPU fault counters remained zero throughout the timed samples.

## Load the station map and its overview

The new tablet could pan and zoom the map and calculate a terrain line of sight from 4,097 elevation samples. Opening the map still took long enough to see where it waited: “Preparing map features.” The first sidebar overview took about five seconds under load. Its worker could finish preparing the pixels only for the sidebar to discard them before the next draw. Pocket now keeps the prepared overview and reuses the visible terrain instead of preparing nine neighboring views.

The new tablet showed about 51 MB resident and 105 MB swapped in an earlier check, and 31 MB resident and 10 MB swapped after the Mesa repair. The desktop was at a different stage in each check. A repeatable comparison needs the same map view and the same point in loading.

When a failed app returned to the desktop, its panels could still be laid out for the old dimensions. Pocket now lays them out again before drawing.

Bluetooth Settings needed direct access to the local adapter even when the APRS service was idle. The installer now provisions the tablet's persistent Bluetooth address before the controller registers. Settings sends adapter changes to BlueZ with the property value wrapped in the variant type its interface expects.

## Start the GPU desktop with audio enabled

The speaker played a test tone on the second N810. After a reboot the sound driver loaded automatically, but the Pocket desktop never appeared. Its launcher still checked for the presence of the audio driver and stopped when it found it. That check dated from an earlier audio configuration that could lock up the tablet.

Two details in the kernel described how sound reached the speaker. The board driver looked for the codec under the name `tlv320aic3x-codec.1-0018`. Linux had registered it as `tlv320aic3x.1-0018`. The device tree also described an extra interrupt on McBSP2, the processor's serial port for audio. The corrected description identifies the port as `mcbsp2` and gives it transmit interrupt 62 and receive interrupt 63.

The boot service checks that configuration before enabling playback and capture. The GPU launcher now runs `n810-audio pcm-status` when the sound driver is loaded. A failed check still stops the desktop. On slot A, a normal reboot brought up both sound and the GPU-rendered desktop. Playback and microphone capture ran under the ordinary `nokia` account. With audio enabled, the graphics check recorded 50 completed GPU jobs and zero faults.

These checks used the SD slots updated in place. Installation from a fresh image containing the final fixes remains to be tested.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [map_pixels.py](../assets/source/journal/pocket/graphics/map_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/map_pixels.py))<br>[owner_session.py](../assets/source/journal/platform/bootstrap/gpu_runtime/owner_session.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/gpu_runtime/owner_session.py))<br>[n810-cpu-policy](../assets/source/journal/platform/scripts/n810-cpu-policy.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-cpu-policy))<br>[Desktop presentation and frame counter](../assets/source/journal/pocket/graphics/full.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/full.py))<br>[Surface Room pixel view](../assets/source/journal/pocket/graphics/room_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/room_pixels.py)) |
| Checks and fixtures | [test_gpu_audio_owner.py](../assets/source/journal/platform/bootstrap/test_gpu_audio_owner.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/test_gpu_audio_owner.py))<br>[test_map_pixel_handoff.py](../assets/source/journal/pocket/tests/test_map_pixel_handoff.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_pixel_handoff.py)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-17-pocket-on-the-second-n810)
<!-- journal-sources:end -->
