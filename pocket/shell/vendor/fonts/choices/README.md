# Console font

`console-8x16.psf` is the packaged N810 console font. `catalog.json` records
its dimensions, SHA-256, 512 glyph slots and 353 Unicode mappings. The font
includes the console rules, fractional blocks and Powerline symbols used by
Pocket. Its bitmap is unchanged by the removal of the unused alternate fonts.

The Font Preview reads this bitmap through the catalog. A saved selection for
an unavailable font falls back to Console 8x16. On SSH, the terminal application
controls the displayed font. The preview leaves the terminal and device font
settings unchanged.

Linux-derived glyphs retain GPL-2.0-only terms. Original additions have the
compatible grant recorded in the root `LICENSE-SCOPE.json`. See
`licenses/FONTS.md` at the repository root for the source comparison and notices.
