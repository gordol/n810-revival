/* SPDX-License-Identifier: MIT */
#ifndef MBX_BLEND_STATE_H
#define MBX_BLEND_STATE_H
/* Reference-derived factor field only. Not a complete render-state word.
 * No claim of N810 blend acceptance. Separate alpha/equations unsupported.
 * factor values are OpenGL enums; output unchanged on failure. */
int mbx_blend_factors(unsigned source,unsigned destination,unsigned *bits);
#endif
