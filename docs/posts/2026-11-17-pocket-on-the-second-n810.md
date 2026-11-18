# Getting Pocket running on a second N810

*11–18 November 2026.*

On one boot I could type on the second N810. On the next, the power button brought up the menu and I couldn't even move the selection with the D-pad. We'd rebooted because SSH was slow. We hadn't changed the kernel between boots.

We had a working keyboard on the original N810, so we went looking for what we'd left out of the installer. The old tablet had two copies of Pocket and experimental Mesa libraries in the home directory. An agent followed the graphics launcher through a read-only backup to find the release it actually used. The APRS receiver (which collects station reports over amateur radio) took a little more digging. Its startup script lived in `/etc/boot.d`, where `/etc/rc.local` ran it at boot. That script started a supervisor as root, and the supervisor ran the receiver as `nokia` out of the home directory. A list of installed packages would have missed that arrangement.

The keyboard setup on the two tablets matched down to the debounce interval (30 milliseconds). The original kernel lived in flash, outside our filesystem backup, so we rebuilt it with the original compiler and changed the root-device selection for the second tablet. We checked the running build against `/sys/kernel/notes`. The LM8323 keyboard controller still didn't acknowledge reads on the I²C bus, and its interrupt count stayed at zero. We'd reached the point where Linux needed an answer from the chip before a key mapping could do anything.

The keyboard had worked on a Linux boot immediately after the installer ran Maemo in RAM. Days later we could type at the internal recovery console, too. During recovery the driver logged `chip lost config; reinitializing`. At that point we already had a kernel running with a working keyboard. Why boot another one to run Debian from the SD card? We changed startup so the flashed kernel selects a Debian root filesystem on the card before starting services and keeps control of the keyboard across that switch. Both Debian slots use modules built for that kernel. We later typed `htop` in Pocket's Terminal on the second tablet. What caused the controller to stop answering on the earlier boots is still an open question.

## A test tone and a missing desktop

We heard a test tone, rebooted to check that sound came up on its own, and lost the desktop. The graphics launcher had a check we'd added when an earlier audio configuration could lock up the tablet. As soon as it saw the sound driver loaded, it refused to start Pocket.

Getting sound working had taken two corrections. We changed the codec name in the board driver to the one Linux registered (`tlv320aic3x.1-0018`) and fixed the interrupts for the processor's serial audio port (McBSP2 uses 62 for transmit and 63 for receive). We changed the launcher to run `n810-audio pcm-status` when it finds the driver loaded, so it can check whether the boot service approved that configuration. We tried the repair on Debian slot B first. Once Pocket started and passed its GPU check, we marked B good and booted the repaired slot A. Pocket drew its desktop, the `nokia` account could play and record audio, and the GPU completed 50 jobs with all four fault counters at zero.

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

During testing I could see the backlight, but the screen was blank. Over SSH the agent could see Pocket running on `tty7` with power to the panel. The framebuffer overlay was disabled. The agent enabled it and requested a display update, and I could see Pocket again.

We also tried Station Map with the maps on their own partition, accessible from either Debian slot. We panned and zoomed, then ran a terrain line-of-sight calculation with 4,097 elevation samples. Under load the first sidebar overview took about five seconds to prepare. The worker finished drawing it, but the sidebar could discard the pixels before its next redraw. Pocket now keeps the finished image for that redraw.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [build.py](../assets/source/journal/platform/kernel/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/build.py))<br>[ab_early.py](../assets/source/journal/platform/bootstrap/ab_early.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/ab_early.py))<br>[map_pixels.py](../assets/source/journal/pocket/graphics/map_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/map_pixels.py))<br>[owner_session.py](../assets/source/journal/platform/bootstrap/gpu_runtime/owner_session.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/gpu_runtime/owner_session.py))<br>[n810-cpu-policy](../assets/source/journal/platform/scripts/n810-cpu-policy.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-cpu-policy))<br>[Desktop presentation and frame counter](../assets/source/journal/pocket/graphics/full.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/full.py))<br>[Surface Room pixel view](../assets/source/journal/pocket/graphics/room_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/room_pixels.py)) |
| Checks and fixtures | [test_build.py](../assets/source/journal/platform/kernel/test_build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/test_build.py))<br>[test_ab_early.py](../assets/source/journal/platform/bootstrap/test_ab_early.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/test_ab_early.py))<br>[test_gpu_audio_owner.py](../assets/source/journal/platform/bootstrap/test_gpu_audio_owner.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/test_gpu_audio_owner.py))<br>[test_map_pixel_handoff.py](../assets/source/journal/pocket/tests/test_map_pixel_handoff.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_pixel_handoff.py)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-17-pocket-on-the-second-n810)

[Installing the two Debian slots](../how-to/install-n810-ab.md)
<!-- journal-sources:end -->
