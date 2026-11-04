# Connections

## Purpose

Attach a device and use its feed, System telemetry, Reticulum and MeshCore services together. Individual owner selection remains available. Opening the shell creates
no peer connection, discovery broadcast, or service advertisement.

## Open a service

Click a service row, or press **I** for System, **F** for Radio Feed, **R** for
Reticulum, or **M** for Messages. The row shows its selected owner and availability.
Opening a service does not connect a radio or send traffic. For independent owner
selection, use the Reticulum or MeshCore tab. See [Apps and services](apps-and-services.md).

## Unix sockets

Enter the absolute path of a directory containing `aprs.sock` and `replay.sock`,
then choose **Socket folder**. The first supplies live events; the second supplies
bounded retained snapshots. The service process owns the hardware independently
of the shell. Filesystem permissions determine access to these local endpoints.

Multiple shells may subscribe to the same owner. Disconnecting one shell does
not stop the owner or detach the others. Use a different `INSTANCE` for each
simultaneous shell to keep preferences and application stores separate.

## SSH

Enter `user@host` or an SSH configuration alias, then choose **SSH**. This retains
the existing OpenSSH Unix-socket forwarding adapter. The default N810 profile
uses `~/.ssh/id_rsa_n810` and the existing N810 host-key alias. Verify the host key
and establish normal SSH authentication before using this control.

The installed remote shell must provide `/usr/local/share/n810-pocket/device_services.py`. Its private binary catalogue supplies System telemetry and the configured Reticulum and MeshCore owner sockets. The radio feed uses `/dev/shm/n810-aprs.sock` and `/dev/shm/n810-aprs-replay.sock`. Missing radio services do not prevent System attachment. The adapter checks strict host keys and uses
noninteractive key authentication. A connection failure is displayed inside the
shell. It does not prevent local applications from running.

After you choose a device, temporary startup failures and a lost connection are retried automatically, with a delay of up to 15 seconds between attempts. Services that finish starting later are attached automatically. Recovery preserves service owners you selected independently afterward, including an explicit per-service disconnect. System telemetry does not wait for an optional radio owner to start. Invalid configuration still needs correction. Recovery does not repeat radio commands or send messages.

Disconnect cancels automatic retries and detaches the shell. A reusable SSH master can remain running; the
shell does not terminate a tunnel that another consumer may use. Pending
attachment cancellation rejects a late result; a bounded SSH operation already
in progress may finish before its worker exits.

## Availability

**Connecting** means attachment work is in progress. **Waiting** means an
endpoint has been selected but its service is unavailable. **Attached** means the device catalogue is connected (or the feed is connected for a Unix receive-socket attachment). The service rows show **starting**, **ready**, or **unavailable** independently. A ready service can be opened while another service is still starting. Reticulum and MeshCore service readiness means their controls are available; radio connection progress is shown in the corresponding app. It does not prove
that the radio is receiving RF or that any message was delivered.

## Independent services

Select the **Device**, **Reticulum**, or **MeshCore** tab to choose the attachment to edit. **Tab / Shift-Tab** moves focus between the tab strip and controls. When the tab strip has focus, **Left / Right** changes the selected tab. **[ / ]** switches tabs directly. Each service keeps
its own selected owner and address. Switching the controls does not detach either
service. Device disconnect detaches the services attached by that device connection. An owner independently selected afterward is preserved. Service disconnect affects only that selected service.

For Reticulum, **Local configuration** reads `reticulum-owner.json` from the
address folder (blank uses this instance’s state folder). It starts or attaches
the configured management owner, with its radio still idle. **Owner socket**
attaches to an existing `owner.sock`, including one forwarded separately through
SSH. Open the Reticulum app to operate that owner. Detaching an external owner
leaves it running; detaching a management owner started by this shell stops it.

## Discovery, trust and sharing

Reticulum’s signed announcements identify services by their original owner key.
The Heard page records these observations, including relayed announcements.
Discovery and names do not confer trust: save the contact and compare its full
fingerprint before verification. The existing RNS transport handles routing;
a relay does not become the service owner or inherit a grant.

In Reticulum’s **Data** page, select a verified peer. **Share read (C)** grants
access to the Reticulum service's contacts, messages and current-state events.
**Allow send (W)** also permits sending through that owner. Both show their scope
and require confirmation. **Use peer (U)** attaches the existing app to that
remote service through your local gateway; it does not grant access back.
**Revoke (D)** removes that peer's grants and closes its subscriptions.

In Connections → Reticulum, **C Reticulum peer** accepts the full verified peer
identity after a local gateway is attached. Returning to the original owner socket
or local configuration preserves that gateway. Disconnect releases both the remote
subscription and a gateway owned by this shell. Other independently owned services
remain running. Grants are not restored at launch. See [service transports](service-transports.md)
for exporting additional owner-protocol services and delivery limits.

SSH continues to authenticate through OpenSSH and local sockets through operating
system access controls. Reticulum data uses the existing owner’s RNS identity,
full-key verification, encrypted links and explicit per-peer operation grants.
Carrier profiles support TCP, LAN, serial/USB, Bluetooth serial, KISS and AX.25
through that owner. Service contents use authenticated RNS links on every carrier.
Cleartext owner TCP is limited to numeric loopback addresses. Three-instance TCP,
virtual-serial, KISS and AX.25 tests exercise relayed commands and subscriptions
without transmitting RF. Physical-device acceptance is separate.

## Connect a verified Reticulum device

1. On each device, attach its local Reticulum owner and connect the intended
   interface. Import the other device's contact card and verify its full key.
2. On the device supplying telemetry and receptions, open **Reticulum → Data**,
   select the verified client, choose **Device read G**, then **Grant Y**.
   This starts the existing local device catalogue if needed and grants only
   snapshots and subscriptions. It does not grant radio commands or message sends.
3. To share the Reticulum owner's contacts, messages and state as well, grant
   **Owner read C** separately. **Allow send W** adds explicit send permission.
4. On the client, choose **Use peer U** in Reticulum → Data. Alternatively, enter
   the full peer identity in Connections → Device and choose **Reticulum peer P**.

Connections shows System and Feed together. Separately granted owner services
attach through the same selected local gateway. Radio Feed and Last heard use
that device's original receive records and timestamps; there is no second radio
owner. A bounded recent window is transferred, with omissions reported as a
possible history gap. This is a live view, not bulk history synchronization.

A verified direct contact can establish an encrypted link without a public
announcement or path probe. Existing cached routes also work. A fresh hidden
multi-hop route still requires an established carrier route; the shell does not
turn on public discovery to work around that limitation.

If attachment says **Peer has not shared device read access**, grant Device read
on the supplying device. If the link is unavailable, check both interfaces and
contact keys. Disconnect cancels this client's subscriptions and preserves its
local Reticulum gateway. **Revoke D** on the supplying owner removes the peer's
service access. Independent service selections are preserved when they no longer
belong to the detached device.

## Preferences

The address field is saved with this instance's view preferences. Restoring it
does not connect. `make n810 SSH_TARGET=user@host` or `LINK=/path/to/sockets`
prefills the field for this launch. `SSH_KEY=/path/to/key` selects an explicit
SSH identity file. Choose Connect SSH or Socket folder inside Connections to attach.

## Local startup

After its first display, the shell attaches local receive/status services and
configured local Reticulum or MeshCore owners in background workers. New owners
stay idle until Connect. After an explicit Connect, that owner remembers the
selected radio and resumes it after restart. Disconnect disables recovery.
Changing the saved target requires a new Connect. Sharing remains explicit.
Saved external sockets and remote peers are not automatically attached.
Use `make n810 EXTRA=--no-local-services` to start with everything detached.
Missing local owner configurations are skipped; configuration errors appear in
Connections without preventing the shell from opening.

## Connection scope

SSH attaches the device catalogue, System telemetry and each configured radio-service owner together. System displays the selected device's CPU, memory, battery and link observations. Samples arrive over the existing bounded binary subscription every five seconds; drawing a window does not run a remote command. The SSH badge follows device connectivity, while the feed and radios report their own states.

The catalogue is a private, user-owned Unix socket accessed through authenticated SSH. It is not broadcast or publicly announced. It starts configured management owners; an owner resumes its radio only when its saved connection request matches that target. An unavailable service remains visible as unavailable. The remote catalogue and borrowed owners can remain running after a client detaches.

Reticulum is both a messaging service (LXMF) and a transport for explicitly
authorized Pocket service requests. Attaching a Reticulum owner exposes its
controls; Connect activates its configured interfaces. Choosing a remote service
over Reticulum requires a verified peer and that peer’s grant.


## External microReticulum node (host-side integration)

Reticulum → Radio shows the selected external node and the age of its latest
status response. Disconnect the radio before changing offload preferences.

- **Board B:** select a USB serial device on the owning computer, or
  `rfcomm://2C:BC:BB:9F:E0:E2/1` for the already-paired experimental HTIT.
- **Auto A:** monitor that board; retain local execution when application
  offload is unavailable.
- **Disabled O:** disable external offload and automatic polling. Local
  Reticulum remains available; **Refresh V** can still read board status.
- **External only X:** prohibit local fallback. Connecting reports the reason
  when the external node cannot delegate application endpoints.

The current experimental firmware identifies itself as microReticulum schema 2.
Pocket reads its identity, standalone mode and LoRa metrics over the binary USB
or Classic RFCOMM provisioning interface without changing radio settings or
network remote management. Background reads reuse one connection, every 20 seconds.

The host adapter now supports automatic external execution, local fallback and
return to the external node with the same application identity. It uses the
existing service bridge and native backend, including link, resource and LXMF
operations. See [External Reticulum execution](external-node.md) for configuration,
recovery behavior, the executor contract and acceptance commands.

Board firmware must advertise and implement that complete contract. Legacy
schema-2 status alone remains unavailable for application offload: Auto uses the
local stack and External only blocks local startup. Host integration tests use a
separate native executor against stock RNS; they do not establish physical board
or Nokia acceptance.

Packet history controls and retention settings: [Radio packet history](receive-history.md).

SSH setup runs in the background. `POCKET_SSH_CONNECT_TIMEOUT` sets its handshake
allowance (default 15 seconds, range 1–120). This does not delay the first shell
frame. Existing authenticated tunnels are reused. An incompatible device
directory is replaced under its startup lock only after verifying the local
socket peer, user, executable arguments and runtime; radio owners are retained.
