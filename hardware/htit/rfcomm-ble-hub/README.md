# Pocket HTIT-TB hub

Custom firmware for the original Heltec Wireless Bridge (ESP32-D0WDQ6,
SX1276, 8 MB flash). This is **not** an ESP32-S3 build. The first version connects
an N810 over Bluetooth Classic SPP/RFCOMM and a laptop over CP2102 USB serial,
then acts as a BLE central for one existing MeshCore companion radio.

The hub runs the BLE connection and pairing. Pocket runs the MeshCore client;
the external radio runs MeshCore. The hub does not issue companion commands on
its own. Scanning, connecting and transmitting are explicit host actions.

## Implemented paths

- USB UART0 at 115200, 8N1; boot/reset control lines deasserted by host helper.
- Up to two authenticated Classic SPP host sessions, plus USB concurrently.
- One BLE central connection, with passkey pairing, bonding, MTU negotiation,
  service discovery and notification subscription before reporting ready.
- A single renewable owner lease for the MeshCore service. Other hosts can use
  the independent host-to-host data service while MeshCore is owned.
- Bounded framed packets with CRC, escaping, service IDs and request IDs.
- One Python helper presents MeshCore, peer and optional RNode serial PTYs over the same physical connection.
- Service 3 exposes the onboard SX1276 with an independent lease and RNode-compatible packet framing.

Wi-Fi remains disabled. LoRa is initialized only by explicit service-3 configuration. A peer PTY
is a byte tunnel, not an automatically configured IP or SSH network. Peer send
acknowledgements mean the hub queued the packet, not that a remote application
consumed it. There is no automatic retry of companion commands after failure.

## Shared host connection

Pocket uses one managed hub owner for each configured USB or RFCOMM device.
MeshCore, the peer byte tunnel and onboard LoRa attach to separate services on
that connection. Disconnecting MeshCore releases its BLE lease and local port;
it leaves LoRa and the physical connection running. Disconnecting Reticulum
releases only its LoRa attachment. A physical connection failure closes every
attachment; reconnect explicitly. Commands are not replayed.

To use onboard LoRa from the shell:

1. Configure and connect the HTIT MeshCore connection once. This registers the
   hub on the device running that service; BLE availability does not gate LoRa.
2. Select that device's Reticulum owner and disconnect its current radio.
3. Open **RNode connections**, choose **Shared hub**, then select the HTIT.
4. Select a saved radio profile and connect the radio in Reticulum.

The saved selection names the hub, not a temporary `/dev/pts` port. Each
connection resolves a fresh local endpoint. Merely starting the hub owner or
opening the LoRa endpoint does not enable RF; explicit radio configuration and
radio-on acquire the LoRa lease. The standalone `hub_transport.py bridge
--rnode` command remains available for diagnostics, but must not open a device
already owned by Pocket.

## Build

Use Python 3.11–3.13 and PlatformIO 6.1.18. The project pins Espressif32 6.10.0
(ESP-IDF 5.4.0). From this directory:

```sh
python3 -m venv .venv
.venv/bin/pip install platformio==6.1.18
.venv/bin/pio run
```

PlatformIO installs its compiler and SDK. If an interrupted initial install
leaves the IDF Python environment incomplete, recreate that environment rather
than using arbitrary latest SDK helper packages. The tested helper versions are
idf-component-manager 2.1.2, esp-idf-kconfig 2.5.1 and esp-idf-size 1.6.1.

This build requires working PSRAM and allocates bounded 512-frame output queues
for each host there. USB transmission is nonblocking so a contact-list burst
does not stall Bluetooth processing. The partition layout leaves space for
later planning but does not implement OTA,
boot personality selection or firmware switching.

## First hardware setup

1. Identify the chip and flash size with esptool. Require original ESP32 and
   confirm the board is HTIT-TB. Preserve a complete flash backup first.
2. Flash the generated bootloader at `0x1000`, partition table at `0x8000` and
   firmware at `0x10000`. Do not flash this image to an S3 or another radio.
3. Start with USB. Install `host/requirements.txt` into the host environment.
4. Run `python host/hub.py --port /dev/cu.usbserial-0001 info` (use the actual
   device path). No automatic BLE scan or radio connection occurs.
5. Run `... pair`. Enter a temporary 4–16 digit PIN privately. The hub becomes
   discoverable as `Pocket-HTIT-Hub` for two minutes. Pair the N810 with that PIN.
   Previously bonded hosts may reconnect outside the pairing window. No default
   Classic pairing PIN is compiled into the firmware.
6. Use BlueZ SDP to find the SPP channel. On Linux the helper accepts
   `rfcomm://MAC/CHANNEL` directly, without a privileged device binding. Existing
   `/dev/rfcommN` devices also work; preserve other radios’ bindings.
7. Run `... scan` on USB or RFCOMM. Record the desired radio's address and address
   type from the hub's scan. macOS CoreBluetooth UUIDs are not BLE MAC addresses.
8. Start the bridge using the exact address/type printed by the hub:

```sh
python host/hub.py --port rfcomm://00:11:22:33:44:55/1 bridge --ble aa:bb:cc:dd:ee:ff --address-type 1
```

The address is an example. First pairing prompts for the radio's six-digit BLE
PIN. The PIN is not saved by the helper; the ESP32 stores its Bluetooth bond in
NVS. If the radio changes its PIN or clears bonds, pairing may need to be redone.

The helper prints `MESHCORE_PORT=/dev/pts/N` on Linux or `/dev/ttysNNN` on macOS.
Keep it running. Select that PTY in Pocket's existing MeshCore owner config at
115200 baud. Connect explicitly in Pocket. `serial_client.py` supplies a narrow
PTY adaptation for the pinned MeshCore library, whose physical serial transport
otherwise tries to manipulate nonexistent DTR/RTS lines on a PTY.

For a laptop-to-N810 byte tunnel, each helper selects the other host ID:

```sh
# Laptop on USB (host 0); assume N810 is the first SPP session (host 1).
python host/hub.py --port /dev/cu.usbserial-0001 bridge --peer 1
# N810; may also add --ble ADDRESS --address-type TYPE to own MeshCore.
python host/hub.py --port rfcomm://00:11:22:33:44:55/1 bridge --peer 0
```

Read the actual host IDs from `info`/helper startup; SPP IDs are session-local.
Each side prints a `PEER_PORT` PTY. Applications can exchange bytes through them.
Only one helper should open each physical USB/RFCOMM device. A second laptop
SPP session is supported by the firmware but depends on the laptop's Bluetooth
Classic serial support; USB is the preferred laptop path.

On the tested Mac, opening the CP2102 USB device can reset the HTIT even with
DTR/RTS deasserted. Keep one USB helper open during a session; reopening it can
interrupt a concurrent Nokia connection. Startup retries only the harmless hello
request, never radio commands.

The hub never fetches chat messages autonomously. Pocket automatically requests
pending messages after setup and on a messages-waiting notification. Fetching
consumes the radio’s queued copy; contact and channel queries do not. Contact
sync allows 60 seconds (350 contacts took 13.2 seconds in the USB hardware test).

Ctrl-C releases ownership and disconnects BLE. Cable loss is handled by a
30-second ownership lease (up to 60 seconds while awaiting a pairing PIN).
Oversized BLE writes fail explicitly rather than being arbitrarily fragmented.
Connection loss or queue exhaustion ends the session; queued commands are not
replayed into a new connection. Callback event loss reboots the hub to avoid
continuing with corrupt connection state. These are prototype fail-closed
behaviors, not seamless failover.

## Tests

```sh
python -m unittest discover -s tests -v
```

The framing tests compile the same C parser used in firmware and compare it
with the Python host implementation under fragmentation, escaping, corruption,
truncation and overflow. The adapter integration test uses PTYs, the pinned
MeshCore library and an emulated hub; install Pocket's optional MeshCore
requirements to run it. It also verifies host-to-host byte framing. These tests
do not substitute for physical RFCOMM + BLE coexistence testing.

See `PROTOCOL.md` for the wire contract and `VALIDATION.md` for measured results.

## Next stages

1. Add SX1276 driver and service 3, with explicit frequency/settings and packet
   send/receive operations. Keep BLE radio ownership separate from local LoRa.
2. Add host endpoint identity, routing and acknowledgements before introducing
   Wi-Fi/LoRa alternate paths. Deduplication, TTL, loop prevention, bounded
   queues, link costs and delivery semantics are necessary for a resilient
   interconnect. A LoRa fallback cannot carry normal laptop network traffic at
   Wi-Fi rates. Never silently replay state-changing MeshCore commands.
3. Evaluate board-specific RNode or MeshCore firmware builds independently.
   Changing personality means selecting a verified image and rebooting; it
   will interrupt the bridge. Existing bonds/partitions need an explicit
   migration plan. There is no live firmware swapping in this prototype.
4. Add a Pocket flashing workflow only after device identification, per-board
   manifests, backups and recovery have been validated. No automatic flash
   selection or cross-device flashing is implemented here.

IBSS is outside this version. Its absence from the standard ESP32 driver is not
resolved by this design; adding it later remains separate feasibility work.

## Indicators and link security

On the original HTIT-WB V0.2 wiring (active-high GPIO23/25/22):

- Yellow (case label WiFi): brief heartbeat every two seconds, driven by the
  main service loop. WiFi remains disabled.
- Blue: off with no Bluetooth session; slow blink with a Classic host but no
  ready BLE radio; fast blink while connecting or during the Classic pairing
  window; solid when the BLE companion is ready. Payload traffic makes a brief
  dark pulse; control/status/lease packets do not count as payload activity.
- Green (LoRa): off when disabled; brief receive-mode heartbeat, solid while a
  packet is pending/transmitting, and pulses for received traffic.

SPP now explicitly requires both authentication and encryption. New Classic
pairing is accepted only during the two-minute USB-opened pairing window with
its supplied PIN; existing bonds reconnect outside that window. Legacy PIN
pairing is required for the Nokia and is weaker than modern Secure Connections.
Any authenticated bonded host can request the hub services; the owner lease is
concurrency control, not an access-control role. USB is a trusted local control
interface and has no application authentication. BLE requests Secure Connections,
MITM protection and bonding, and waits for successful security completion before
service discovery; negotiated security properties are not independently audited.

The firmware does not add end-to-end encryption to its framed payloads (CRC is
only an error check). Public MeshCore channels remain public over LoRa. Flash/NVS
and physical USB access are not protected against a person possessing the hub.
Do not erase bonds while updating; flash only the application partition.
