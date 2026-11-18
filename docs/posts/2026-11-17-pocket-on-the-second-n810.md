# Getting Pocket running on a second N810

*11–18 November 2026.*

I tried our installer on a second N810 to see whether it could reproduce the Pocket setup I'd been using on the first. We'd been developing on that tablet for a month, and a fair amount of what we'd tried was still on the SD card. During the gears tests we'd copied over different Mesa builds to try on the hardware and kept the earlier ones around for comparison. I counted 26 compressed archives with `gears` or `mesa` in the name at the top of the `nokia` home directory alone.

## What went into the installer

We worked from a read-only copy of the backup and compared it with the November 12 installer image. The original root filesystem contained 202,909 regular files. Of those, 103,204 were under `/var/backups/n810-pocket-console`, where Pocket upgrades had kept copies of application files and assets. The installer image contained 12,787 regular files. Counting Debian packages accounted for some of the difference. The old tablet had 245 packages absent from the image (including Xfce and debugging tools), but among the packages they shared, only `libutempter0` differed in version.

To decide what belonged on the second tablet, we followed the commands the first one ran. There were two Pocket trees, one in `/usr/local/share/n810-pocket` and another in `/home/nokia/pocket/current`. For graphics, the launcher selected `/usr/local/lib/n810-graphics/releases/20261109-6970068`. That gave us a specific Mesa library and kernel module to compare with the installer's versions. We kept the trial builds in the backup and used the selected release as our reference for the hardware tests.

Following startup scripts also turned up files the installer had missed. The original power-button handler called `/usr/local/sbin/n810-console-power-menu`, a helper absent from the image. We found part of the working APRS service among the experiments in my home directory. At boot, `/etc/rc.local` ran the scripts in `/etc/boot.d`. One started a supervisor that ran `/home/nokia/n810-aprs-feed.py` as `nokia`, and the receiver imported the Python modules beside it. That accounted for a set of files we'd have lost by excluding the home directory wholesale.

## Keeping the keyboard through boot

I could type on the first Debian boot after the installer ran Maemo in RAM. I rebooted because SSH was slow, and the keyboard stopped responding even at the Debian login prompt. The two boots used the same kernel. We compared the keyboard settings with the original tablet and found the same 30-millisecond debounce interval on both. To try the original kernel as well, we had to rebuild it (the kernel lived in flash, outside the filesystem backup). We used the original compiler, changed the root-device selection for the new card, and checked the running build ID in `/sys/kernel/notes`. The LM8323 controller still didn't acknowledge reads over I²C, and its interrupt count stayed at zero.

When I got back to the project a few days later, I could type at the recovery console. The driver had logged `chip lost config; reinitializing` during recovery, and by the time we needed to mount the SD card the flashed kernel already had a working keyboard. Our installer would then boot another kernel and initialize the hardware a second time. We removed that step. The flashed kernel now selects one of the two Debian installations on the card (slots A and B) before starting services, and both slots carry modules built for it. I could type `htop` in Pocket's Terminal after the change. We never established why the controller stopped answering on the earlier boots.

## Getting sound and graphics to start together

The audio driver expected a codec called `tlv320aic3x-codec.1-0018`. Linux had registered it as `tlv320aic3x.1-0018`. We corrected the name in the board driver and fixed the interrupt assignments for the McBSP2 serial audio port (62 for transmit and 63 for receive). I heard the test tone, but when we enabled sound at boot and restarted the tablet, Pocket failed to start.

We'd put that check in the graphics launcher when an earlier audio configuration could lock up the N810. It exited as soon as it found the sound driver loaded, which now happened on every boot. We changed the launcher to run `n810-audio pcm-status` so it could check whether the boot service had approved the configuration. We tried the repair in slot B first, with A available to boot if it failed. Once Pocket started and passed its GPU check, we marked B good and applied the repair to A. After booting A, the `nokia` account could play and record sound while graphics remained available. The GPU completed 50 jobs with all four fault counters at zero.

## Running Pocket on the new installation

Pocket draws directly to the framebuffer, so we also counted redraws inside Surface Room, which can submit several GPU jobs per frame. With the camera turning continuously in a 640 × 416 window and the animated background off, it drew 131 frames in 45.65 seconds at 480 MHz (2.87 FPS).

At one point during testing I could see the backlight and nothing else. Over SSH, Codex found Pocket running on `tty7` with power to the panel and the framebuffer overlay disabled. Enabling the overlay and requesting a display update put Pocket back on the LCD.

I wanted to try the maps I'd put on the shared partition, since I'd be using them from either Debian slot. We panned and zoomed in Station Map and ran a radio line-of-sight calculation across 4,097 elevation samples. Under load the first sidebar overview took about five seconds to prepare. The worker finished drawing the image, but the sidebar could discard it before the next redraw. We changed the sidebar to retain the completed image.

## Repeating the graphics tests

We took the [gears and terrain executables from the original measurements](2026-11-10-gpu-residency-and-480mhz.md) and ran them on the second N810 with Xorg. Both workloads rendered a 400 × 400 RGB565 window and submitted one GPU job per frame. After the first frame-rate report we counted completed jobs over three consecutive 30-second intervals at each CPU clock. We counted display-controller interrupts over the same intervals to measure how often the controller transferred an image to the LCD.

| Workload | CPU clock | Original N810 FPS | Second N810 FPS | Second N810 display interrupts/s |
|---|---:|---:|---:|---:|
| Standard gears | 330 MHz | 36.25 | 38.24 | 23.50 |
| Rotating terrain | 330 MHz | 60.96 | 63.75 | 23.46 |
| Standard gears | 480 MHz | 42.74 | 45.34 | 25.71 |
| Rotating terrain | 480 MHz | 71.67 | 74.63 | 25.79 |

We could check the gears result against the particular Mesa build we'd recovered from the original installation because the library hashes matched on both tablets. Raising the CPU clock from 330 to 480 MHz had improved gears throughput by 18% on the first N810. On the second we measured a 19% improvement with the same executable and library. The original 480 MHz terrain run used a different Mesa build, so we couldn't make the same comparison for terrain.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [build.py](../assets/source/journal/platform/kernel/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/build.py))<br>[ab_early.py](../assets/source/journal/platform/bootstrap/ab_early.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/ab_early.py))<br>[map_pixels.py](../assets/source/journal/pocket/graphics/map_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/map_pixels.py))<br>[owner_session.py](../assets/source/journal/platform/bootstrap/gpu_runtime/owner_session.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/gpu_runtime/owner_session.py))<br>[n810-cpu-policy](../assets/source/journal/platform/scripts/n810-cpu-policy.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/scripts/n810-cpu-policy))<br>[Desktop presentation and frame counter](../assets/source/journal/pocket/graphics/full.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/full.py))<br>[Surface Room pixel view](../assets/source/journal/pocket/graphics/room_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/room_pixels.py)) |
| Checks and fixtures | [test_build.py](../assets/source/journal/platform/kernel/test_build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/kernel/test_build.py))<br>[test_ab_early.py](../assets/source/journal/platform/bootstrap/test_ab_early.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/test_ab_early.py))<br>[test_gpu_audio_owner.py](../assets/source/journal/platform/bootstrap/test_gpu_audio_owner.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/platform/bootstrap/test_gpu_audio_owner.py))<br>[test_map_pixel_handoff.py](../assets/source/journal/pocket/tests/test_map_pixel_handoff.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_pixel_handoff.py)) |

[Build and test instructions](../how-to/run-n810-gpu.md) · [Chronological source index](../reference/journal-sources.md#2026-11-17-pocket-on-the-second-n810)

[Installing the two Debian slots](../how-to/install-n810-ab.md)
<!-- journal-sources:end -->
