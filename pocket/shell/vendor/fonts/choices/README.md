# Device font choices

Local font candidates for the N810 Linux virtual console. `catalog.json` supplies
stable IDs, dimensions, 800x480 text grids, hashes and preview regions. Generate
with `python3 console-fonts/build-choices.py` from the project root.

All five PSF2 files retain the working console font's 512 slots and 353 Unicode
mappings, including Powerline U+E0A0–U+E0A2 and U+E0B0–U+E0B7. Console 8x16 is
byte-identical to the device-tested cf22797a font. Other choices use their family's
mapped bitmaps and resized console glyphs for missing characters. UI box rules,
blocks and Powerline symbols use shared console geometry; area coverage preserves
thin strokes at smaller sizes. These are font variants with a shared symbol set,
not complete upstream fonts or a full Nerd Fonts collection.

The builder checks PSF round trips, exact Unicode mappings, nonempty Powerline
bitmaps and identity of the original choice. The preview uses the actual packaged
bitmaps. New variants still need physical review for readability, connected rules,
Powerline, colors and application resize behavior. The existing Console 8x16 is
the tested fallback. Font source licensing remains with the source assets;
Inconsolata's license is ../LICENSE-Inconsolata.txt.

## Integration contract

- Target `linux-vt`, capability `font512-unicode`; all new variants are local
  candidates. Selection is preview-only until the operator validates application
  and restoration through the current session helper.
- Family IDs: `console`, `terminus`, `inconsolata`; size IDs: `8x16`, `8x14`, `6x12`,
  `7x14`. Persist the complete catalog ID. Only expose sizes listed for a family.
- Apply through the existing helper on its reserved VT, preserving its current
  font backup and restoration. Do not deploy the old tty1 font switcher.
- Font dimensions change the terminal grid. Notify/reflow the application after
  applying a choice and keep its glyph-profile selection consistent with the PSF.
- On SSH, the local terminal app controls font selection; selecting a device font
  does not change the Mac terminal's font.
- No kernel, palette, boot default or physical device change is included here.
