/* SPDX-License-Identifier: MIT
 * Exact interior fast path for the standard homogeneous clipping cube.
 * Outside, negative-W and nonfinite vertices retain Mesa's plane tests.
 * Integer magnitude comparisons avoid six VFP additions/comparisons for
 * interior vertices, without changing coordinates or clipping precision.
 */
#ifndef DRAW_MBX_CLIP_H
#define DRAW_MBX_CLIP_H
#include <stdint.h>
#include <string.h>
static inline int mbx_clip_cube_inside(const float p[4])
{
 uint32_t b[4];memcpy(b,p,sizeof(b));
 uint32_t w=b[3];
 return w>=0x00800000u && w<0x7f800000u &&
        (b[0]&0x7fffffffu)<=w && (b[1]&0x7fffffffu)<=w &&
        (b[2]&0x7fffffffu)<=w;
}
#endif
