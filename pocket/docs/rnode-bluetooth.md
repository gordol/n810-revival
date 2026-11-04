# RNode Bluetooth

Open **Connections → Reticulum → H RNode connections**, or choose **RNode connections** from the Radio application menu. Select the local RNode owner first. Setup actions require its radio session to be disconnected.

For an RNode that needs Bluetooth enabled:

1. Attach USB to the owning computer. Use **USB port** to select its serial port.
2. Choose **Enable Bluetooth**, then **Pairing mode**. These use the existing RNode configuration utility. They do not flash firmware or configure the LoRa radio.
3. Choose **BLE device** and enter `ble://` followed by the exact advertised name, for example `ble://RNode D76D`. A platform BLE identifier can also be used.
4. **Discover** lists nearby UART devices. **Stop setup** cancels discovery. **Pair** connects to the selected device and requests an authenticated RNode detection exchange.
5. Complete the operating system's pairing prompt using the code on the RNode display. A discovery result or BLE connection alone does not verify pairing. Pocket reports an authenticated RNode only after receiving its reply over the protected UART.
6. Choose **Connect radio** to start the existing Reticulum session with the saved radio profile. Confirm that the radio reports ready before removing USB. The RNode still needs battery or external power.

The USB/BLE choice is saved per station and radio. Identity, verified peers, message history and radio profiles remain in the same state directory. **USB port** can switch back after disconnecting the radio.

BLE replaces the cable between the computer and its RNode. Reticulum messages and peer services still travel over the configured LoRa interface. This does not create a Bluetooth Reticulum peer network.

The local runtime needs Bleak and its platform dependencies. macOS uses CoreBluetooth and its pairing dialog; it does not expose a Python API for submitting the passkey. Linux Classic Bluetooth serial remains a separate supported connection type. No new readiness polling or automatic reconnect loop is added.

While the protected UART exchange is pending, Pocket shows **authenticating**. Enter the current code only in the operating system prompt. Pocket cannot accept a code in the TUI on macOS: Bleak's `pair=True` is ignored there and protected characteristic access triggers system pairing. See the [Bleak macOS pairing documentation](https://bleak.readthedocs.io/en/latest/backends/macos.html#pairing).

If macOS never shows the prompt, use **Stop setup → USB port**, enter the attached serial port, and choose **Connect radio**. This selects the cable for the same owner, identity and profiles. Keep USB attached while using it. A Bluetooth failure is not a reason to erase or reflash the radio.

For the Mac D76D setup, discovery works through the actual Pocket TUI. The current macOS pairing attempt has not completed: the system received the passkey request but displayed no prompt. This is not a verified cable-free connection yet. On October 26, USB Bluetooth setup was also exercised through the registered Pocket view and real sandboxed owner at `/dev/cu.usbserial-0001`. USB is selected again; the radio session remains idle.
