# Map navigation and retained regions

Ordinary dragging moves the map. Zoom preview changes a target box; Enter accepts
it and Escape cancels it. Explicit Overview keeps its camera fixed while the box
is adjusted. Moving a preview beyond the loaded image scrolls its context at the
same scale instead of returning to the regional overview.

`map_regions.py` owns a cache of at most two geographic regions, with a combined
240,000-cell budget. Its cache key includes display spacing and layer/source
identity. A pan at the same spacing reprojects overlapping cells and prepares
only exposed edge strips. Each strip includes two extra cells for slope and line
calculations; those extra samples are discarded when copying the strip. A new
scale, changed layer identity, or view without overlap requires fresh rendering.
Context views use their requested dimensions; detail views may retain padding
for subsequent pans. The old image remains available during background work.

Geometry helpers are ordinary functions. The cache is stateful because it owns
retained images and their bounded lifetime. The existing single rendering worker
does the preparation; input handling does not wait for it. Repeated interim pans
flatten their sampling maps instead of retaining recursive image chains.

`region_status()` exposes retained, reused, and prepared cell counts for checks.
`tests/test_map_incremental_regions.py` checks overlap preservation, exposed-strip
work, layer/scale invalidation, and north/south panning at a 953 km span.
`tests/test_map_interaction_regressions.py` checks input through the outer app
wrapper as well as the underlying map. These tests do not establish live display
quality on either the laptop terminal or Nokia.

# Map data preparation

Use the [area-selected build workflow](map-data.md). One fine elevation catalogue
feeds desktop, terminal, profile and LOS readers. Display overviews are derived
locally; analysis retains fine samples. Generated maps share `data/maps/`.

`make maps-plan` reports cache reuse and remaining exports without downloading.
`make maps-terrain` derives display levels offline. Legacy coarse/local packs stay
readable for compatibility, but new builds do not generate them or mirror data
into Map Library resources. Area selection is currently through the CLI and
saved configuration; the integrated area/layer download pane remains unfinished.
