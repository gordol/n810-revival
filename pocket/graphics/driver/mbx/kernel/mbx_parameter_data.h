/* SPDX-License-Identifier: MIT */
#ifndef N810_MBX_PARAMETER_DATA_H
#define N810_MBX_PARAMETER_DATA_H
#define MBX_BACKGROUND_WORDS 26U
/* CPU-side constructors only. Buffer byte order is the ARM little-endian word
 * order. Original Nokia initializer0x801ba85c and tile list0x801bb844..8b8. */
int mbx_background_parameter(unsigned *words,unsigned capacity_words);
int mbx_tile_headers(unsigned *words,unsigned capacity_words,unsigned tiles_x,unsigned tiles_y,unsigned group_x,unsigned group_y);
/* Original full-core32x32 frame rounds to2x2 tiles and groups4x4 tiles.
 * The padded list therefore contains16 entries; only the last gets END. */
int mbx_render_list32(unsigned *words,unsigned capacity_words);
int mbx_background32(unsigned *words,unsigned capacity_words);

#endif
