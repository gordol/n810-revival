# Prepare a regional guide and carry a field log

A laptop prepares text for a region. Pocket opens the resulting file offline and
keeps observations in a private journal on the receiving device. The Field Guide
and Phrasebook share the active pack. Field Log groups observations by the
pack's stable region ID. Switching or replacing a pack preserves the journal.

## Try the example

From `pocket/` in a source checkout with Python 3.11 or newer:

```sh
python3 tools/fieldpack.py build examples/field-companion/region.json /tmp/valley.pack
python3 tools/fieldpack.py install /tmp/valley.pack
make tui
```

Open **Field Guide**, **Phrasebook** or **Field Log** from Applications.
Field Guide includes fictional shelter and food-planning cards. Phrasebook
includes an authored English/Spanish drinking-water question. Select an entry
with the arrow keys. Enter shows its detail, Tab switches panes and F filters
the list. In Field Log, press N, type an observation and press Enter to save.
Use Ctrl-], then q, to leave Pocket.

To use another device running this version of Pocket, copy the `.pack` file
using your usual file transfer. Choose **Import pack** in any of the three apps
and enter its local path. Choose **Reload** in another open view to pick up the
selection. Region IDs identify trips across devices, so keep the same ID for a
revised pack and use a different ID for an unrelated region.

## Prepare your own materials

Copy the example directory on your laptop. Edit the region ID and title, list
your cards in `region.json`, and put their UTF-8 text files in that directory.
Each card declares an ID, a kind (`guide` or `phrase`), a title, a relative
file, a source credit and terms. Phrases can contain both languages on separate
lines. For seasonal fishing or hunting rules, include the issuing agency,
jurisdiction, effective dates, and date checked. For shelters, record access
conditions. Regional foraging references should identify their author and
edition. A field observation alone cannot establish edibility.

Use your own material, authorized exports or sources permitting your intended
offline use. Personal storage, automated download, and redistribution can have
different terms. The builder reads files you supply. Keep private inputs,
prepared packs and observations in a personal directory outside the checkout.

## Exchange a phone observation

Copy `companions/field-note.html` to a phone and open it in a browser that
supports local HTML and file downloads. Enter the pack's region ID, write or
paste a note, and choose **Save observation file**. Transfer the JSON file
using your existing file-transfer method. In Pocket's Field Log choose
**Import log** and enter the local file path. Importing the same file twice
adds one observation. Date, source, entry type and original text travel together.

A phone keyboard can supply dictation when supported by the installed keyboard,
language and offline model. A translation app can supply translated text.
Choose Transcript or Translation when importing that output. Saving a file is
the persistence step on the phone. Use the original note as a separate record
when you want to keep both versions. Pocket's Phrasebook works offline using
the prepared text in the pack.

To exchange observations between two checkouts, from `pocket/` run:

```sh
python3 tools/fieldpack.py export-log sample-valley /tmp/observations.json
python3 tools/fieldpack.py import-log /tmp/observations.json
```

For a large journal, export prints a cursor. Repeat the export with a new
output file and the printed `--after-id` argument until no cursor appears.
Rerunning from the start includes observations added during a previous export.

The CLI and apps use `$XDG_STATE_HOME/current-world/field-companion`, or
`~/.local/state/current-world/field-companion` by default. The CLI accepts
`--state DIRECTORY` before the subcommand for an isolated store. Field Log
displays the most recent 100 observations for the active region.

## Integration boundaries

| Component | Contract |
| --- | --- |
| Regional content | The build manifest and the transferred MessagePack map carry `format = pocket.field-pack/1`, `id`, `region`, and `cards`. Building replaces each card's local `file` with its `body`. Activation validates the entire pack and replaces the active file atomically. Limits are 256 cards, 16,000 characters per body and one MiB per transfer. |
| Private observations | A UTF-8 JSON object carries `format = pocket.field-log/1` and a `notes` array. Each note has a UUID `id`, region ID, offset-aware ISO timestamp `time`, producer label `source`, `kind` (note, transcript or translation), and `body`. A batch imports in one SQLite transaction. Identical UUID and content are safe to retry. Conflicting content rolls back the batch. A source label identifies what the producer claimed. |
| Device transport | The apps consume local files. An SD card, USB file transfer or a phone share action can carry the same bytes. This version includes an offline phone capture page. The optional Android UV-PRO adapter below handles live Bluetooth reception. Speech models and direct watch access are future adapters. |

Larger maps, terrain and guides such as ZIM archives belong in their existing
readers. A future pack revision can reference those assets by size and digest.
A watch activity or GPX track also needs a typed asset with coordinates,
timestamps and provenance. A phone companion could use Garmin's supported
export or device APIs when available for the watch and account, then hand that
asset to Pocket. Keep device permissions, pairing credentials and model
downloads on the device that owns those services.

## Run Pocket locally in Termux

Install Termux using a supported distribution listed in the
[Termux installation guide](https://github.com/termux/termux-app#installation).
In Termux, install the prerequisites:

```sh
pkg install python make
```

Place this version of Pocket inside your Termux home directory. Android shared
storage is useful for exchanging packs and logs. Keep the working tree, SQLite
journal and session files in Termux private storage. From the directory
containing Pocket's Makefile, run:

```sh
python tools/fieldpack.py build examples/field-companion/region.json "$HOME/valley.pack"
python tools/fieldpack.py install "$HOME/valley.pack"
make termux PYTHON=python
```

This launches Pocket's terminal desktop with portable rendering and local
service discovery. Use `EXTRA=--no-local-services` for detached startup. Open Field Guide, Phrasebook and Field Log from Applications.
For a first field check, save a note, exit with Ctrl-] then q, enable airplane
mode, reopen Pocket, and read the note. The phone can also [prepare geographic maps and terrain](#prepare-maps-on-the-phone).
The launch profile has been exercised on a Linux terminal; physical Android
acceptance is pending.

### Fairphone battery and standalone UV-PRO reception

Install the Termux:API Android companion from the same distribution as Termux,
then run `pkg install termux-api`. Check `termux-battery-status` once.
Pocket's **System** window and battery tray use its charge level and status.
**Bluetooth** shows the Android controller setting when readable. Press P or
tap **Phone Bluetooth settings** to manage pairing in Android.

For direct reception, use Android 11 or later. Install the accompanying
`Pocket-UVPRO.apk` on the phone. This development APK is signed with a local
test key. The Fairphone owns the live Bluetooth Classic serial connection.
A radio paired with two devices may already have an active serial client.
Disconnect that client before selecting the radio on the phone. The existing
pairing can stay in place.

From the Pocket directory, run:

```sh
make termux PHONE_RADIO=uvpro
```

Allow **Nearby devices** when prompted. Select the paired UV-PRO in the Android
picker and switch back to Termux. Pocket's **Radio Feed** and **Stations** consume
incoming packet records. Reception uses the radio's existing settings. A quiet
channel can have an open serial connection and zero received packets.

The Android foreground service copies received serial bytes to Pocket over
loopback. Pocket chooses a new port and token for each connection, decodes KISS
and UV-PRO vendor frames, and updates the local station directory. No internet
or N810 is needed after setup. The adapter supports reception. Channel changes,
bank downloads, audio and push-to-talk require additional protocol support.

Use **Connections → Disconnect** or quit Pocket to release the radio.
The receiver notification also has a Stop action when Android displays app
notifications. After a disconnect, select **This device** to choose the radio
again. To use the N810 as the radio owner instead, install OpenSSH in Termux,
configure the existing SSH key and verified host, and use **Connections →
Connect SSH**. Choose that session without `PHONE_RADIO=uvpro` to skip the
local radio picker.

To build the APK on a laptop, install JDK 17 or 21, zip, Android SDK Platform 35
and Build Tools 35.0.0. Set `ANDROID_HOME` and run
`sh platform/android/uvpro/build.sh` from `pocket/`. The script verifies the
APK signature and keeps the development signing key outside the source tree.
Use the same private key for an in-place update of your own APK.

For MeshCore messaging, pair a MeshCore BLE companion in Android settings and
select `android-ble://paired` in the local owner's configuration. Messages can
then open a separate BLE link while Stations uses the UV-PRO. See the
[MeshCore owner setup](messaging.md).

### Fairphone 4 graphical desktop

The Fairphone 4 uses an Adreno 619. Pocket’s graphical frontend needs desktop
OpenGL 2.1. The Termux:X11 route uses Mesa Zink to run OpenGL over Vulkan and
Turnip to drive the Adreno. Install the matching Android Termux:X11 companion
from the [Termux:X11 project](https://github.com/termux/termux-x11), then
install its command and graphics build dependencies in Termux:

```sh
pkg install x11-repo
pkg install termux-x11-nightly clang make python pkg-config sdl2 mesa mesa-dev mesa-vulkan-icd-freedreno vulkan-tools
make mobile
```

Open the Termux:X11 activity to see Pocket. Run `make mobile` from the repository
root or the `pocket` directory. It reuses your display or starts Termux:X11 on
the local display (default `:1`). With the Freedreno Vulkan driver installed,
Make selects it and Zink automatically. Explicit graphics driver settings take
precedence. On the field companion branch, `make mobile-update` pulls the latest
commits and launches Pocket. To record a GPU report, run
`make mobile EXTRA="--report $HOME/pocket-gpu.json"`. After Pocket exits, check the `cell_renderer` field
in the report for the Turnip/Adreno renderer. The graphical launcher checks for
software GL unless you explicitly pass `--allow-software`. The desktop
compositor uses OpenGL; availability of individual compute effects depends on
their backend. Software GL on Linux exercises the window and rendering pipeline.
Physical Fairphone acceleration and radio reception still need device evidence.

### Phone notifications on a Garmin watch

For a first display test, enable Termux notifications in Android and allow
the corresponding application in Garmin Connect's smart notification settings.
Install the Termux:API companion from the same distribution as Termux, then
install the client with `pkg install termux-api`. Use a synthetic message:

```sh
termux-notification --id pocket-radio-test --title 'Pocket radio test' --content 'Simulated receiver disconnected'
```

If it appears on the phone first and then the watch, the notification path
works for that combination. Check notification permissions, the watch's
activity mode and Do Not Disturb if delivery differs while hiking. Live radio
alerts still need an Android notification producer fed by Pocket's radio owner.

### Send maps from the phone to a running N810

In Termux install OpenSSH with `pkg install openssh`. Configure an SSH host
alias for the tablet and check that `ssh nokia@n810` accepts your key. In
**Offline Data**, enter the local folder containing the prepared map views,
geography, hydrography and selected elevation catalogue. Enter the tablet's
hostname or SSH alias and tap **Push prepared maps to N810**. You can also run
the same transfer from the Pocket directory:

```sh
python tools/push_reference_data.py "$HOME/region" n810
```

The tablet needs the revival image's `n810-install-reference-data` tool and
space for the staged dataset plus any new or changed installed files. The
receiver checks the staged file hashes, installs under
`~nokia/.local/share/pocket` and verifies the result. Restart Pocket on the
tablet to reopen its map files. If installation reports an error, correct it
and rerun the transfer. Raw GIS downloads and field logs stay on the sender.

The Termux:X11 pixel frontend defaults to double-size desktop pixels. Select
direct touch in Termux:X11 to tap controls at their displayed positions. For a
larger landscape layout try `make termux-gui EXTRA=--ui-scale=3`.

### Building and installing the N810 system

Open **N810 Setup** with `make -C pocket setup` in a full repository checkout
on a build host. A complete kit builds the pinned ARM kernel, matching modules
and Debian root filesystem together. It requires Docker with a Linux engine and
ARM execution support. From Termux you can SSH into that host and run the
terminal setup there, for example
`ssh -t builder 'make -C ~/n810-revival/pocket setup'` if that is the build
host's checkout path. Keep the tablet attached to the machine performing USB
installation. The Pocket-only phone archive contains the map sender. Building
or flashing a fresh tablet directly from stock Termux is currently unsupported.
See the [N810 Setup guide](bootstrap.md).

### Pocket Home on Android

With Termux:X11 and the graphics dependencies installed, run `make mobile`
from the Pocket directory. Add `PHONE_RADIO=uvpro` to use the paired receiver.
Pocket Home opens fullscreen with large tiles for the map, stations, messages,
field notes and offline data. Tap **Home** to leave an app open, **Windows** to
switch between open apps, or **Apps** for the full catalogue. The grid adapts
when the display rotates. The mobile layout has its own session file and uses
the same app data as the graphical desktop. Use `make termux-gui` for the
windowed layout.

### Prepare maps on the phone

The first `make mobile` installs the Debian GIS tools through PRoot-Distro
and needs internet and local storage. Later launches check the installed tools
locally and can start offline. The builder runs on the phone’s CPU. Map,
elevation and FCC downloads start when you select them in Pocket.

1. Open **Pocket Home → Offline Data** and enter west, south, east and north
   in decimal degrees. For a small area leave the OSM URL empty. Pocket
   requests that bounding box from OpenStreetMap. Larger or densely mapped
   areas may need a matching regional PBF extract URL.
2. Keep the default local folder to use the result in Pocket. Choose **Plan**
   for the estimated elevation raster size. Choose **Download and build this
   area** and keep the app open until it reports the output folder.
3. Reopen Pocket and use **Station Map** offline. **Push prepared maps to
   N810** is optional.

The current importer requires a complete coastline crossing the selected area
and the terrain source is USGS 3DEP. For a first build, choose a small coastal
area within USGS coverage. A tested example near Newport, Oregon uses bounds
`-124.074 44.619 -124.064 44.629` and 30-metre spacing. The phone caches
source downloads, builds the map
and water layers, and derives terrain overviews locally.

### Select a download area on the world map

Open **Offline Data → Choose area on world map**. Pocket displays the bundled
Natural Earth overview. Tap **Find**, type a city name and tap a match, or
tap the map to center it and use **+** and **−** to zoom. Drag to pan.
Choose **Box** and tap two opposite corners or drag diagonally. Choose
**Use area** (**Use** on narrow displays) to fill the bounds in Offline Data,
then choose **Plan** or **Download and build this area**. **Back** discards
the selection. You can also enter coordinates directly.

The overview works offline. Regional downloads need connectivity. Selections
over 0.25 square degrees require a matching OSM extract URL. Terrain availability
depends on USGS coverage, and the current map importer requires coastline data.

On the Termux mobile shell, open **Input** on the bottom bar. Choose
**Touchscreen** to tap an item at its position or **Trackpad** to move the
cursor and click at its position. The choice updates the running Termux:X11
activity and applies to other X11 apps on that display too.

### Download Wikivoyage phrasebooks

In **Offline Data → Wikivoyage phrasebooks**, choose Spanish, French, German
or Japanese to fetch a preview from English Wikivoyage. Choose **Save for
offline use**, then open **Phrasebook** (or choose **Reload** there). Each
saved language adds sections to the phrase list alongside your regional pack.
Downloading the same language again replaces its saved edition when you save.
The cards include the source revision, contributor credit and CC BY-SA terms.

To carry a language to the N810, copy its
`~/.local/state/current-world/field-companion/phrasebooks/wikivoyage-*.pack`
file and use **Phrasebook → Import pack** on the tablet. The default state
directory follows `XDG_STATE_HOME` when set.

### Rainier walk and Wildlife

Open **Apps → Rainier walk** in the Android OpenGL shell to play on the
Ohanapecosh River. Tap dry ground to walk to the little gold ring. To follow
the berry trail, tap **Berries** or the round compass in the scene. When you arrive, a berry turns blue in the counter and the
bush loses its fruit. From the starting clearing the four stops trace roughly
140 metres through the woods on the same riverbank. Tap the compass again to find the next bush. After three, tap to
bring the berries to the story fox. A heart means the fox has eaten. Tap
again to play another round. Each feeding adds a heart for this session.
Drag the view to look around. While walking to a waypoint or following the
berry guide, your steps carry on as you look to either side.
A new tap on the ground sets the next destination. Tap **Walk** for continuous walking while you look,
and **Stop** to stand still. In Tap to walk mode, looking around keeps your
walking heading. Stop, face a new direction and tap Walk to head that way. You can also look around on a guided walk.
Tap **Map** below **Guidebook** for a north-up map centered on your position.
The gold marker points in the direction you face. **Valley** shows the whole river
reach and both mapped hiking trails. Tap a spot, then **Zoom in** to inspect it
or **Walk here** to set a direct walking waypoint. **Back** closes the map.
The valley map works offline.

Choose **Hike → Paradise meadows** on a solo walk to visit the subalpine
flower fields above Paradise. The first regional visit needs the Rainier elevation
download. In summer, look for violet broadleaf lupine, magenta paintbrush
and white avalanche lilies. Approach a patch to add the flower to **Guidebook**.
The spring setting shows the snowmelt lilies. The flower patches are illustrative,
and their bloom follows the game's seasons. [Mount Rainier wildflowers](https://www.nps.gov/mora/learn/nature/wildflowers.htm)

The regional summit uses a bundled USGS 3DEP elevation inset with roughly
34 × 38 metre sample spacing. Walking and rendering use the same surface.
Across the meadows, distant slopes carry simpler conifer crowns out to roughly
2.4 km. Tree locations and shrub patches are illustrative.

Choose **Hike → Fish at trout pool** for a bank-side view of several rainbow trout.
Tap **Cast fly**. The fly drifts downstream, and some drifts pass without a bite.
Tap **Lift rod!** at a rise. Tap **Reel** once to wind continuously. Tap **Ease line** when the fish runs,
then **Reel** when it rests. Landing a trout adds its species to the guidebook. High tension can break the line, and prolonged slack can lose the fish.
Release native rainbow trout. A landed brook trout also offers **Keep brook**.
The park permits brook trout retention in open streams without a minimum size.
Google Play Termux includes vibration support. For F-Droid Termux, install
the Termux:API companion app from F-Droid. `make mobile` installs the `termux-api` command package when
`termux-vibrate` is missing. Run `termux-vibrate -d 300` to feel a test
pulse. Fishing pulses at a bite, during runs and on landing. Set `POCKET_HAPTICS=0` to disable pulses.
For an optional motion hook-set, check that `termux-sensor -l` lists an
accelerometer, then launch with `POCKET_MOTION_ROD=1 make mobile`. At a bite,
tilt the phone about 30 degrees from its starting angle and hold briefly.
The game samples for about 1.5 seconds. **Lift rod!** also works throughout.
Look down to see fish and
stones through the water, or look along the river to see sky and conifer reflections.
The pool and its fish are illustrative.

Choose **Hot Springs Trail** or **Silver Falls Loop Trail** in **Hike** to arrive on
the dirt path facing along it. The game includes the portions inside the valley
terrain. Ferns line the path, and flocks of small birds have homes along it.
[National Park Service public trail geometry](https://mapservices.nps.gov/arcgis/rest/services/NationalDatasets/NPS_Public_Trails/FeatureServer/0)

Choose **Hike → Gather camp supplies** for the campsite activity. Follow the
distance and direction to loose stones, sticks and a fallen log. Tap **Gather**
beside each one, then return to the clearing and tap **Build camp** for a tent,
stone ring and log seat. These supplies and fishing actions are local to the walk.

The river is audible through the woods and grows louder as you approach the bank. Each berry has its own chime. Listen for occasional caws, hoots, whistles and chips from nearby wildlife. The game synthesizes these calls and fades them with distance. Tap
**Mute** for quiet play. There is
no countdown. The fox is a game character. At Mount Rainier, watch wild
animals from a distance and leave them their natural food.

Tap **Hike → Pace** to cycle between Walk (1×), Brisk (2×) and Explore (8×).
The pace affects manual movement, continuous walking and ground waypoints.
The guided berry stops keep their usual pace.

For a mountain hike, tap **Hike → Download Rainier & hike**. Pocket fetches
the regional USGS elevation grid once. On later visits choose **Open summit
approach**. Start about 2.2 km south of the highest sampled point and head
north uphill. On first regional travel Pocket requests a finer USGS 3DEP
export for the 470 × 917 m approach and caches it for offline visits.
Its sample spacing is 2.8 × 3.2 m. At the reported viewpoint USGS identifies
the Mount Rainier 2008 NED 1/9-arc-second survey (published in 2010).
Walking and rendering use the same triangles, including shallow illustrative
wind ridges. Small rock fragments are illustrative. If acquisition fails,
the existing summit terrain remains walkable. The whole grid is walkable, about 52 km east–west by 59 km
north–south, with elevation samples roughly 200–230 m apart. The altitude
in the footer follows the ground underfoot. **Map** opens a north-up relief
map. Tap a spot to start walking there, or tap **Back** to stay put.
**Hike → Return to Ohanapecosh** restores your previous valley position.
Wildlife encounters and shared family rooms are in the detailed valley.
On the regional map, nearby terrain grows deterministic conifer stands below
the treeline and grass clumps in open areas. Steep rock and the high summit
stay bare. This vegetation illustrates elevation and slope on the USGS grid.
In Ohanapecosh, saplings grow beneath a 25–54 m canopy, with occasional
older conifers reaching about 77 m. Fern colonies and woody shrubs grow at
walking height. Around Paradise, tree height falls toward timberline.
Nearby trees cast longer shadows in low sun. Shadows change direction during
the 12-minute light cycle, soften in mist and showers, and fade at night.
The regional terrain represents mountain shape; it does not show climbing routes.

The game includes a roughly 2 km square of USGS 3DEP elevations sampled at
8 m and four USGS National Hydrography Dataset flowlines. The water surface
is level from bank to bank and descends along the joined flowlines. Ripples
travel downstream through bends. The channel depth, water level and width,
individual trees, blueberries and wildlife encounters are illustrative. Look
across the river for a black bear or along the shallows for a jumping rainbow
trout. The site data travels with Pocket and works offline. The cell-based
walk still uses its original separately downloaded summit-area grid.
[USGS sources and reach identifiers](../graphics/assets/ohanapecosh/site.json) ·
[National Park Service guide to Ohanapecosh](https://www.nps.gov/mora/planyourvisit/ohanapecosh.htm) ·
[Mount Rainier fish](https://www.nps.gov/mora/learn/nature/fish.htm)

In the Android graphical shell, **Apps → Wildlife** opens an animated hoary
marmot. Tap **Animal** for the next animal or **Group** to jump to birds, fish,
reptiles and amphibians, invertebrates, or mammals. **Turn**, **Zoom**, and
**Pause** let you inspect a field mark. The offline catalog includes barred
owls, American crows, newts, swallowtails and trout. Regional studies share
body shapes across related species, with different size, coloration and marks.
Encounter locations are game placements and imply no recorded sighting.

Watch for rings spreading over the trout. Head upstream on the starting bank:
a dipper bobs on a broad rock and paw prints lead toward the otter pool.
Tap the large **Camera** button, aim the crosshair at an animal, then press
**Take photo**. You can also tap an animal directly. **Put away** closes the
camera. Open **Guidebook** from the trail to leaf through your finds or open
the **Album**. The river valley shows through the paper. Tap either side of
a photo to turn the page, or tap **Book** to return to its guidebook page. Portraits are
also saved locally as PNGs in
`${XDG_DATA_HOME:-$HOME/.local/share}/pocket/rainier-walk/photos/`. Each
player keeps their own photos in a family room.

The optional riverbank questions are available with the **?** key.
The regional rules in those cards were checked November 24, 2026. For a trip, check the current park rules or the
Washington rules and emergency updates for the specific water.

- [Mount Rainier fishing and boating](https://www.nps.gov/mora/planyourvisit/fishing-and-boating.htm)
- [Washington fishing rules and emergency updates](https://wdfw.wa.gov/fishing/regulations)
- [Washington fish identification definitions](https://app.leg.wa.gov/wac/default.aspx?cite=220-300-160)
- [Field investigation of Slippery Falls and Ohanapecosh fish passage, sections 2.5 and 4.2](https://www.morageology.com/pubs/356.pdf)
- [CDC guidance on Giardia and drinking water](https://www.cdc.gov/giardia/prevention/index.html)

Rainier Walk prepares the valley on the first visit and saves the generated
terrain, plants and wildlife meshes under `$XDG_CACHE_HOME/pocket/rainier-walk`
(default `~/.cache/pocket/rainier-walk`). Later visits reuse the scene. Each
graphics detail level has its own cache, refreshed when its inputs change.

Rainier Walk selects graphics detail automatically. High detail adds denser
berry clusters and nearby wildlife meshes, bark and ground texture, nearby
animal shadows, and a soft glow around bright highlights. Auto starts with a
smaller mesh on devices reporting less than 3 GiB of RAM. On a sustained
slowdown it drops bloom, fine shading and extra foliage for the session.
The elevation grid, berry hunt, wildlife encounters and touch controls work
in both modes. To choose a mode when launching Pocket from the checkout:

```sh
POCKET_RIVER_QUALITY=high make mobile
```

Use `low` for the lighter build, or run `make mobile` with no override for auto.

### Family walk

Up to eight graphical Pocket players can share the blueberry hunt on a trusted
Wi-Fi network. Open **Rainier walk → Family** on each device.

1. On one device, tap **Host on this Wi-Fi**. Read the four-digit room code.
2. On the others, tap **Join with a code** and enter those four digits.
3. When the room shows everyone, tap **Walk together**. Orange pennants mark
   the other walkers. Each player can steer or tap to follow a berry.
4. The room shares one basket and one heart per feeding. Anyone can start
   another round. **Family → Leave room** returns to your solo basket.

Keep the host in Rainier Walk while playing. Hosting opens UDP port 43817.
Broadcast discovery needs a network that allows devices to talk to each
other. To join through an existing private VPN, or when broadcast is
unavailable, launch the joining device with the host's reachable IPv4 address:

```sh
POCKET_RIVER_HOST=192.168.1.24 make mobile
```

Replace the example with the host's LAN or VPN address, then enter its room
code. A VPN server can route the connection between devices. The host still
runs the game. The room protocol is unencrypted and designed for trusted
networks. Keep the UDP port private.


In **Settings → App: Rainier walk → Touch controls**, choose **Tap to walk**
(the default) or **Two thumbs**. With Two thumbs, drag on the left to walk or
sidestep and on the right to look around. Pocket saves this choice locally. On a computer use W/A/S/D and the arrow keys. Tap Camera
and photograph an animal, or walk within a few steps of a blueberry shrub,
conifer or forest fern. Open **Guidebook** for the discoveries saved
on this device. The photo album keeps repeat shots, too. Ferns appear at high
detail. Android uses Termux:X11's **Direct touch** mode for independent fingers.

Tap **Binoculars** for a 4× view. In the valley, **Berry view** takes you
to a bluff across the river and aims at an unpicked blueberry patch at 8×.
Tap it again to scan the remaining patches and the fox. Spotting leaves the
berries on the bushes until a player walks up to them. Pinch with two fingers or tap **Zoom** to
change magnification from 1× to 8×. With **Camera** open, keep an animal near
the middle until its name appears, then tap **Take photo**. Focus follows it
a little way off center. Swipe left or right to turn guidebook or album pages.

In **Hike → Camp & sky**, visit the river overlook to see the Ohanapecosh
channel and its rocky shallows from above. Pitch a tent in the starting
clearing or turn on the optional Bigfoot camp story. Camp choices apply on
this device. Tap **Light** for day, dusk, night, or a 12-minute cycle, and
**Weather** for clear skies, mist, or showers. Clouds drift past the stars
at night. On clear spring and summer days, watch the trout pool for a hatch. Snow cover changes by season. River discharge and snowmelt are
not simulated. To visit the fire tower, choose **Visit Mt Fremont lookout** on the same
menu while exploring solo. Pocket opens the regional elevation map, downloading
it on the first visit. At the tower, tap **Up to deck** for the view toward
Rainier, **Binoculars** for a closer look, or **Step down** to explore on foot.
**Hike → Return to Ohanapecosh** returns to the valley. The model approximates
the two-story lookout and wraparound balcony at the NPS site coordinates.
[National Park Service lookout history](https://www.nps.gov/places/mount-fremont-fire-lookout.htm)
and [site location](https://parkplanning.nps.gov/showFile.cfm?projectID=95553&sfid=478470).

**Summit ski loop.** From the regional Hike menu choose **Put on skis** after
the regional terrain opens. Tap **Course** (keyboard **C**) before gliding
or at the finish to choose a distance. The 150 m practice loop uses the
close-up summit patch. The 1.2 km and 2.6 km descents use the broader summit
terrain and have three and six snow ramps respectively. Cross a blue lip to
launch automatically, or carve around it. Braking in the air takes effect
on landing. At the long-course finish, **Ride again** restarts that course.
Tap **Glide** and drag sideways to carve
between the orange flags. **Brake** stops the skis until you tap Glide again.
Assist caps speed at 8 m/s. Turn it off for a faster line. The green flags
mark the runout. On the practice loop choose **Climb back**, then tap alternating grips to traverse
uphill to the start. **Reset** returns to the top and **Walk** removes the skis.
On a keyboard, left/right set the carve, up straightens, space operates the
brake or next grip, and R resets. On Termux installations with a working
accelerometer, launch with `POCKET_SKI_TILT=1 make mobile` and hold the phone
upright and level when putting on skis. The course and ice grips are fictional.
