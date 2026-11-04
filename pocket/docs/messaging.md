# Messages

Open Messages from the shell. Press **p** to select APRS, Reticulum or MeshCore.
In Connections, select the matching service and attach its local owner or Unix
socket. Opening the shell does not connect radios or publish your identity.

## Reticulum

Press **o** to connect the configured owner. Select a contact and press **v**.
Compare the full fingerprint with the recipient over a trusted channel, then
confirm. Press **c** to compose and **Ctrl-S** to send. Enter does not send.
Received messages appear in the conversation; outgoing messages show their
current delivery state. A queued message is not evidence of delivery.

Discovery is off by default. Press **a** to publish or hide your messaging
identity; publishing requires confirmation. A fresh route may require explicit
public discovery. Hiding prevents future announcements and path-probe replies;
it cannot erase earlier announcements or existing routes. Service discovery is
controlled separately in Reticulum's Data page. Granting service access does
not publish your services. A private invitation/rendezvous flow is not available
yet; use SSH for private service access without public discovery.

The owner retains the most recent 32 message records in a bounded binary store.
Older LXMF history is read from the existing history file on first migration;
that file is preserved. Drafts remain in memory per owner and conversation.

## MeshCore

Use a MeshCore companion radio connected by serial/USB to the machine running
its owner. Install the pinned client into a separate Python environment:

```
python3 -m venv /absolute/path/meshcore-runtime
/absolute/path/meshcore-runtime/bin/pip install -r requirements-meshcore.txt
```

Create `meshcore-owner.toml` in a private configuration directory and set its
permissions to `0600`. Use absolute paths and your actual serial device:

```toml
state = "/absolute/path/meshcore-state"
interpreter = "/absolute/path/meshcore-runtime/bin/python"
station = "pocket"
port = "/dev/ttyACM0"
baudrate = 115200
trusted_peripheral = true
```

In Connections, select MeshCore, choose Local, and enter that directory. Then
open Messages, select MeshCore and press **o**. The owner reads existing contacts
and channels; it does not advertise, change radio settings or send chat at startup.

Select a contact, press **v**, and compare the entire public key before confirming.
Press **c** to compose and **Ctrl-S** to send. Messages are limited to 160 UTF-8
bytes. Ambiguous contact key prefixes are rejected. Direct sends show radio
acknowledgements; channel sends have no group delivery receipt. Public channels
are labelled public; shared-key channels do not authenticate individual members.
Press **d** to disconnect.

The serial companion connection is cleartext and requires a physically trusted
peripheral. To use an owner on another computer, forward its Unix socket through
SSH and select that local socket. This adapter provides MeshCore messaging; it
does not carry arbitrary Pocket services over MeshCore. Native BLE pairing is
not implemented. Reticulum service transport remains a separate adapter.

## Troubleshooting

- **No owner:** select the protocol's owner in Connections before connecting.
- **No route:** check the remote Reticulum owner and its discovery choice.
- **Unverified contact:** compare and confirm its full fingerprint/key first.
- **Unconfirmed send:** delivery is unknown. Inspect the conversation before
  deciding to resend; the MeshCore owner does not automatically retry.
- **Wrong protocol / binary frame error:** upgrade both service endpoints.
  The new wire format does not fall back to JSON.

The messaging update is installed on Nokia. Physical MeshCore hardware acceptance remains pending.
