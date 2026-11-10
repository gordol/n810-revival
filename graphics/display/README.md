# N810 partial RFBI update

`n810-partial-rfbi.patch` applies to maintained Linux commit
`6bd43ee8d27b207c958808368251d55ec0475f9e`. It changes the existing panel,
RFBI and DSS manager path; it does not introduce another display owner.

The panel validates the requested bounds under its existing ownership lock.
RFBI checks whether the current overlay can be cropped. For the unscaled,
unrotated RGB565 GFX plane, DSS programs a temporary source address, keeps the
original framebuffer stride, and sets the transfer width/height. RFBI's pixel
count and Blizzard's input/output window use the same rectangle. Logical
overlay state remains full-frame. Hardware overlay/timing state is restored
under the existing IRQ lock before the frame-done callback releases RFBI.
Configuration failure restores state before returning; an incomplete transfer
retains the existing fault/ownership boundary.

Multiple overlays, scaling, rotation, incompatible formats and unaligned
regions use the existing full-screen transfer. Invalid bounds are rejected.
The Nokia userspace adapter expands horizontal bounds to pixel pairs without
changing pixel values. On the old full-only kernel it records one EINVAL
capability rejection and uses full transfers thereafter.

Read-only aggregate parameters `rfbi_completed_updates`,
`rfbi_completed_pixels`, `rfbi_partial_updates` and `rfbi_transfer_ns` record
completed work. The time is kick-to-observed-callback time, including interrupt
handling/restoration overhead, not a pure electrical bus measurement. Atomic
64-bit access avoids torn ARM32 reads. There is no per-frame diagnostic output.
Read counters after draining the display; userspace requested bounds alone do
not prove that the kernel avoided its full-screen fallback.

## Local check

```
python3 test_region.py --kernel-tree /path/to/clean/maintained/linux
```

This extracts the actual patched manager functions, compiles them with address
and undefined-behavior sanitizers against hardware/lock test doubles, and checks
crop address/stride, restoration, invalid bounds, unsupported layouts, busy
ownership, and failure before start. It does not emulate the display hardware.
Build all modified kernel objects and the complete kernel/modules as well.

The current N810 configuration has `CONFIG_FB_OMAP2_DSS=y`,
`CONFIG_FB_OMAP2_PANEL_N8X0=y` and `CONFIG_KEXEC=y`. Those display components are
built into the image, so this change uses a kexec kernel replacement; the GPU
probe remains independently reloadable. Use a distinct kernel release and its
matching modules. Preserve the installed boot image and current device tree,
and hold Pocket/radio autostart before any test-kernel entry.

Physical partial-transfer correctness and performance remain pending activation
of the rebuilt kernel. The preceding userspace comparison verified retained
commands and exact final framebuffer pixels; its old kernel still performed
full-screen RFBI transfers.

## Built candidate (2026-11-09)

The complete kernel, standard modules, DTB, and matching external MBX probe
built as `5.15.224-n810-mbx-clock-wip1-rfbi1`. The package manifest verifies
219 files; the GPU module vermagic matches the candidate and KEXEC remains
enabled. Compiler garbage-collection tuning bounded build-host memory only;
it does not change the driver's optimization level or rendering quality.

The current device exposes `/sys/kernel/kexec_loaded` and `/usr/sbin/kexec`.
Its existing SysV `K07kexec` hook can execute a staged image during orderly
shutdown. Kexec avoids NOLO/flashing/power cycling but restarts Linux userspace;
it does not preserve running application processes. Before activation, preserve
the current FDT and hold existing Pocket/radio autostarts, including `rc.local`
boot hooks. Do not overwrite the installed kernel or its module directory.
Physical partial-RFBI validation remains pending a clean device handoff.

## Native render/display overlap candidate

`POCKET_SCENE_OVERLAP=1` with the owned DMA sink defers the display completion wait until after the next private GPU image has completed. Destination preparation returns metadata only; it grants no write lease. The framebuffer is acquired and its previous transfer drained before the first DMA copy. Timeout or ownership failure prevents writes. Remaining tiles share that lease until the normal update submission.

This overlaps GPU rendering with the preceding RFBI transfer without changing the panel driver or kernel. It remains opt-in. Physical validation passed48 full-frame snapshots exactly with zero GPU readback/CPU sink bytes and clean guards. A separate capture-free movement comparison measured9.786 to11.440FPS,66.400 to60.829CPUms/redraw, and peakRSS37080 to37072KiB. Both controls used resident windows and the same full-screen RFBI path. Local native cross-build/reference checks pass. Normal module removal restored the prior console, panel and preferences without reboot. Evidence: project outputs/gpu-rfbi-overlap-20261109/summary.json. The full-screen RFBI fix above still requires activation of the rebuilt kernel; the current no-reboot constraint leaves that activation pending.
