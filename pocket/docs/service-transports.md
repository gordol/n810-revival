# Service transports

## Purpose

Use an existing owner service through a local socket or a remote Reticulum link.
Applications retain the same snapshot, command and subscription contract.
SSH-forwarded Unix sockets remain supported. Carrier profiles use the existing RNS
TCP, LAN, serial, KISS and AX.25 interfaces. USB serial and Bluetooth SPP use the
same serial adapter after the operating system exposes their device port.

## Use a remote Reticulum owner

1. Attach to your local Reticulum owner in Connections and connect its interface.
2. On the serving device, verify the client’s full public fingerprint. In Data,
   select that client and choose **Share read (C)**. Confirm the displayed scope.
   Choose **Allow send (W)** instead to permit sending messages through the owner.
3. On the client, verify the serving peer, then choose **Use peer (U)** in Data.
   Alternatively, enter its full identity in Connections → Reticulum and choose
   **Reticulum peer (C)**.

The local owner remains the transport gateway while the app uses the remote
owner. Choose the original local configuration/socket to return to it. Using a
remote service does not grant reciprocal access. Revocation closes that peer’s
subscriptions without affecting other peers.

## Export another owner service

Create `service-exports.json` in the serving RNS owner’s state directory, owned
by that user with mode `0600`, before starting the owner:

```json
{
  "notes": {
    "socket": "/absolute/path/to/notes.sock",
    "operations": ["put"]
  }
}
```

The target implements application version 1 over binary wire version 2:
MessagePack requests and replies prefixed with `PS\x02` and a four-byte
network-order payload length. `snapshot` and `subscribe` retain versioned snapshots.
Both endpoints must be upgraded together; legacy JSON wire input is rejected.
Its command handler validates its own payloads. Registration makes the service
available for explicit grants; it does not advertise or share it automatically.

Through the local owner protocol, `service_share` takes `peer`,
`expected_public_key`, `service`, and an explicit `operations` list. Grant
`snapshot` and `subscribe` for reads; add only the named commands required.
Trust management and further sharing are not automatically delegated. Reading
`snapshot` from the reserved `$catalog` service returns only the services and
operations granted to the authenticated requesting peer.

`ReticulumTransport(gateway_socket, peer_identity, service_name, timeout=25)` implements
`exchange(request)`, `subscribe(callback, stop_event)`, and `close()`.
`SocketTransport(socket_path)` implements the same interface; an explicitly
selected numeric-loopback TCP socket can also supply the local stream. Cleartext
TCP to other devices is rejected; use SSH or the encrypted Reticulum adapter. Set the Reticulum timeout from
5 to 600 seconds for slower links; it covers network request/response delivery. The existing app `Provider`
accepts either adapter. Other applications can bind that provider through their
existing declared service dependency.

## Delivery and bounds

Messages are limited to 32 KiB. Streams use bounded length framing. RNS requests
and Resources handle transfer of messages larger than an individual packet;
there is no second fragmentation protocol. Response size is checked before
accepting a resource.

Commands have request identities, bounded duplicate suppression and explicit
results. They are never retried automatically. A timeout can leave the outcome
unknown; inspect the service before choosing to submit another command.
Duplicate suppression is bounded and does not promise exactly-once execution
across process restarts or retention eviction.

Subscriptions push snapshots. Each peer/service subscription retains at most one
outgoing snapshot and the latest replacement, so a slow link cannot accumulate
an unbounded queue. This is a current-state subscription, not a lossless event
log; services needing complete history must expose a bounded history operation.
There are at most 16 grants, 16 remote subscriptions, 16 served subscriptions,
and four simultaneous service requests per gateway. Local owner connection
limits can impose a lower limit. Path requests are rate-limited.

## Disconnect and failure

Cancel closes the selected subscription. Revocation checks permissions again on
requests and outgoing updates, closes matching links, and rejects late updates.
Independent owners keep running. No service connection or sharing grant is
created merely by opening the shell.

## Select carriers

Use an interpreter with the reviewed RNS/LXMF runtime and pyserial. Create a
user-owned `reticulum-owner.json` in a configuration folder (mode `0600`):

```json
{
  "mode": "local",
  "state": "/absolute/private/owner-state",
  "interpreter": "/absolute/runtime/bin/python",
  "station": "desktop",
  "carriers": [
    {"type": "tcp-client", "host": "192.0.2.10", "port": 4242}
  ],
  "relay": false
}
```

Open Connections, select Reticulum, enter that folder, and choose Local
configuration. Open Reticulum and choose Connect. Selection starts an idle local
owner; Connect activates its configured interfaces. The other device can use a
`tcp-server` profile with its explicit listening address and the same port.
Verify peers and grant service access separately. No service access is granted
by establishing the carrier. Detach in Connections to stop a gateway started by
this shell; borrowed or external owners keep running.

Replace the entries in `carriers` as needed; up to eight can run together:

| Type | Required fields | Optional fields |
| --- | --- | --- |
| `tcp-client` | `host`, `port` | — |
| `tcp-server` | `host` (listening IP), `port` | — |
| `lan` | `devices` (e.g. `["wlan0", "eth0"]`) | — |
| `serial`, `usb`, `bluetooth` | `port` (device path) | `speed` (default 115200) |
| `kiss` | `port` | `speed`, `preamble`, `txtail`, `persistence`, `slottime` |
| `ax25` | `port`, `callsign` | KISS fields plus `ssid` (default 0) |

Serial ports use 8 data bits, no parity, one stop bit. USB and Bluetooth profiles
require an existing OS serial mapping; this does not implement USB device mode,
Bluetooth pairing, or BLE GATT. A USB network interface or Bluetooth PAN can use
the IP carriers instead. LAN uses RNS AutoInterface on the selected devices and
requires working link-local IPv6. Setting `relay: true` explicitly permits RNS
forwarding between carriers; it does not delegate access to local services.
Stop an owned gateway before changing its carrier configuration. An existing
owner with a different configuration is rejected rather than silently reused.

## Security boundary

Service contents crossing devices must use authenticated encryption. Local Unix
sockets and numeric-loopback TCP can carry cleartext within the device. A cable
is not an encryption mechanism: serial, USB serial, and Bluetooth serial use the
same encrypted RNS links as radio or IP. Wi-Fi/Bluetooth link encryption is not
our end-to-end service security boundary. SSH forwarding terminates at the SSH
endpoints; RNS service encryption terminates at the authenticated service gateways.

Our service bridge uses RNS Links with pinned peer keys and explicit permissions.
Links provide encrypted and authenticated content and forward secrecy. Public
announces, routing information, traffic timing and sizes are not promised to be
confidential. Protect private identity keys and verify full peer fingerprints.
See [RNS link security](https://reticulum.network/manual/understanding.html) and
[SSH transport security](https://www.rfc-editor.org/rfc/rfc4253.html).

AX.25 framing does not itself encrypt payloads. RNS can carry encrypted service
traffic in those frames, but that does not make it permissible on every band.
US amateur stations generally may not transmit messages encrypted to obscure
their meaning under [47 CFR 97.113(a)(4)](https://www.ecfr.gov/current/title-47/section-97.113).
Use encrypted services only on carriers where permitted. Public amateur-radio
applications such as APRS do not become private service-mesh carriers.

## Verification

`tests/integration/service_mesh.py --carrier serial` tests three real RNS owners
through virtual serial cables. `kiss` and `ax25` exercise the corresponding
upstream framing implementations through simulated modem links; `tcp` uses
loopback. These tests cover large commands, pushed snapshots, peer permissions,
multiple subscriptions and revocation. Captures check for test payload leakage;
this is not a cryptographic audit. `carrier_lifecycle.py` verifies idle selection,
explicit connection, borrowed-owner lifetime and owned shutdown. Physical radio,
Bluetooth, USB and LAN interface acceptance remain hardware-specific checks.
