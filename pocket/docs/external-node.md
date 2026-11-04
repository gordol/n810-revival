# External Reticulum execution

Use **Reticulum → Radio → Board** to choose a USB serial port, an encrypted
Classic RFCOMM endpoint (`rfcomm://ADDRESS/CHANNEL`), or a private local owner
socket (`unix:///absolute/path`). Disconnect before changing the board or mode.
The socket can be an existing encrypted SSH forward. Raw TCP is not accepted.

Choose **Auto** to prefer a ready external executor and use the local backend
otherwise. **Disabled** uses the local backend without polling the board.
**External only** prevents local fallback. Connect once; Auto subsequently
switches when the node becomes ready, disappears, or returns. Detection polls
once every 20 seconds; executor event/lease failures trigger recovery sooner.
Refresh reads status immediately. No configured endpoint means no node scanning.

A reachable modem is not necessarily an executor. Legacy schema-2 provisioning
reports identity and radio settings but cannot accept Pocket links, resources or
LXMF endpoints. Auto keeps those applications local until the complete API below
is advertised. A former USB RNode port can be selected as the external endpoint. That port is
then reserved for node control: local fallback needs a separate radio. Pocket
will report it unavailable rather than send RNode setup commands to the executor.
The first successfully observed board identity is pinned. A
replacement identity requires explicit Board reselection.

The host keeps the application identity across handoffs. It drains outstanding
service operations, stops the old runtime, and starts the selected backend through
the existing NativeBackend and service bridge. New commands during a handoff are
rejected. Interrupted commands are never replayed: their result can be unknown.
External-only loss reports an error instead of silently starting a local radio.
Explicit sharing grants and discovery settings follow automatic backend changes
within the same controller session. The new runtime validates those grants
again before reporting ready. Open apps resubscribe through the existing provider
when a backend replacement ends their subscription. Revocation removes grants, and an explicit
disconnect clears them. Messages and service commands are never replayed.
A ready node returning to either Auto or External only wakes the existing
connection-recovery loop. Missing local fallback configuration leaves management
available and does not prevent recovery when the external node returns.
Disposable session sockets use the same ownership receipts and lifetime locks as
other local services. A dead socket is removed only when its receipt still
matches, no owner holds its lifetime lock, and no listener accepts a connection.
Unknown, replaced, live or locked sockets remain untouched.

## Executor contract, version 1

The host, integration-test executor and merged Heltec firmware implement this
contract. Board firmware must pass the physical Auto, service and messaging
acceptance tests before deployment. The software fixture is for host tests only
and must not be installed on a board.

USB/Classic provisioning retains KISS command 0x86 and reply 0x87, carrying
MessagePack `[operation, sequence, data]`. GET_INFO operation 2 may include key
128 with this metadata (string keys):

```
protocol: 1
abi: 2
identity: <32 lowercase hexadecimal characters identifying the board>
features: [links, endpoints, resources, lxmf]
lease_seconds: <number from 1 through 5>
online: true
available: true  # optional: free or owned by this physical connection
framing: kiss-fragment-v1  # USB/Classic; raw PS02 remains valid for local IPC
fragment_size: 1024
clock: unix-ms-v1  # optional: accepts host wall clock at native_open
```

All four features and a ready radio interface are required. The metadata identity
must equal the existing provisioning transport identity. A private Unix executor
returns the same metadata from the `node_info` owner action.

When `clock: unix-ms-v1` is advertised, `native_open` includes `unix_ms`, the
host's Unix time in milliseconds. It must be a positive signed 64-bit integer;
booleans and floating-point values are rejected. This field is optional and
valid only on `native_open`. Hosts omit it for older executors. The executor
uses it for LXMF timestamps and announce emission times, while lease, routing
and request deadlines retain their monotonic clock.

KISS command 0x88 carries the existing PS02 owner protocol, including its bounded
binary framing. Each envelope adds an integer `channel`; replies and pushed
events echo that channel. Provisioning and owner traffic share one reader and
one serialized writer. Hosts allow at most eight channels, with bounded queues.
There is no JSON or native address on the wire.

Large PS02 frames use KISS command 0x89 when `kiss-fragment-v1` is advertised.
Each fragment has an eight-byte network-order header: message ID (uint32),
offset (uint16), total PS02 frame length (uint16), followed by 1–1024 payload
bytes (or the negotiated size, bounded to 256–2048). Total length is at most
32768. Offsets must be contiguous within each message. Receivers retain at most
eight assemblies and discard partial messages after ten seconds without a chunk.
No operation executes before reassembly and normal PS02 validation complete.

Renewals, cancellations, callback replies and provisioning can preempt bulk
transfers between complete fragments. Bytes from different frames never
interleave. A transport close aborts remaining fragments without replay. This
keeps control requests responsive even with worst-case escaped binary payloads;
it does not increase lease durations or write timeouts.

`available: false` means another physical client holds the context. The current
lease owner's probes must report true. Auto keeps execution local while another
client owns the board; `native_open` still enforces exclusivity against races.
Status and radio metrics remain readable when capabilities or interfaces are
not ready, independently of application-offload readiness.

Owner requests contain `version: 1`, `action` and, after opening, `session` (a
random 32-character host session identifier). Implement these actions:

| Action | Request fields | Response |
| --- | --- | --- |
| `native_open` | `identity`, `abi: 2`, `session` | Metadata above; claim an exclusive endpoint lease |
| `native_call` | `operation`, `arguments` | `result` integer, `outputs` byte arrays; negative result includes `native_error` |
| `native_cancel` | `session` | Cancel stamp computation without waiting on the native worker lock; integer `result` |
| `native_renew` | `session` | Acknowledge lease extension |
| `subscribe` | `session` | Stream `session`, `ready: true`, then event envelopes |
| `native_callback` | `token`, `data` bytes | Acknowledge synchronous callback result |

`native_call` uses the pinned Pocket native ABI 2. The authoritative signatures
are `signature_types` in `native_stack.py`; the shared wire operation allowlist,
input/output buffer positions, capacities and strings are in `native_rpc.py`.
An input buffer becomes bytes; an output buffer becomes a null argument and its
bytes return in `outputs`, in declaration order. Fixed outputs must have exactly
the declared size. Variable outputs must match `result` and stay within capacity.
Buffers are limited to 32768 bytes. Handler allowlists contain 16 bytes per peer,
so their count argument is a peer count, not a byte count.

`init` carries `[null, session_bytes]`. The executor supplies its own callback and
storage location; a host filesystem path is never used on the board. All other
operations preserve ABI semantics, including identity import/export, destination
registration, links, request/reply, resources and native microLXMF. Existing
Pocket permissions, contact policy and service grants remain enforced by the
host. The executor owns actual radio transmission, reception and core polling;
the host consumes pushed events rather than polling the board at display speed.

Push events contain `session`, `native_event` (the existing ABI MessagePack event
bytes), and an optional `callback` token. Resource-advertisement callbacks await
`native_callback`; that action must remain responsive while a native worker is
waiting. The executor handles outgoing-radio callbacks locally. Cancellation,
lease renewal and callback replies must not queue behind expensive stamp work.

A lost/reset context must stop transmitting before its lease expires. Reject
requests from expired or other sessions. Successful ABI `reset` acknowledges
release. Without that acknowledgement the host closes all pending channels,
stops renewing, waits a full negotiated lease interval after closing, then permits local
replacement. Scope release to the host's context: do not reset an independently
running board router, IBSS service, or another owner's endpoints. Queued work
must not extend the lease or execute after expiry.

The configured executor receives application private identity material to act as
those endpoints. Use only a trusted board. Do not expose this API to anonymous
network peers, log key buffers, or persist imported keys beyond the selected
storage policy. Classic RFCOMM requests Bluetooth medium security (encrypted
link); failure to establish it fails the connection. Local sockets must be
private and user-owned; remote forwarding must remain encrypted. USB relies on
physical attachment trust.

## Acceptance

Run from the repository with its native library and RNS/LXMF test environment:

```
python tests/integration/auto_runtime.py
POCKET_TEST_NATIVE_ROLE=a POCKET_TEST_EXTERNAL_ROLE=a python tests/integration/service_mesh.py
POCKET_TEST_NATIVE_ROLE=b POCKET_TEST_EXTERNAL_ROLE=b python tests/integration/service_mesh.py
```

`tests/fixtures/native_executor.py` executes the real native library in a
separate process. Auto acceptance covers local → external → local on loss →
external on return, identity continuity, Disabled, and External-only refusal.
The mesh test exercises the existing service bridge against stock RNS/LXMF,
including resources, subscriptions, grants/revocation and signed messaging.
`tests/test_native_rpc.py` checks binary framing, interleaved provisioning/RPC,
buffer bounds and interrupted requests. These are host acceptance tests; radio,
board memory, encrypted RFCOMM and hardware lease-expiry acceptance remain
required before claiming physical offload is ready.

### Physical acceptance (exclusive board access)

`tests/integration/hardware_auto.py` takes `--endpoint`, `--fallback-config` and
`--evidence`. Add `--peer-socket` for end-to-end acceptance: it requires a
real service call and a signed LXMF message/receipt in both directions in every
phase, with the offloaded message timestamp matching the host wall clock. Without a
peer it checks connectivity only. Run it with the native library and real executor
firmware available. The fallback configuration selects one native TCP or RNode
interface; an RNode configuration must preserve the existing radio settings.
Stop any other owner of that radio first. This runner uses isolated application
identities and temporary state. It deliberately closes the external connection,
checks local takeover, permits reconnection, and requires the same application
identity after return. It does not reboot or flash the board. It restores only
its own test connection; it does not manage production owners.
Unexpected executor failures fail the run even if automatic recovery later
succeeds. The report separates backend readiness from service and signed-message
completion times; the deliberate connection loss and final shutdown are excluded
from unexpected failures.

For the service suite, `POCKET_TEST_EXTERNAL_ENDPOINT` selects the physical
executor instead of the fixture. `POCKET_TEST_HARDWARE_INTERFACE` names an
additional stock-RNS interface configuration section for the test hub, providing
the actual packet path to that board. Use it with the existing native/external
role variables. Hold exclusive USB/RFCOMM access for the entire test. Success
requires the same service and LXMF assertions as the simulated-executor test;
status queries alone do not pass acceptance.

### Portable native-call dispatcher

Firmware can include `shell/native/reticulum/rpc_dispatch.h` and call:

```
auto result = pocket_rpc::dispatch(operation, encoded_arguments, length,
    pocket_rpc::Context{event_callback, executor_storage});
```

`operation` is a `std::string` and `encoded_arguments` is the standalone binary
MessagePack argument array, without PS02 headers. `Result` owns `result`,
`outputs` (byte arrays), and `native_error`. `pack_result(packer, result)` writes
those fields plus `version: 1`; the transport adds its channel/session envelope.
Argument spans returned by `Reader(raw, length).read()` borrow the input frame,
which must remain alive until the operation completes. No pointer is decoded
from the wire. `init` requires a null callback placeholder and uses the injected
callback/storage, discarding the second wire argument as a filesystem location.

The dispatcher owns validation and ABI calls only. Firmware still owns session
checks, leases, scheduling, event callbacks and asynchronous stamp work. It may
intercept `lxmf_send` before invoking the synchronous native operation. No OS
threads or filesystem operations are introduced by the header.

Build the boundary tests and an optional bridge to the real native library with:

```
python tests/integration/native_rpc_dispatch.py --native-build /path/to/pinned/native/build --bridge-output /tmp/pocket-rpc-dispatch.so
POCKET_TEST_CPP_DISPATCH=/tmp/pocket-rpc-dispatch.so POCKET_TEST_NATIVE_ROLE=a POCKET_TEST_EXTERNAL_ROLE=a python tests/integration/service_mesh.py
```

Use `.dylib` for the bridge on macOS. The first command checks every operation,
invalid/truncated arguments, buffer/result bounds and ignored host storage paths,
then runs 100,000 decoder mutations with address/undefined-behavior sanitizers.
The second uses that compiled dispatcher with the real native core and stock
RNS/LXMF peers. These checks require a C++17 compiler and an already prepared
native CMake build; they access no physical device.

The companion `request_decode.h` validates the outer owner map after transport
framing has been checked:

```
auto request = pocket_rpc::decode_request(body, length);
auto result = pocket_rpc::dispatch(request.operation,
    request.arguments.data, request.arguments.size, context);
```

`Request` owns the action/session/identity/operation/token strings and exposes
integer `channel`/`abi`. Its `arguments` and `data` spans borrow the immutable
request body until execution completes. Invalid input throws
`std::invalid_argument`; decoding never executes an ABI operation. Firmware must
check its lease/session before dispatching the decoded operation.

Only the six native actions and their exact field sets are accepted. The map is
limited to 16 string-key fields, with no duplicates or trailing data. Version is
1, channel is a positive int32, and session/identity are 32 lowercase hexadecimal
characters. Arguments remain a validated flat MessagePack array; callback data
is binary. Unknown fields, nested objects, wrong types and oversized strings
are rejected. Native boundary tests also cover every truncation of valid maps
and 100,000 mutations of valid outer requests, in addition to argument mutations.

An isolated stock reference can be started on the laptop with
`hardware_auto.py --stock-peer SOCKET STATE CONFIG_DIRECTORY`. Its native/UDP
interface configuration must be explicitly enabled. The handset client connects
to its private owner socket through existing SSH forwarding when needed; it
imports no Python RNS or LXMF. Use temporary state for both test identities.
