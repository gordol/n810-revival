# Console font provenance

The original 256 glyphs in `pocket/shell/vendor/console-icons/base-console-8x16.psf`
match all 4,096 bitmap bytes in Linux 5.15.224 `lib/fonts/font_8x16.c`.
The comparison source is retained in [the evidence directory](evidence/linux-5.15.224-font_8x16.c).
Its SPDX declaration is GPL-2.0 (GPL version 2 only). Preserve those terms for
that bitmap material; the project's custom license supplies no replacement grant.
The GPL version 2 text is retained in [the upstream license collection](upstream/aprslib-LICENSE.txt).

The 512-slot base file exactly matches the project's 16 October additive font
expansion output. The expansion starts with the 256 saved device glyphs and
adds programmatically drawn fractional blocks, quadrants, rules, punctuation,
status symbols and Powerline-shaped separators. The retained expansion script
identifies the added basic icons as original pixel drawings. The later canonical
font changes ten of the original slots; 246 remain byte-identical to the Linux
comparison. This establishes bitmap correspondence and the local expansion
chain, rather than the exact historical Linux revision used by the device.

The original additions identified in `LICENSE-SCOPE.json` now have GPL-2.0-or-later permission under [the original code grant](ORIGINAL-CODE-GPL.md). The Linux-derived bitmap remains GPL-2.0-only.

The package contains Console 8x16. The unused Terminus and Inconsolata variants
and their catalog entries were removed on 7 November 2026. The retained console
font's bytes and existing license notices are unchanged.

Reviewed 7 November 2026. The comparison used decoded glyph bytes, independent
of the PSF container header and Unicode mapping table. No fonts were installed on a device during this review.
