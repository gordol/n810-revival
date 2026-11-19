# Downloading six UV-PRO banks from Pocket

18 November 2026

On the Banks page, the radio looked as though it had already been backed up. All six names appeared, but opening five of them produced no memories. The UV-PRO can report the bank directory while the receiver stays on the current bank. That directory tells Pocket what to list. It doesn't supply the other banks' channel records.

## From one bank to six

In **Radio Manager → Banks**, lowercase **d** reads the selected bank if it is active. **c** reads the current bank. **Download all banks** (lowercase **a**) runs a different operation. The APRS receiver normally owns the radio's Bluetooth serial connection. Pocket pauses that receiver, reads the starting bank and settings, and reads the channel slots. It selects each remaining bank in turn and checks the reported bank number before accepting the next set of channels. Reception can pause during the sweep.

The first attempt stopped on bank 0 even though the handheld showed automatic location sharing was off. The reader had interpreted a single flag as an active timer. On this radio the flag was set, the sharing interval was zero, and Smart Beacon was off. We corrected the check and ran the Banks action again with the handheld settings left as they were.

All six banks returned 30 slots each. Those are 180 slot records, including empty memories. The reader switched back to bank 0 and checked the settings against the original bytes. Bluetooth service discovery then failed several times before the receiver reconnected. For a while Pocket showed both a disconnected radio and five rows marked *name only*, even though the complete backup was already on disk. The Banks view now refreshes its saved catalog when a download finishes, and reports a delayed reconnect separately. On the third tablet the page displayed 30 memories on every row.

## What the receive check established

After reconnecting, live readback showed channel A on 144.390 MHz, the digital channel assigned to A, and KISS enabled. KISS is the serial framing that carries packets from the radio to the tablet. The receive archive contained three inbound frames. All three failed AX.25 decoding, so none supplied a callsign for Heard or a position for Station Map. A known-good APRS position frame passed through the installed decoder into an in-memory station directory. A valid over-the-air position report is still needed to verify that last step with a real station.

Station Map also offers **Tune UV-Pro on B (keep APRS A)** for a selected repeater. The automated tune-and-restore test checked memory readback and preservation of A. During this bank test the physical radio stayed on its restored settings. The installer built from `bd19ce5` passed image checksums and checks of 26 installed source files and seven runtime dependencies; the physical radio results came from Pocket running on the updated tablet.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [Implementation](../assets/source/journal/pocket/shell/radio_manager.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/radio_manager.py)) |
| Checks and fixtures | [Verification](../assets/source/journal/pocket/shell/vendor/packet-console/test-radio-backup.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/packet-console/test-radio-backup.py)) |
| Build inputs | [Installer or runtime input](../assets/source/journal/pocket/shell/vendor/packet-console/n810-radio-backup.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/vendor/packet-console/n810-radio-backup.py)) |

[Build and test instructions](../how-to/install-n810-ab.md) · [Chronological source index](../reference/journal-sources.md#2026-11-18-radio-banks)
<!-- journal-sources:end -->

[Journal](../journal.md)
