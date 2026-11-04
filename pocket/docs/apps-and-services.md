# Apps and services

See [Keyboard navigation](navigation.md) for the shared focus and tab-strip keys.

## Choose a source

Open **Connections**. The **Device** tab selects the device supplying System
telemetry and received packets. Local services attach automatically after launch.
To use another device, enter its address and choose **Connect SSH** or
**Connect peer**. Peer attachment requires a verified contact and a Device read
grant from that device; see [Connections](connections.md).

The service rows open System, Radio Feed, Reticulum, or Messages. Each row shows
availability and the selected owner. Opening an app does not connect a radio,
share a service, or send a message.

Use the **Reticulum** or **MeshCore** tab to select an independent owner. Each tab
keeps its own address. This permits, for example, a Nokia packet feed and a local
MeshCore companion. Disconnecting a device releases its attached owners while
preserving an owner selected independently afterward.

In an app's Settings, activate a receive, Reticulum, or MeshCore service entry to
open its Connections controls. An available provider is a local client binding;
check Connections for the owner's live availability.

## App sources

| App | Source and operation |
| --- | --- |
| System | Selected device telemetry; local observations when using this device |
| Radio Feed, Heard, Last heard | Selected receive source and retained observations |
| Stations, Station Map | Local Directory projection of received observations and installed map data |
| Services, Nets | Receive-derived information and retained schedules; these are not the device-service catalogue |
| Walk | Retained walk journals; active probing is a separate operation |
| Messages | Receive-derived messages plus independently selected Reticulum and MeshCore owners |
| Reticulum | Selected Reticulum owner; interface activation and sharing grants are explicit |
| Bluetooth, Radio, Radio Manager | Existing radio controls and owner state; a remote feed alone does not grant every hardware command |
| Reader, Library | Local document stores and configured content sources |
| Workbench, CW, Audio Monitor | Local processing or explicitly configured audio inputs |
| Terminal | Local shell process |
| Scenery and graphics demos | Local rendering; no remote service required |

Map Library, Winlink, and hardware experiments have separate integration and
acceptance requirements. Their presence in the source tree does not mean they
are available as shared device services.

## If a service is unavailable

1. Read the owner shown in Connections. Confirm that it is the device you intend.
2. For the device feed or System, check the Device attachment and its error.
3. For Reticulum or MeshCore, select that owner's tab. Attach its local
   configuration or existing socket; open its app to operate the radio.
4. For a remote Reticulum device, confirm the contact key, carrier connection,
   and grants on the supplying device. Attachment does not grant access back.

Retained packets can remain visible after disconnection. Their timestamps are
observations, not proof that a live radio link is working.

## MeshCore through an HTIT hub

A local MeshCore selection can use an explicit hub URI in `port`:
`htit://CLASSIC_MAC/SPP_CHANNEL/BLE_MAC/ADDRESS_TYPE`, for example
`htit://2C:BC:BB:9F:DF:72/1/FB:91:48:2D:AA:14/1` for the tested hub and Gordo.
This requires a Linux host with Bluetooth RFCOMM, the optional pinned MeshCore
runtime, and both Bluetooth bonds already established. No PIN belongs in the URI.

The Messages app's MeshCore **Connect** action starts its bridge, connects BLE,
and syncs contacts and configured channels. **Disconnect** closes that bridge.
Shell launch alone does not connect the radio. Loss of the owner closes the
bridge's parent pipe, ending its session; commands are never replayed.

Channels appear first. Use **[ Prev contacts** / **] Next contacts** to browse
all contacts, 32 at a time. Contact sync allows 60 seconds before failing.

After setup Pocket automatically pulls pending messages from the companion.
This consumes their copies in the radio's receive queue. Each received message
is committed to the private `messages.sqlite3` archive in the configured owner
state directory before Pocket requests the next one. The TUI shows the latest
32 messages; older messages remain in that archive. No LoRa test messages are
sent as part of connecting.

If archive storage fails, automatic retrieval stops and the connection closes;
the unsaved message is retained in owner memory for a manual reconnect/save
attempt. MeshCore provides no transactional acknowledge-after-disk-write command,
so a power failure between radio dequeue and local commit can still lose that
in-flight message. The hub itself is a transport and does not maintain a mailbox.
