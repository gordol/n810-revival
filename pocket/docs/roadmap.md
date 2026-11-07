# Remaining work

Remove items when completed. Keep implementation history and test results out of
this file; Git and the relevant technical documents retain that evidence.

## Current priorities

1. **Install and inspect the latest changes on Nokia.** Use a coordinated device
   window. Check map pan/zoom, sidebar clipping, profile return, title contrast,
   input focus and retained panel preferences on screen.
2. **Finish app interaction consistency.** Migrate remaining app commands to named
   bindings with matching buttons/help. Finish local Escape behavior, narrow-window
   focus and actionable loading/empty/error states.
3. **Make map navigation responsive.** Reduce cold preparation and verify retained
   views, incremental pan and preview refinement through the actual UI. Profile
   locally while Nokia is shared; use an uncontended device window for acceptance.
4. **Reduce startup, recovery and idle work.** Profile shell, catalogue, SSH and
   crypto initialization separately. Remove repeated model work, hidden-view polling
   and subscription amplification without delaying input or independent services.
   Investigate console/kernel output costs if they remain significant.
5. **Finish runtime integration.** Complete native layer/overlay composition and
   input/event-host work; integrate Map Library with proper cancellation/lifetimes.
   Audit remaining optional startup imports and runtime dependencies.
6. **Finish maintenance gaps.** Show the source revision instead of UNKNOWN.
   Add release-capacity preflight, idle-owner quiescing and repeatable clean-machine
   acceptance to the existing update workflow.
7. **Integrate notifications.** Connect message events, desktop/terminal notices and
   LED policy through one bounded store, with deduplication, expiry and dismissal.

## Application backlog

- **Terrain:** independently compare known paths, quantify mixed-resolution
  uncertainty, inspect refinement boundaries and choose a Nokia detail budget.
- **Repeaters:** establish antenna-height provenance and data update scheduling;
  verify restore/listen behavior without disturbing APRS.
- **APRS:** verify end-to-end message/ACK evidence and freshness presentation.
  Historical aprs.fi lookup is optional and requires a configured key.
- **FCC:** schedule database updates with visible last-success/failure and verify
  data availability on the device.
- **Messaging:** finish delivery/expiry/reconnect and cross-view contact checks.
  Add attachments only with an implemented transfer transport, progress,
  cancellation and duplicate handling.
- **Packet/BBS:** connect to an existing BBS through the shared KISS owner; assess
  a maintained local BBS separately.
- **Native Reticulum:** close remaining BLE, LAN discovery, multiple-interface,
  routing, KISS flow-control/beacon and AX.25 gaps.

## Hardware acceptance

- Verify sustained stylus move/resize, release/cancel, edges and held keys under
  service traffic; run long-session memory and independent-owner recovery checks.
- Verify physical carrier loss/reconnect and direct/channel message delivery,
  including signatures and receipts, when the relevant radios are available.
- Finish external-node offload acceptance: board memory, encrypted RFCOMM,
  service/subscription transfer, lease expiry and whole-system timings.
- Reconcile platform power/charge, network/Bluetooth soaks, storage/card recovery,
  USB host/HID, audio, suspend/watchdog and boot selection with current device work.

## Deferred

- First-use setup and two-N810 peer acceptance together when the second device arrives.
- Live UV-Pro tuning/RF checks until a relevant change needs the powered radio.
- Debian packaging; HF/modems, VARA/ARDOP/PACTOR and cellular experiments.
- SSTV, satellite/ADS-B/radiosonde views, speech-to-text, keyer and Winlink integration.
- Optional GPU/MBX and wildlife experiments; hardware AES investigation requires
  separate known-vector, hardware-path and packet-size evidence.
