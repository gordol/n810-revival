# Make a personal Pocket field pack

A field pack is a local directory you choose. The same checkout can open different packs by changing two environment variables. Keep generated data outside the checkout so a pack can grow, be replaced, or travel with you independently of the application.

| Path inside your pack | Contents |
|---|---|
| `pocket/` | Pocket data root for offline geography, hydrography, and elevation. |
| `pocket/repeaters/repeaters.json` | Station Map directory. Include the source, edition, repeater records and coordinate accuracy. |
| `uv-pro/*.csv` | One BTECH channel group per file. Pocket validates the supported channel fields when loading the Field tab. |
| `radios/<radio>/frequencies.csv` | Model-specific reference lists with `station`, `hz`, `mode`, and `source`. Optional `bank` and `utc` columns group entries and display schedules. Optional `tx_hz` records the transmit frequency for a transceiver. |

### Prompt to copy into your agent

> Build a personal offline Pocket pack for **[places or route]**. Save it in **[local folder outside Git]**. My devices are **[laptop, handheld, radio models, available control interfaces]**. I want **[map detail, terrain, radio services or listening interests]** and my storage budget is **[size]**.
>
> Check the existing pack and reuse its downloads. Show me the bounding box, proposed coverage, elevation spacing, source dates, and estimated disk usage before a large download. Use the repository’s map builder with an explicit output directory. Check source coverage and offline-use permissions. Record attribution and source URLs alongside the data. Mark approximate repeater positions and keep unknown fields explicit.
>
> For each radio, ask whether I want listening references, operating frequencies, programmable memories, or rig control. Check what Pocket supports for that model and interface. Build the requested groups. Record repeater inputs, outputs and tones from the source. Set monitoring channels to receive-only and check that the radio encoder preserves that setting. For scheduled broadcasts include UTC windows and validity dates where available. Keep radio programming as a separate step that I can request.
>
> Open this pack in Pocket. Check representative route stops offline at street and regional zoom, check terrain coverage, and browse the requested banks in Radio Manager. Report actual pack size, coverage gaps, and which checks ran on hardware. Keep generated files, private radio backups, credentials and personal locations local.

### Choose the layers

- **Street maps** — Start with the towns or route you expect to visit. Choose a bounding box with room for detours and an OSM extract that covers it. Record extract date, license and attribution in the pack.
- **Terrain** — Select elevation coverage and sample spacing independently of map zoom. Run the storage plan before downloading. Inspect a known hill and a route-edge point after building. Missing elevation should display as unknown.
- **Repeaters** — Choose the services you want, such as amateur FM or GMRS. Prefer operator or coordinator records with permission for offline use. Keep source links, access restrictions, position accuracy, and tone direction with each entry. A listing without a position can still be a bank entry.
- **Radio banks** — Start with a CSV export from the target radio application so field names and units match. Group by region or purpose. Airband AM, weather FM, GMRS scan, and amateur repeaters have different mode, tone and transmit settings. Check each proposed group against the loader and channel encoder. For a transceiver such as an X6100, use `radios/X6100/frequencies.csv` for manual tuning references. Put the receive or dial frequency in `hz` and any known transmit frequency in `tx_hz`, both in integer hertz. A receiver-only list can omit `tx_hz`. These CSVs are browseable on the Field tab. Automatic tuning and upload require a model-specific control adapter; the hardware adapter included here is for the UV-PRO.
- **Other references** — Include the local operating notes, network profiles, manuals or frequency schedules you need. Keep a small source list with retrieval dates and refresh instructions. A different region may use different network settings.

### Build and open

Run from `pocket/` in the checkout. Set `POCKET_FIELD_PACK` to the absolute path of your chosen folder and `POCKET_DATA_ROOT` to its `pocket` subdirectory. The map CLI takes `--output` explicitly for each action. For example, after choosing a local OSM extract and bounds:

```sh
export POCKET_FIELD_PACK="$HOME/Pocket/packs/my-region"
export POCKET_DATA_ROOT="$POCKET_FIELD_PACK/pocket"
python3 tools/maps.py configure --output "$POCKET_DATA_ROOT" \
  --source "$OSM_PBF" --bbox "$WEST" "$SOUTH" "$EAST" "$NORTH"
python3 tools/maps.py plan --output "$POCKET_DATA_ROOT" --spacing-m 30
```

Once you accept the estimate, build the selected layers and audit the terrain:

```sh
python3 tools/maps.py build --output "$POCKET_DATA_ROOT"
python3 tools/maps.py elevation --output "$POCKET_DATA_ROOT" --spacing-m 30
python3 tools/audit_regional_elevation.py --data "$POCKET_DATA_ROOT"
```

Use the spacing you selected during planning. The geography importer needs a suitable land mask in inland regions. Check this before assuming an arbitrary extract will build. The map guide covers prerequisites, data sources and integrity checks. [Offline map build guide](map-data.md)

For Pixel Pocket on macOS, build the Bluetooth helper with the Apple compiler and frameworks, then launch the GUI:

```sh
make mac-radio
POCKET_OPEN_FIELD=1 make gui
```

Open **Radio Manager → Field** to browse pack groups. **Banks** and **Memories** display downloads from the selected radio. A hardware backup contains the operator’s channel configuration and belongs with their private app state.
