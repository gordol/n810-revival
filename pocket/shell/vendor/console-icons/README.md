# Approved compact icon set

The user approved the 48-glyph preview on October 23, 2026. This local font adds
U+E100 through U+E12F to previously unmapped slots in console-8x16.psf. Existing
mapped glyph bitmaps and Unicode mappings are preserved; 158 unmapped slots remain.

Each icon occupies one 8x16 cell. These are custom private-use symbols, not official
APRS symbol artwork or Unicode emoji. Applications must use the manifest explicitly;
installing this font alone does not add markers to an application.

build.py runs in the offline font sandbox with the base font at /sample/font.psf
and writes to /out. It reads the emitted font back and renders preview.png's source
image from those glyphs. No physical-device installation has been performed.

The 8x16 asset must not silently replace a different active font size. Deployment
and actual application integration are coordinated through the project coordinator.

## Unicode-first correction

All additions remain one cell. The manifest codepoint is the primary app mapping;
compatibility_alias retains the original PUA codepoint. Home, Weather, Envelope,
Gear, and Power use semantic BMP Unicode defaults. If a standard mapping already
exists, primary_slot references that existing glyph without replacing it.
semantic_unicode records additional suitable emoji characters, but supplementary
characters are deferred pending renderer/width verification; no two-cell support
or variation-selector sequences are introduced. Specialised symbols retain PUA.

This artifact is artwork and mapping input, not a wholesale replacement for the
canonical device font. Runtime must graft additions onto its canonical font,
preserving all existing glyphs, mappings, box rules and active geometry. Desktop
primary characters also require the current renderer's width check before use.
