# Restoring detail and steady movement in the Pocket map

*9 November 2026.*

The Station Map exposed two different defects on the Mac desktop. Terrain and water appeared in large blocks even though the display had enough pixels for finer detail. During a drag, an old image could move beneath a newly requested view, leaving a seam or a jump when the replacement arrived. The terminal map had a separate readability problem: dense road glyphs obscured regional views. These were presentation and navigation faults, not evidence that the underlying regional packs had lost their detail.

## Keep map data separate from terminal cells

The earlier desktop path treated a terminal cell as the source of both terrain color and map text. Enlarging that cell also enlarged its water edge and road mark. The revised shared map surface carries terrain samples, geographic line segments, and annotations separately. The Mac renderer samples terrain at pixel density and draws roads and streams as lines in an accelerated scene. The terminal keeps its cell renderer and limits minor road strokes at wide scales. The [map rendering reference](../pocket/map-rendering.md) records the navigation and sidebar regression checklist.

A complete map scene remains visible while its replacement is prepared. The Mac renderer retains terrain and line textures across changes to the zoom box and other annotations. A drag uses a surrounding terrain plane at the requested camera, so the exposed edge belongs to the destination geography. The sidebar locator samples its own camera from the same map sources. Zoom preview and Overview expand their context when the target box leaves the visible area.

## Make labels and local identity stable

The first attempt to keep labels visible during a drag left bitmap letters in the map texture while macOS drew its smooth text over them. The doubled letters looked heavier than the desktop text outside the map. The stationary Mac map now uses one smooth text pass; moving labels use the map glyphs until the drag ends. Label placement limits collisions, and label backgrounds and letters enter the completed scene together.

The same work removed an invented APRS self identity. Pocket asks for a callsign when none is configured and stores it beside the selected local Directory database in a private settings file. The GUI and terminal readers resolve the same data root. No personal database or settings file is part of this source checkpoint.

## Checks and remaining boundary

The full Pocket host suite passed **808 tests, with 30 skipped**. The regional coastline integration tests passed when run against the local regional data; the full-suite loader uses fictional map fixtures, so those tests now check their data prerequisite at execution time. The native graphics check passed on the Mac Metal path, including eight drag frames and eight surrounding-plane frames with no ordinary map readbacks. A hidden Mac window exercised smooth text for 30 frames. These are host results. Map latency, memory, and visual acceptance on a physical N810 remain to be measured before using the laptop's detail density as a device claim.

[Build and test instructions](../how-to/validate.md) describe the host and device checks.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [Retained native map scene](../assets/source/journal/pocket/graphics/gpu_scene.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/gpu_scene.py))<br>[GPU map rasterizer](../assets/source/journal/pocket/graphics/native/gpu_scene.c.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/native/gpu_scene.c))<br>[Semantic map surface](../assets/source/journal/pocket/graphics/map_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/map_pixels.py))<br>[Geographic lines and labels](../assets/source/journal/pocket/shell/map_geography.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/map_geography.py))<br>[Local station identity](../assets/source/journal/pocket/shell/directory_preferences.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/directory_preferences.py)) |
| Checks and fixtures | [Pixel handoff and interactions](../assets/source/journal/pocket/tests/test_map_pixel_handoff.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_pixel_handoff.py))<br>[Terrain density checks](../assets/source/journal/pocket/tests/test_gpu_map_terrain_detail.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_gpu_map_terrain_detail.py))<br>[Local identity checks](../assets/source/journal/pocket/tests/test_directory_preferences.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_directory_preferences.py))<br>[Native map check](../assets/source/journal/pocket/graphics/check_map.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/check_map.py)) |
| Build inputs | [Native graphics build](../assets/source/journal/pocket/graphics/build.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/build.py))<br>[Pocket build targets](../assets/source/journal/pocket/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/Makefile)) |

[Build and test instructions](../how-to/validate.md) · [Chronological source index](../reference/journal-sources.md#2026-11-09-pocket-map-rendering)

Host Mac and test-fixture results are recorded here. Physical N810 map performance and visual acceptance remain separate checks.
<!-- journal-sources:end -->
