/* SPDX-License-Identifier: MIT */
#ifndef MBX_NATIVE_CELLS_H
#define MBX_NATIVE_CELLS_H
#include "present.h"
/* MSB-first monochrome glyph, opaque RGB565 foreground/background. */
int mbx_cell_rgb565(struct mbx_surface *surface,unsigned x,unsigned y,
                   unsigned width,unsigned height,const unsigned char *glyph,
                   size_t glyph_bytes,uint16_t foreground,uint16_t background);
#endif
