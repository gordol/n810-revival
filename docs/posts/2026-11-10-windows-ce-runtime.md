# Investigating a native ARM Windows CE runtime

*10 November 2026. Design investigation; no Windows CE application has been run on the N810 through this path.*

The [Symbian runtime](2026-11-06-native-symbian.md) suggested another use for its execution model. It loads Symbian applications and lets their ordinary ARM instructions run on the N810 processor, while a compatibility runtime supplies the operating-system services and Pocket regains the display when the application exits. We investigated whether selected ARM Windows CE 3, 4.x, and 5.x applications could use a similar boundary.

Booting Windows CE would require adapting its kernel and hardware support to the tablet. The proposed runtime keeps Linux running. It needs a Portable Executable (PE) loader, CE library imports, process and thread state, and implementations of the services each selected application calls. A small board support package would not supply those services. Windows CE through version 5 divided APIs among the kernel and processes for files, devices, and graphics; Microsoft's [CE architecture account](https://learn.microsoft.com/en-us/archive/msdn-magazine/2006/december/mobilize-explore-the-new-features-in-windows-embedded-ce-6-0) describes that boundary.

There are two possible library starting points. Loading an original ARM `coredll.dll` would preserve its wrappers but require the kernel calls and CE state behind them. A replacement CE-facing `coredll` could resolve selected imports into our Linux-backed services. The replacement still needs PE import resolution; it cannot be only an ordinary Linux shared library. We favor the replacement for the first narrow test, then can measure whether original-library wrappers help a particular application. Neither performance claim is established yet.

Memory and faults need explicit design. CE 3 applications had a 32 MB private address space and could allocate additional shared memory, as described in Microsoft's [process overview](https://learn.microsoft.com/en-us/archive/msdn-magazine/2000/november/windows-ce-3-0-enhanced-real-time-features-provide-sophisticated-thread-handling). A guest allocator must reproduce the observable `VirtualAlloc` behavior, PE section protections, and address placement. The N810's 32-bit ARM Linux kernel has 4 KB pages, so the large-page concern sometimes raised for modern ARM64 hosts does not apply to this machine. CE's high KData and trap addresses cannot simply become Linux user mappings. The runtime must provide expected thread state and dispatch intentional guest calls without mistaking a real crash for a call. Applications using structured exception handling will also need CE exception delivery; a Linux signal alone is insufficient.

We found a possible later test in the locally supplied PocketDOS 1.12.3 demo. Its outer `.exe` is a desktop x86 self-extractor containing ARM CE CABs. PocketDOS itself emulates a PC/XT and uses graphics, input, files, and timing, so it would exercise several layers at once. Its bundled readme prohibits reverse engineering or modifying its files. We will use independently authored CE fixtures for development and treat a user-supplied ARM build as an eventual acceptance target. The separate Casio BE-300 build is MIPS and cannot use the native ARM path.

Prior work gives useful comparisons. [WCECL](https://github.com/gweslab/wcecl) implements a replacement `COREDLL` for x86 CE programs on desktop Windows, but its author archived it and reported one confirmed working application. [CERF](https://github.com/gweslab/cerf) and [MAME](https://docs.mamedev.org/initialsetup/mameintro.html) emulate hardware; they can inform behavior without determining the native execution design. Any source reuse needs a revision and license review.

The first experiment should load an authored ARM CE PE, resolve a few imports, execute its ordinary instructions natively, print expected output, and exit cleanly. File and thread behavior, a simple window, DirectDraw, and PocketDOS follow only when the preceding result is repeatable. The [roadmap](../roadmap.md#run-selected-arm-windows-ce-applications-on-linux) records those acceptance steps. This entry records a design decision, not a working CE runtime or a device test.

<!-- journal-sources:start -->
## Research status


[Chronological source index](../reference/journal-sources.md#2026-11-10-windows-ce-runtime)

Design investigation only. No Windows CE compatibility implementation or N810 test is included.
<!-- journal-sources:end -->
