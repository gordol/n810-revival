# Local map data

Choose an area before acquisition. From `pocket/`, use `make maps-configure`,
`make maps-plan`, then `make maps`. Install build dependencies once with
`make maps-deps`. See the map-data guide under `pocket/docs/` for runnable examples.

One fine elevation catalogue supplies local display overviews and fine analysis.
`make maps-terrain` is offline derivation; it does not download a coarse DEM.
Generated maps share `data/maps/`; new builds do not create legacy local crops,
terminal terrain copies, or Map Library mirrors. Downloads and outputs stay out of Git.

GUI and terminal readers use this data root for maps, elevation grids and
terrain references. Set `POCKET_DATA_ROOT` to an absolute directory to select
a different dataset. Elevation grids belong directly under the root; map
packs belong under `maps/`.
