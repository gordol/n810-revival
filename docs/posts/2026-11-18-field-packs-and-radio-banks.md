# Taking Pocket maps and radio banks into the field

18 November 2026

For a road trip, I wanted to open a map, pick a nearby repeater and tune the handheld. I also wanted the roads, terrain and radio frequencies on the laptop before leaving home. Pocket now brings those together in a field pack. I can pan along the route offline, look at the terrain around a repeater and select it on Station Map to tune the B side of a paired UV-PRO.

Radio Manager handles the other half of the trip. The Field tab holds the groups I prepared in advance. I picked a group of eight GMRS repeater outputs and loaded it into an empty bank for receive-only scanning. From the same window I could download all six banks, browse their channels in Memories and give the new group a name I would recognize on the handheld. After the download, the radio was back on the group I had been using.

The pack follows the trip. The hardware connection follows the device I choose in Pocket. On the laptop I can use the UV-PRO directly over Bluetooth. Selecting an N810 over SSH gives Pocket access to the tablet’s own services. The same pack can also hold a shortwave schedule for a receiver or receive and transmit frequencies for a transceiver such as an X6100. Those lists are available for manual tuning; direct radio control is implemented for the UV-PRO.

For another trip, I can choose a different region, terrain detail and set of radios. The [field-pack guide](../pocket/field-packs.md) includes a prompt anyone can adapt to build their own.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [Field-pack frequency lists](../assets/source/journal/pocket/shell/field_banks.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/field_banks.py))<br>[Mac radio control](../assets/source/journal/pocket/shell/mac_uvpro.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/mac_uvpro.py)) |
| Checks and fixtures | [Radio reference lists](../assets/source/journal/pocket/tests/test_field_pack_radios.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_field_pack_radios.py)) |
| Build inputs | [Mac Bluetooth adapter](../assets/source/journal/pocket/bluetooth-macos/uvpro.m.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/bluetooth-macos/uvpro.m)) |

[Build and test instructions](../pocket/field-packs.md) · [Chronological source index](../reference/journal-sources.md#2026-11-18-field-packs-and-radio-banks)
<!-- journal-sources:end -->

[Journal](../journal.md)
