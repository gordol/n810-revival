# Local offline map packs

Run `make maps-download` and `make maps` from `pocket/` to populate this directory.
The build produces `puget-sound.json.gz`, its source metadata and the road overlay,
and copies them to the Map Library resource directory. The pack records the
selected geographic bounds, source hash and OpenStreetMap attribution.

The application reads these files offline. Optional fine terrain is prepared by
`make maps-elevation`. Inputs and generated packs are ignored by Git and excluded
from the source release. Build instructions are in `docs/how-to/build-map-data.md`
at the repository root.
