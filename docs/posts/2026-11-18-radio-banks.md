# Downloading six UV-PRO banks from Pocket

18 November 2026

Radio Manager initially showed names for five banks and memories for only one. Download all banks now releases the Bluetooth receive connection, reads each bank, restores the original bank and settings, and starts reception again. The bank reader originally treated one location-sharing flag as proof of periodic transmission. The test radio reported a zero interval with Smart Beacon off. The corrected reader completed the export without changing its location settings.

On the third N810, Radio Manager displayed 30 memory slots in each of six banks. The UV-PRO returned to bank 0 with byte-for-byte settings readback. Bluetooth service discovery took several retries before the receive monitor reconnected. Three archived inbound frames failed AX.25 decoding. A known-good position frame exercised the installed decoder and station directory in memory. Live reception of a valid position report still needs confirmation.

Installer checkpoint `bd19ce5` passed its image checksums and checks of 26 installed source files and seven runtime dependencies. The radio results above came from the running tablet.

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
