# Build offline maps for an area

Run these commands from `pocket/` after cloning the repository in your build-host Python environment. Python,
Make and the map build dependencies are required; Nokia's readers do not need
GDAL, osmium or Shapely.

```sh
make maps-deps
make maps-configure MAP_BBOX="-124.8 46.3 -120.6 48.7" \
  MAP_SOURCE=data/downloads/washington.osm.pbf \
  MAP_URL=https://download.geofabrik.de/north-america/us/washington-latest.osm.pbf
make maps-plan
make maps
```

The example selects western Washington. Supply your own west/south/east/north
bounds and matching OSM extract or URL for another area. Selection is saved in
`data/map-area.json`; no region is selected implicitly. Configuration and planning
make no network requests. Planning reports reusable fine packs, cached raw exports,
new export count and estimated uncompressed raster bytes. Actual transfers and
storage depend on compression, coverage and missing data.

`make maps` reuses the OSM input, builds geography only when its inputs/builders
change, and acquires missing fine elevation. Dependency installation is separate.
`MAP_SPACING=15` is the default requested elevation sample spacing in metres;
choose a smaller value for more samples. Export spacing is not a claim about the
underlying USGS DEM's native resolution.

## One elevation source, local display levels

Fine exports are kept under `data/downloads/usgs/`. Each is prepared once into
compressed metre-valued height tiles under `data/elevation-fine/`. Progress is
retained per export, so a later run reuses complete fine packs or raw exports,
including an existing larger export covering a smaller requested area. Only
uncovered areas need another export. No separate coarse DEM is downloaded.

Display overviews are derived locally by reducing the fine height grid. Missing
samples remain unknown. `data/elevation.json` selects the active packs; unselected
cached areas are reusable but excluded from reference-data transfers. Terminal
rendering selects an appropriate overview and quantizes display colours. Desktop
rendering samples the same height catalogue at display resolution. LOS and
profiles keep the fine samples; display averages never establish clearance.

The original F32 GeoTIFF is retained for GIS use. Runtime height tiles round to
one metre vertically. The graphical reader uses those heights, rather than a
terminal colour raster; direct GeoTIFF/COG reading through GDAL is not required
by this pipeline.

New geography and terminal views share `data/maps/`. Builds do not make a
Lakewood crop, `terrain-next.n8t`, or a generated Map Library resource mirror.
Legacy readers/assets remain compatibility inputs for existing installations.
The OSM importer still requires complete coastline topology for its selected
coverage; arbitrary inland/ocean-only extracts need a separate land-mask source.

## Reuse and verification

```sh
make maps-terrain                 # Offline: derive/reuse existing elevation only
python3 tools/audit_regional_elevation.py --data data
python3 -m unittest discover -s tests -p test_elevation_pipeline.py
python3 -m unittest discover -s tests -p test_map_build_pipeline.py
```

The first test suite uses small fictional height grids and mocked transfers. The
second runs the real OSM importer and renderer on fictional geometry when the
map build dependencies are installed. Neither downloads a region. The integrity
audit checks selected fine/overview tile lengths and hashes without expecting a
fixed number of packs. Generated data and caches stay out of Git.
