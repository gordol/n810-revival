# HTIT firmware sources

The Heltec HTIT-TB Wireless Bridge combines an original ESP32, an SX1276 LoRa radio, 8 MB of flash, PSRAM, USB serial and Bluetooth Classic. This directory preserves two firmware designs in their own source directories.

| Directory | Role | Build environment |
|---|---|---|
| `rfcomm-ble-hub/` | Multiplex USB and Bluetooth host connections, a BLE companion connection and the onboard LoRa service. | `htit_tb`, Espressif32 6.10.0, ESP-IDF 5.4.0. |
| `microreticulum/` | Run microReticulum and microLXMF on the ESP32 and expose Pocket's executor protocol over RFCOMM. | `htit-tb-executor-rfcomm`, Espressif32 6.12.0, Arduino ESP32 2.0.17. |
| `experiments/ibss-rsn/` | CCMP framing, receive-descriptor analysis and the experimental WPA IBSS RSN adapter. | Host tests and explicitly selected experimental ESP32 environments. |

The executor includes the UART buffer changes, the internal-RAM Bluetooth receive path, the private pairing-PIN requirement, and the retained microLXMF parsing and object-lifetime repairs. `executor-libs/` holds the source versions used by that target. Their license notices remain beside their code. `source-provenance.json` identifies the source checkpoint and upstream firmware revision.

Use the [firmware build guide](../../docs/how-to/build-htit.md) for the ordinary hub and executor builds. The guide also gives the host test commands. The [HTIT journal entry](../../docs/posts/2026-10-29-htit.md) explains why execution moved onto the board; the [recovery entry](../../docs/posts/2026-10-30-htit-recovery.md) follows the buffering and reconnect failures.

The optional RSN adapter verifies WPA Supplicant 2.12 against SHA-256 `08e23937e16d0155e55cab2b51f51fbe10d80a1aa91c4e15442645059b737ef6`. Set `HTIT_RSN_WORK` to a local build directory. Its host tests use generated keys and in-memory peers. Experimental radio trials have their own hardware prerequisites and acceptance work.
