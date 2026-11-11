# Journal

Read from the beginning. The entries follow the recorded sequence from Maemo research and recovery through the November GPU and runtime investigations. Several investigations overlapped; their headings give the covered period. The early entries were reconstructed on 4 November 2026 from retained notes. Later entries follow the UI and session fixes, map rendering, native Symbian execution, the Mac graphical desktop, Surface Room interaction, and the Windows CE design investigation.

The visual record begins with the [sidebar desktop](posts/2026-10-05-sidebar-desktop.md), continues through the [APRS packet inspector](posts/2026-10-14-aprs.md) and [console color comparison](posts/2026-10-16-16-bit-console.md), and reaches the [first live MBX gears](posts/2026-11-03-mbx-rendering.md). Captions distinguish historical tablet captures from later laptop demonstrations.

| Period | Entry |
|---|---|
| Early October 2026 | [Recovering the machine and booting Debian](posts/beginnings.md) |
| 3 October 2026 | [Recovering the complete Wi-Fi firmware](posts/2026-10-03-wifi.md) |
| 4 and 5 October 2026 | [Bringing up charging, display wake, and input](posts/2026-10-05-power-display-input.md) |
| 5 October 2026 | [Building the first sidebar desktop](posts/2026-10-05-sidebar-desktop.md) |
| 13 October 2026 | [Moving Debian to SD and connecting peripherals](posts/2026-10-13-sd-bluetooth.md) |
| By 14 October 2026 | [Starting with APRS and the handheld radio](posts/2026-10-14-aprs.md) |
| 14 to 16 October 2026 | [One radio receiver, several terminal views](posts/2026-10-16-radio-ssh.md) |
| 16 October 2026 | [Extending the Linux console to RGB565](posts/2026-10-16-16-bit-console.md) |
| Mid-October 2026 | [Moving the desktop into the terminal](posts/2026-10-16-pocket-desktop.md) |
| Mid-October and subsequent replay work | [Decoding Morse recordings and preparing an audio input](posts/2026-10-16-cw.md) |
| 18 October 2026 | [Measuring the ARM CPU before moving work elsewhere](posts/2026-10-18-cpu-acceleration.md) |
| 20 October 2026 | [Rendering water and measuring idle work](posts/2026-10-20-water-and-idle.md) |
| 20 to 24 October 2026 | [Preparing maps and preserving the last usable view](posts/2026-10-24-maps-with-an-edge.md) |
| 24 October 2026 | [Sending LXMF messages through the terminal interface](posts/2026-10-24-lxmf.md) |
| 29 October 2026 | [Moving Reticulum execution onto the HTIT](posts/2026-10-29-htit.md) |
| 30 October 2026 | [Debugging HTIT reconnects and internal RAM pressure](posts/2026-10-30-htit-recovery.md) |
| October GPU investigation through 1 November 2026 | [Bringing up the graphics clock domain](posts/2026-10-31-gpu-clocks.md) |
| 2 November 2026 | [Reconstructing the MBX command stream](posts/2026-11-02-gpu-command-stream.md) |
| 2 November 2026 | [Repairing microLXMF parsing and object lifetime](posts/2026-11-02-microlxmf.md) |
| By 3 November 2026 | [Maintaining the N810 changes on Linux 5.15.224](posts/2026-11-03-kernel.md) |
| 3 November 2026 | [Rendering standard glxgears on the MBX](posts/2026-11-03-mbx-rendering.md) |
| 3 November 2026 | [Integrating the Pocket applications into version 0.1.0](posts/2026-11-04-pocket-0-1-0.md) |
| 4 November 2026 | [Moving geometry onto the GPU and reaching 30 FPS](posts/2026-11-04-gpu-performance.md) |
| 5 November 2026 | [Rendering synthetic terrain and comparing cached updates](posts/2026-11-04-gpu-performance.md#5-november-rendering-a-synthetic-terrain-mesh) |
| 5 November 2026 | [Following our own keyboard instructions](posts/2026-11-05-help-and-input.md) |
| 6 November 2026 | [Keeping session state correct across reconnects](posts/2026-11-06-session-recovery.md) |
| 6 November 2026 | [Playing a Symbian chess game through native ARM execution](posts/2026-11-06-native-symbian.md) |
| 7 November 2026 | [Resizing the map without stretching its annotations](posts/2026-11-07-map-resizing.md) |
| 7 November 2026 | [Teaching the MBX path the drawing operations that Symbian apps use](posts/2026-11-07-symbian-surfaces.md) |
| 7 November 2026 | [Running the Pocket desktop in a native Mac window](posts/2026-11-07-native-desktop.md) |
| 7 November 2026 | [Adding movement, aiming, and targets to Surface Room](posts/2026-11-07-surface-room.md) |
| 7 November 2026 | [Moving desktop effects and terrain work onto the Mac GPU](posts/2026-11-07-gpu-effects.md) |
| 10 November 2026 | [Investigating a native ARM Windows CE runtime](posts/2026-11-10-windows-ce-runtime.md) |

The guide and reference pages describe reusable procedures and the latest reconciled state. Dated posts preserve the observations available at each checkpoint.

## Reading the records

The history was reconstructed from recovery notes, Maemo-derived board observations, dated platform tests, Pocket source documentation, radio acceptance records, and GPU build and performance checkpoints. Where the first execution date is incomplete, the entry uses a period. Captions identify later demonstrations and reconstructed comparisons. Published checkpoints link their source, tests, and build inputs. Experimental entries identify the available development source and the work still awaiting integration.
