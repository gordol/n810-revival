# Hub protocol version 1

USB and each authenticated SPP connection carry the same binary stream.
A frame is `7e escaped-body 7e`. Inside the body, `7e` and `7d` are escaped as
`7d` followed by the original byte XOR `20`. Consecutive delimiters are allowed.
A delimiter resets parsing after malformed input. Boot-console noise is ignored.

Unescaped body, little-endian integers:

| Offset | Field |
| --- | --- |
| 0 | version, 1 |
| 1 | service |
| 2 | operation |
| 3 | uint16 request ID |
| 5 | uint16 payload length, 0–512 |
| 7 | payload |
| 7 + length | uint16 CRC-16/CCITT-FALSE over header + payload |

Requests have bit 7 of operation clear. Replies use request operation OR `80`
and the same ID/service; their first payload byte is status. Asynchronous events
use operations `90` and above and ID zero. Peer receive events retain the sending
request's ID as an opaque correlation value. No automatic retry is implied.

Status: 0 success, 1 bad argument/peer unavailable, 2 busy/not ready, 3 not owner
or permission denied, 4 transport error, 5 unsupported, 6 payload exceeds BLE MTU.

## Service 0: management

| Operation | Request | Success reply after status byte |
| --- | --- | --- |
| 1 hello | empty | protocol, host ID, service bitmap (0f) |
| 2 status | empty | owner (ff=none), BLE ready, BLE connected, scanning, MTU uint16, SPP1 online, SPP2 online |
| 3 scan | empty; owner required | empty; five-second active BLE scan |
| 4 connect | address type (0 public/1 random), six address bytes in printed order | accepted; wait for ready event |
| 5 disconnect BLE | empty; owner required | accepted |
| 6 passkey | six ASCII digits; owner and pending request required | accepted |
| 7 claim/renew | empty | exclusive MeshCore ownership, 30-second lease |
| 8 release | empty; owner required | accepted; BLE closes |
| 9 Classic pairing window | 4–16 ASCII PIN digits; USB only | two-minute discoverable window |

Events: 90 scan result (address type, address[6], signed RSSI, UTF-8 name bytes),
91 scan complete, 92 failure/disconnect/lease expiry, 93 BLE ready, 94 passkey
required. Events 91–94 carry explanatory UTF-8 text, never the PIN.

A new owner cannot claim while a prior BLE connection is still closing. Only
one selected BLE radio is connected; no name-based automatic selection occurs.

## Service 1: external MeshCore companion

Operation 1 carries exactly one unmodified BLE companion command payload.
Only the current owner may send. Reply 81 reports the GATT write result, not
MeshCore execution or LoRa delivery. Event 90 carries one received BLE payload.

Host serial adaptation removes the MeshCore `< lengthLE16` header before sending
and adds `> lengthLE16` to incoming payloads. BLE payload boundaries must survive
the serial stream. The hub rejects commands exceeding negotiated MTU minus 3;
it never guesses a fragmentation scheme. Maximum hub payload is 512 bytes.

## Service 2: host-to-host data

Operation 1: destination host ID followed by 0–511 data bytes. Destination must
be connected and different from sender. Event 90: source host ID followed by
those bytes. Reply 81 means queued at the hub, not consumed by the application.
USB is host 0; SPP sessions occupy IDs 1 and 2 until disconnection. Applications
requiring reliable delivery must add end-to-end sequence/acknowledgement logic.

## Service 3: onboard RNode-compatible LoRa

Independent of the MeshCore lease. Radio starts off; configuration is not persisted.
Host IDs are shared, but either service can have a different owner. A disconnected
SPP owner or expired 30-second lease stops the radio. USB owners must release or
allow the lease to expire. Any valid owner request renews its lease.

| Operation | Request | Success reply |
| --- | --- | --- |
| 1 claim/renew | empty | empty; busy if another owner holds lease |
| 2 configure | frequency u32LE, bandwidth u32LE, SF u8, CR denominator u8, power dBm u8 | empty after register readback; radio must be off |
| 3 state | one byte: 0 off, 1 receive | empty; does not transmit |
| 4 transmit | 1–508 RNode payload bytes | empty only after all fragments finish transmitting; no delivery guarantee |
| 5 status | empty, no ownership needed | owner u8 (ff none), enabled u8, busy u8, then 11-byte configuration |
| 6 release | empty | empty; stops radio |

Event 90: RSSI i16LE dBm, SNR i8 quarter-dB, then reassembled packet bytes.
The SX1276 driver supports 850–950MHz, bandwidth125/250/500kHz, SF7–12,
CR4/5–4/8, PA_BOOST2–17dBm. Unsupported profiles are rejected without clamping.
On-air format uses sync0x12, explicit header, CRC, normal IQ and RNode's sequence
nibble/split flag. Payloads above254bytes use two fragments; at most508bytes.
Split receive state expires after30seconds. CAD with randomized busy backoff
precedes a transmission; hardware timeout is60seconds, with no automatic replay.
The initial adapter does not implement RNode's configurable airtime-limit policy.

`rnode_adapter.py --port rfcomm://MAC/CHANNEL` exposes an RNODE_PORT PTY for an
ordinary RNS RNodeInterface. Its KISS firmware response1.52 indicates compatibility
level; it is not a claim to run official RNode firmware. Firmware flashing,
Bluetooth setup, display controls and nonzero airtime-limit commands are unsupported.

## Resource and failure bounds

Firmware: 48 callback events, 512 outgoing frames per host, 512 bytes per
payload. Queue exhaustion drops the affected host or resets the hub when
callback events are lost. Hosts must stop when acknowledgements or the BLE
connection fail. There is no reconnect replay, hidden radio scan or automatic
MeshCore command. USB exposes local management to its physical host; Classic
hosts must pair/bond. CRC detects accidental corruption, not malicious traffic.
