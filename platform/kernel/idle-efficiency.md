# N810 idle CPU and peripheral work

This review compares the 5.15.224 source reconstructed by our builder at
`f263494` with the [revive-n8x0 6.18 patch series](https://github.com/thehumanweb/revive-n8x0/tree/7629d71ca775283248a48729fa6cca18ceb01520/kernel/patches/6.18).
The tablet's live kernel, display owner, radio state and interrupt load determine
which paths execute. Hardware CPU, power and throughput deltas are pending.

## Changes in this draft

**McSPI DMA.** The OMAP2420 has a revision 1.4 McSPI controller. Revision
2 introduced the FIFO. The old local workaround spun on missing EOW and TXFFE
flags using two nominal 10 ms timeouts. At HZ=100, the strict jiffies comparison
can take roughly 10–20 ms per expired wait. TX-only FIFO transfers can encounter
both. Both the [N810](https://github.com/gregkh/linux/blob/700e62ea909a70b9f72692d8b7a192ac7ebde0aa/arch/arm/boot/dts/omap2420-n810.dts) and [N810 WiMAX](https://github.com/gregkh/linux/blob/700e62ea909a70b9f72692d8b7a192ac7ebde0aa/arch/arm/boot/dts/omap2420-n810-wimax.dts)
identify as OMAP2420. This board-specific overlay uses non-FIFO DMA directly
on both controllers. It removes FIFO setup, per-transfer FIFO depth tests and
the probe-time revision read. A build targeting newer SoCs should use the
general revision check in the linked 6.18 patch. Association, command/reply handling, calibration and firmware inputs still
matter independently. The comparison project reports timeout occurrences on its
own N810; frequency on ours is unknown. [Original revision check and rationale](https://github.com/thehumanweb/revive-n8x0/blob/7629d71ca775283248a48729fa6cca18ceb01520/kernel/patches/6.18/0039-spi-omap2-mcspi-no-fifo-before-rev2.patch).

**Automatic console refresh.** The N810 panel retains its last image. With one
display, the default refresh rate, no fbdev user files or VMAs, and no active
video overlays, skip the panel sync and transfer until fbcon draws or the
one-second refresh deadline expires. Fill, copy, glyph and cursor drawing,
mode/pan changes, last user release, and starting auto mode request a refresh.
An update failure requests a retry. The delayed worker still checks at its
normal cadence so keyboard echo and console scrolling can reach the next
update. A kernel writer bypassing the framebuffer callbacks can take about a
second to appear. The fallback also picks up display configuration changes.
Any fbdev user open keeps continuous updates active, including a read-only
monitor. An mmap holds its file reference after close. Video overlays,
multiple displays or a positive explicit `auto_update_freq` also retain
continuous updates. Manual Pocket presentations follow their existing path.
State costs three 32-bit words per fbdev device and no shadow framebuffer.

**Display policy publication.** The display daemon sampled every five seconds
and atomically replaced its status even across identical samples, including
while blank. It also wrote effective brightness on every active sample. Publish
changed status atomically, recreate a missing status, and use the brightness
value already read from the runtime file to skip redundant writes. The sample
interval, thresholds, blank handling and brightness control follow the same
paths. Consumers in this tree read status as state; PID/starttime identify
the daemon. Status mtime now reflects publication. [Display daemon](../scripts/n810-displayd).

## Other findings

| Path | Source evidence and implication for this tablet |
| --- | --- |
| Console display refresh | The builder supplies `omap2fb.auto_update=y`. Before this patch the auto-mode fbdev worker synchronizes the display, requests the **entire resolution**, then requeues after HZ/20 by default. On an 800×480 RGB565 screen each full image is 768,000 bytes. The delay starts after the work, so 20 is a nominal scheduling rate. Blanking stops the worker. Pocket's native bootstrap explicitly selects manual update and restores the old mode at exit. Check the live mode before attributing activity to this worker. Dropping auto refresh globally would require another way to present ordinary fbcon writes. [Linux worker](https://github.com/gregkh/linux/blob/700e62ea909a70b9f72692d8b7a192ac7ebde0aa/drivers/video/fbdev/omap2/omapfb/omapfb-main.c#L1654-L1684) · [Pocket ownership](../../pocket/platform/n810/bootstrap_desktop.py) |
| Wireless worker | Both trees move reply processing off mac80211's ordered queue to avoid configuration stalls. Ours uses a system work item and theirs a dedicated ordered queue. A second backport would need evidence of contention. The optional per-TX delay and dummy RX flush in our source default to zero/off. [Their worker patch](https://github.com/thehumanweb/revive-n8x0/blob/7629d71ca775283248a48729fa6cca18ceb01520/kernel/patches/6.18/0041-p54spi-own-workqueue.patch) |
| Battery sensing | The Tahvo monitor checks once a second. An ordinary unplugged pass makes one charger-presence ADC read plus five battery-voltage and five temperature reads. Most userspace battery properties return cached values. Separate presence detection from settled discharge telemetry only after establishing how much stale data the low-battery shutdown policy can tolerate. Keep fresh checks before enabling charging and retain active charge monitoring, thresholds and fault recovery. Their kernel starts with charge PWM off and exposes the hardware to Maemo BME; its userspace sampling cost is unknown. [Our charger](n810-5.15.224.patch#L9235-L9295) · [Their charger interface](https://github.com/thehumanweb/revive-n8x0/blob/7629d71ca775283248a48729fa6cca18ceb01520/kernel/patches/6.18/0006-retu-maemo-charger-off-and-user-interface.patch) |
| ADC error propagation | The Retu ADC helper masks its result with 0x3ff before returning it and ignores the channel-select write result. A negative bus error can become a plausible sample. Before caching readings for longer, exercise failed channel selection, failed reads, and Vilma restoration against a bus fixture. This has implications for battery-policy correctness independently of CPU cost. [ADC implementation](n810-5.15.224.patch#L6473-L6500) |
| Ambient light and LEDs | Both daemons default to the same IIO lux file. The LCD reads while active. The LED daemon reads it only for a lit, low-current indication; ordinary LED-off idle skips it. The TSL2563 driver acquires its supply clock for access and releases it when event detection permits. Sharing a recent sample is most relevant during persistent low-battery or notification indications. [LED policy](../scripts/n810-ledd#L115-L142) · [Sensor clock handling](n810-5.15.224.patch#L6738-L6762) |
| Touchscreen recovery | The board requests an eight-second TSC2005 ESD interval. The core schedules rounded delayed work when enabled with reset support and can check the chip after inactivity. Preserve recovery and count this separately from WLAN traffic on the other SPI controller. [Board setting](n810-5.15.224.patch#L456) · [Core worker](https://github.com/gregkh/linux/blob/700e62ea909a70b9f72692d8b7a192ac7ebde0aa/drivers/input/touchscreen/tsc200x-core.c#L360-L408) |
| Retention and serial console | Their OMAP24xx idle implementation checks functional clocks and DMA before choosing retention. Our build requests a serial console, and our panel driver holds its oscillator while enabled. Record the live clocks and available idle-state usage/time, especially with screen on versus blank. Clock residency can cost battery while the CPU idle percentage looks good. A clock request alone does not establish the running power state. [Their PM implementation](https://github.com/thehumanweb/revive-n8x0/blob/7629d71ca775283248a48729fa6cca18ceb01520/kernel/patches/6.18/0019-arm-omap2-pm24xx.patch) |
| RFBI latency | Their DRM patch polls the CPU during an in-flight display update to avoid missed/delayed completion wakeups. Our stack uses omapfb. Their trace points (arm, TE, FRAMEDONE) are applicable if we see stalls; copying their spin would need a separate latency/power justification. [Their RFBI patch](https://github.com/thehumanweb/revive-n8x0/blob/7629d71ca775283248a48729fa6cca18ceb01520/kernel/patches/6.18/0066-drm-omap-rfbi-idle-poll-during-update.patch) |
| Pocket idle and accounting | The Nokia selector can sleep without a frame timer. A non-Flux animated background can request a 100 ms timeout. The host preview has a separate 16 ms cap. The kernel configuration enables tickless idle, HZ=100 and tick-based CPU accounting with IRQ time accounting disabled. Short IRQs can be poorly represented by CPU ticks. Interrupt counts measure activity; individual handler duration needs separate evidence. [Nokia backend](../../pocket/graphics/nokia.py) · [Desktop scheduling](../../pocket/shell/desktop.py#L1958) · [Kernel config](n810.config) |

## Matched hardware comparison

1. Record kernel identity, CPU frequency/governor, foreground owner, framebuffer update mode, brightness, charger state, Wi-Fi state and background settings. Keep the clock fixed across each comparison. Use local collection so a monitoring SSH stream does not generate WLAN work.
2. Let startup and paging settle. Collect endpoint deltas over 60 seconds, reverse the order and repeat. Separate console in auto mode, static Pocket in manual mode, and screen blank. Capture /proc/stat, /proc/interrupts, /proc/softirqs, per-process user/system ticks, and available cpuidle residency and RFBI completion counters. Record unavailable counters explicitly. Track exited helper processes separately if attributing daemon cost. Battery power requires an electrical measurement or validated device telemetry.
3. Isolate the SPI change with the same userspace. Compare Wi-Fi powered off, associated and quiet, and a fixed bidirectional transfer. Record throughput, packet loss/retries, p54 command failures and kernel CPU. Verify association/reassociation, touch taps, drags and recovery on McSPI1. Use the original kernel as the control.
4. Isolate displayd with the same kernel, running active, unchanged blank and a blank/wake transition. Compare status publications, effective-brightness writes and process CPU. Check manual brightness, sunlight hysteresis and low-battery dimming. Keep the previous kernel and userspace available for recovery.

## Host verification

The Linux archive matched the builder's pinned SHA-256. All overlays applied
with zero fuzz, all 14 repository input digests and 64 final source digests
matched, and the updated McSPI driver compiled to an ARM EABI5 object using
GCC 12.2.0 and binutils 2.40.

In a same-host shell fixture with a one-second sample interval and an unchanged
blank screen, both daemons completed five samples. The original invoked
`mv` five times to publish status; the candidate invoked it once. This counts
publications. Device CPU utilization and battery savings require the physical
comparison above. The [regression test](../scripts/test-n810-displayd-publication.py)
also exercises active, blank, sensor-fault and recovered states, stable
brightness, and recreation of a deleted status file.

Compared with the earlier runtime revision check in this draft, the same
ARM object build reports 9,202 to 8,514 bytes of text (688 bytes smaller).
Data and BSS remain 148 and 16 bytes. DWARF reports a 56-byte controller
structure in both builds. These figures describe the McSPI object and its
layout; compressed boot image size and tablet power were not measured.

The complete omapfb directory cross-compiled for ARM with the N810 config.
The [host worker test](test_console_refresh.py) calls the patched callbacks
and worker with synthetic jiffies and a counting panel. In 20 idle checks at
HZ=100 the original worker submitted 20 full-screen updates and the patched worker submitted one in the first second.
Drawing coalesced, failed updates retried, and continuous updates ran with a
userspace open, enabled video overlay, multiple displays or explicit rate.
Run `python3 platform/kernel/test_console_refresh.py /path/to/patched/linux`.
On a tablet also check cursor blink, scrolling, a mapped writer after closing
its fd, video playback, manual/auto switching, and immediate unblank repaint.
Use an external observation or RFBI counters for idle tests: a monitor holding
the framebuffer device open deliberately selects continuous updates.
