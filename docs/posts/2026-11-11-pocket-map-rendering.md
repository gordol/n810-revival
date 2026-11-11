# Restoring map detail in the native GPU desktop

11 November 2026

The Station Map rendering changes were reconciled with the current native GPU pipeline at `ca60eb0`. The earlier map branch predates that pipeline. Its missing behavior was ported through the current shared map surface and native scene interfaces.

Semantic maps select local streets at pixel scale, sample terrain more densely within a fixed work budget, and place complete geographic labels around station and path annotations. Forest roads can be toggled without discarding the retained terrain scene. During a drag, the native renderer moves the sharp retained view over a surrounding map; release requests the destination view. The sidebar locator is a separate semantic scene, with a geographic target outline. Overview navigation expands its context when the target leaves the current camera.

Station identity is read from local configuration beside the Directory database, with legacy preference fallback. Saved QTH labels use that configured identity. Identity files, downloaded map data, terrain packs, and caches remain local inputs.

## Host verification

The Mac native graphics check exercised the actual desktop, map drag, surrounding scene, locator inset, resizing, and 25 applications using Metal. The map harness reported zero diagnostic GPU readbacks. Source-only regression fixtures cover map detail, forest-road selection, labels, navigation, and local identity storage. The desktop smoke checks also passed.

The isolated Pocket suite runs each test module with private local state. Strict documentation and publication input checks passed. The all-object history audit found three pre-existing blobs in main containing operator home paths in historical MBX build scripts; this port does not rewrite those commits. These checks establish host behavior and publication validation. No N810 installation, device rendering check, or physical LCD acceptance was performed for this port.

<!-- journal-sources:start -->
## Code, tests and build inputs

| Material | Repository files |
|---|---|
| Implementation | [Native map scenes](../assets/source/journal/pocket/graphics/map_pixels.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/map_pixels.py))<br>[Shared map navigation](../assets/source/journal/pocket/shell/map_navigation.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/map_navigation.py))<br>[Local station identity](../assets/source/journal/pocket/shell/directory_preferences.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/shell/directory_preferences.py)) |
| Checks and fixtures | [Native map desktop check](../assets/source/journal/pocket/graphics/check_map.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/graphics/check_map.py))<br>[Map regression checks](../assets/source/journal/pocket/tests/test_map_interaction_regressions.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_interaction_regressions.py))<br>[Pixel handoff checks](../assets/source/journal/pocket/tests/test_map_pixel_handoff.py.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/tests/test_map_pixel_handoff.py)) |
| Build inputs | [Graphics build and checks](../assets/source/journal/pocket/Makefile.txt) ([GitHub](https://github.com/gordol/n810-revival/blob/main/pocket/Makefile)) |

[Build and test instructions](../how-to/validate.md) · [Chronological source index](../reference/journal-sources.md#2026-11-11-pocket-map-rendering)

Host Metal and source-only checks accompany this port. N810 device acceptance remains separate. Public map acquisition inputs and local settings are excluded from Git.
<!-- journal-sources:end -->
