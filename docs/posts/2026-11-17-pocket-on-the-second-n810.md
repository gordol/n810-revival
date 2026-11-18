# Getting Pocket running on a second N810

*11–18 November 2026.*

I tried our installer on a second N810 to see whether it could reproduce the Pocket setup I'd been using on the first.

## The keyboard after a reboot

The installer ran Maemo (Nokia's operating system) in RAM before it started Debian. I could type on that first Debian boot. I rebooted because SSH was slow, and when I opened the power menu the D-pad wouldn't move the selection. The keyboard had stopped responding at the Debian login prompt as well. Both boots used the same kernel.

We checked the settings from the working tablet, including the 30-millisecond interval the controller uses to filter switch bounce. Those matched. The backup didn't include the original kernel because Nokia kept it in flash, so we rebuilt it with the original compiler and changed the device it used for the Debian root filesystem. Codex checked the running kernel's build ID in `/sys/kernel/notes` after the reboot. Reads from the LM8323 keyboard controller went unacknowledged on the I²C bus, and its interrupt count stayed at zero. There were no key presses for a console keymap to translate.

A few days later I could type at the internal recovery console. The keyboard driver had reported `chip lost config; reinitializing` during recovery. Our installer was about to boot a second kernel to start Debian from the SD card, which would make Linux initialize the hardware again. We changed the boot sequence to keep the kernel that was already driving the keyboard. It now mounts Debian from the card before starting services.

The card holds two Debian installations (slots A and B), so we can try an update in one and still boot the other. Both use modules built for the kernel in flash. I later typed `htop` in Pocket's Terminal. That verified keyboard input all the way into an application, although we never isolated the cause of those earlier unanswered reads.

## Starting Pocket with sound enabled

To get a test tone out of the second tablet, we changed the codec name in the board driver to the one Linux registered (`tlv320aic3x.1-0018`) and corrected the interrupts for the processor's serial audio port (McBSP2 uses 62 for transmit and 63 for receive). I heard the tone. When we rebooted to check that sound came up on its own, Pocket failed to start.

We'd written that refusal into the graphics launcher ourselves. An earlier audio configuration could lock up the tablet, so the launcher exited whenever it found the sound driver loaded. We changed it to run `n810-audio pcm-status` and check whether the boot service had approved the configuration. We tried the repair in slot B and marked it good after Pocket started and passed its GPU check. On the repaired slot A, the `nokia` account could play and record audio, and the GPU completed 50 jobs with all four fault counters at zero.

## Comparing the two GPUs

The original N810 still had experimental Mesa graphics libraries in its home directory. To repeat its [gears and terrain measurements](2026-11-10-gpu-residency-and-480mhz.md), Codex followed the graphics launcher in the backup to find which library it loaded. We used the same benchmark executables on both tablets and verified by SHA-256 that the gears runs used identical Mesa libraries. The original 480 MHz terrain measurement used a different Mesa build.

Each program drew a 400 × 400 RGB565 window through Mesa on the MBX GPU, with Xorg displaying the image. Each frame took one GPU job, so after the program's first frame-rate report we counted completed jobs over three consecutive 30-second intervals at each CPU clock. We counted display-controller interrupts separately because the LCD can receive fewer updates than the GPU renders frames.

| Workload | CPU clock | Original N810 FPS | Second N810 FPS | Second N810 display interrupts/s |
|---|---:|---:|---:|---:|
| Standard gears | 330 MHz | 36.25 | 38.24 | 23.50 |
| Rotating terrain | 330 MHz | 60.96 | 63.75 | 23.46 |
| Standard gears | 480 MHz | 42.74 | 45.34 | 25.71 |
| Rotating terrain | 480 MHz | 71.67 | 74.63 | 25.79 |

At the same CPU clock, gears ran about 6% faster on the second tablet. Matching the Mesa library ruled out a library change for that comparison. We didn't measure background load on both tablets, so we can't attribute the difference to it.

## Using Pocket on the new install

Pocket draws its 800 × 480 desktop directly to the framebuffer. During testing I saw the backlight come on with a blank screen, while Codex could see over SSH that Pocket was running on `tty7` and the panel had power. The framebuffer overlay was disabled. Codex enabled it and requested a display update while I watched the LCD, and the desktop reappeared.

For a frame rate inside Pocket we used Surface Room, where a redraw can take several GPU jobs. With the animated background off and the camera turning continuously in a 640 × 416 window, Room counted 131 completed frames in 45.65 seconds at 480 MHz (2.87 FPS).

We kept the maps on a shared partition so switching Debian slots would leave them in place. Station Map's first sidebar overview took about five seconds to draw under load, and the sidebar could discard the worker's finished image before its next redraw. We changed the sidebar to keep that image.
By the end of the week I could boot the second tablet into Pocket and use the maps on the card. We panned and zoomed in Station Map and ran a radio line-of-sight calculation across 4,097 elevation samples.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [build.py](../assets/source/journal/platform/kernel/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/build.py))<br>[ab_early.py](../assets/source/journal/platform/bootstrap/ab_early.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/ab_early.py))<br>[map_pixels.py](../assets/source/journal/pocket/graphics/map_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/map_pixels.py))<br>[owner_session.py](../assets/source/journal/platform/bootstrap/gpu_runtime/owner_session.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/gpu_runtime/owner_session.py))<br>[n810-cpu-policy](../assets/source/journal/platform/scripts/n810-cpu-policy.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-cpu-policy))<br>[Desktop presentation and frame counter](../assets/source/journal/pocket/graphics/full.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/full.py))<br>[Surface Room pixel view](../assets/source/journal/pocket/graphics/room_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/room_pixels.py)) |
| Checks and fixtures | [test_build.py](../assets/source/journal/platform/kernel/test_build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/test_build.py))<br>[test_ab_early.py](../assets/source/journal/platform/bootstrap/test_ab_early.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/test_ab_early.py))<br>[test_gpu_audio_owner.py](../assets/source/journal/platform/bootstrap/test_gpu_audio_owner.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/test_gpu_audio_owner.py))<br>[test_map_pixel_handoff.py](../assets/source/journal/pocket/tests/test_map_pixel_handoff.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_pixel_handoff.py)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-17-pocket-on-the-second-n810)

[Installing the two Debian slots](../how-to/install-n810-ab.md)
<!-- journal-sources:end -->
