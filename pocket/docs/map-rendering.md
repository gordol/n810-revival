# Map navigation and retained regions

Ordinary dragging moves the map. Zoom preview changes a target box; Enter accepts
it and Escape cancels it. Explicit Overview keeps its camera fixed while the
target box fits. When zooming out or moving the box beyond that view, the
overview camera expands to keep the box visible. Moving a normal preview beyond
the loaded image scrolls its context at the same scale instead of returning to
the regional overview.

`map_regions.py` owns a cache of at most two geographic regions, with a combined
240,000-cell budget. Its cache key includes display spacing and layer/source
identity. A pan at the same spacing reprojects overlapping cells and prepares
only exposed edge strips. Each strip includes two extra cells for slope and line
calculations; those extra samples are discarded when copying the strip. A new
scale, changed layer identity, or view without overlap requires fresh rendering.
Context views use their requested dimensions; detail views may retain padding
for subsequent pans, with one eighth of the visible dimensions on each edge
(about 1.56 times the visible area). The old image remains available during
background work. Across scale changes it samples the terrain's two half-cell
colours separately; it never stretches road or station glyphs into repeated
stripes. Station annotations and hit targets are projected at the displayed size.

The desktop DEM sampler gathers only unresolved land pixels after selecting a
display overview. Covered pixels and known water do not trigger fine tile reads.
The packed colour lookup preserves the renderer's existing RGB565 quantization.

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

## Station Map regression checklist

- Main GUI map: terrain remains semantic pixels through pan, preview, confirm,
  resize and Overview; roads and labels remain geographic overlays. A zoom
  before the first map image arrives must still start the map request.
- Box-only redraw: reuse the stable terrain and geographic-line texture; change
  only the transparent annotation texture. Keep window margins clear at odd
  physical sizes so old map pixels cannot appear above or below the UI.
- Sidebar locator: use the same terrain and vector source as the main map at its
  own camera, with dense desktop pixel sampling and a geographic target outline.
  Opening the sidebar must not replace the detailed locator with enlarged cells.
- Overview zoom out: keep the target box visible by expanding the camera when it
  reaches an edge, including when the regional preview asset is absent.
- TUI: keep its cell renderer and check readability at local and regional zoom.
- N810: measure map latency and memory on the physical device before claiming
  the desktop detail density is suitable there.

Run `python3 -m unittest discover -s tests -p test_map_interaction_regressions.py`,
`python3 -m unittest discover -s tests -p test_map_pixel_handoff.py`, and
`python3 graphics/check_map.py` for the interaction and native Metal checks.
The native check uses the generated fictional map fixture and requires a
working desktop graphics environment. It asserts a pixel locator, dense terrain,
scene rebuilds and zero map readbacks.

# Map data preparation

Use the [area-selected build workflow](map-data.md). One fine elevation catalogue
feeds desktop, terminal, profile and LOS readers. Display overviews are derived
locally; analysis retains fine samples. Generated maps share `data/maps/`.

`make maps-plan` reports cache reuse and remaining exports without downloading.
`make maps-terrain` derives display levels offline. Legacy coarse/local packs stay
readable for compatibility, but new builds do not generate them or mirror data
into Map Library resources. Area selection is currently through the CLI and
saved configuration; the integrated area/layer download pane remains unfinished.

## Terrain applications

Station Map owns terrain profiles, antenna obstruction and LOS radius tools;
there is no separate Terrain Profile launcher. The profile implementation remains
shared by those tools.

Rainier walk is the ground-level 3D exploration demo. Press O there to open
Scenery's Viewpoints section, with the original, wide, elevated and valley camera
compositions. These are independent overview cameras; returning to Rainier walk
preserves its walking position. Scenery also retains its camera adjustments and
saved scene library. APRS Walk Logs is the separate read-only field-test log
viewer, previously titled Walk.
