# Pocket 0.1.0

First product-versioned ecosystem release. Exact commit and payload identities
remain in build-info.json and the installer receipt.

- Shared map sidebar, band filters, glyph grid, road and water detail, station
  retention during navigation, and zoom-request feedback.
- Terrain profiles and radius LOS with cancellation, desktop worker isolation,
  bounded refinement and a per-app off switch. Terrain-only estimates remain
  distinct from measured RF coverage.
- Persistent repeater directory, details and shared-owner UV-Pro secondary-B
  tuning with offset/tone configuration and restoration.
- Separate opt-in APRS Internet fill and bounded message evidence; Internet
  positions do not become RF-heard records.
- Integrated station/FCC lookup navigation, clearer window chrome, cleaner chat
  presentation and compact panel status menus.
- Shared reference-data discovery for installed devices and explicit product
  version alongside immutable source/build identities.

Debian packaging and an APT repository are deferred. Nokia deployment retains
its existing guarded installer and rollback selector. Firmware, kernel and
modem/HF work are outside this release. Hardware acceptance is recorded in a
separate deployment receipt; this changelog does not assert RF delivery.
