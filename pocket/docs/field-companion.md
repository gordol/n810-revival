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
| Device transport | The apps consume local files. An SD card, USB file transfer or a phone share action can carry the same bytes. This version includes an offline phone capture page. Live authenticated pairing, speech models and direct watch access are future adapters. |

Larger maps, terrain and guides such as ZIM archives belong in their existing
readers. A future pack revision can reference those assets by size and digest.
A watch activity or GPX track also needs a typed asset with coordinates,
timestamps and provenance. A phone companion could use Garmin's supported
export or device APIs when available for the watch and account, then hand that
asset to Pocket. Keep device permissions, pairing credentials and model
downloads on the device that owns those services.
